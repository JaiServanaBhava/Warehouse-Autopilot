"""Warehouse operations: picking, packing, QC, dispatch, workers."""
from fastapi import APIRouter, HTTPException, Body
from ..db import db_cursor, now_iso
from ..schemas import WorkerIn
from ..engines import optimize_route, log_activity
from ..services.alert import create_alert
from ..events import hub
import uuid, json

router = APIRouter()


# ---------- workers ----------
@router.get("/workers")
def list_workers():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM workers ORDER BY name")
        return cur.fetchall()


@router.post("/workers")
def create_worker(body: WorkerIn):
    wid = str(uuid.uuid4())
    with db_cursor() as cur:
        cur.execute("INSERT INTO workers(id,name,role,available,workload,efficiency,current_task) VALUES(?,?,?,?,?,?,?)",
                    (wid, body.name, body.role, int(body.available), 0, body.efficiency, None))
    hub.publish("worker_updated", {})
    return {"id": wid}


@router.put("/workers/{wid}/toggle")
def toggle_worker(wid: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM workers WHERE id=?", (wid,))
        w = cur.fetchone()
        if not w:
            raise HTTPException(404)
        cur.execute("UPDATE workers SET available=? WHERE id=?", (0 if w["available"] else 1, wid))
    hub.publish("worker_updated", {})
    return {"ok": True}


@router.put("/workers/{wid}/reassign")
def reassign_worker(wid: str, role: str = Body(..., embed=True)):
    with db_cursor() as cur:
        cur.execute("UPDATE workers SET role=? WHERE id=?", (role, wid))
    log_activity("worker", f"Reassigned worker to {role}", "worker", wid)
    hub.publish("worker_updated", {})
    return {"ok": True}


# ---------- pipeline / tasks ----------
STAGES = ["PICKING", "PACKING", "QC", "DISPATCH"]


@router.get("/tasks")
def list_tasks(stage: str = "", status: str = ""):
    q = "SELECT t.*, o.order_no, o.customer_name, o.priority, o.customer_priority, w.name as worker_name FROM tasks t LEFT JOIN orders o ON o.id=t.order_id LEFT JOIN workers w ON w.id=t.worker_id WHERE 1=1"
    args = []
    if stage:
        q += " AND t.stage=?"; args.append(stage)
    if status:
        q += " AND t.status=?"; args.append(status)
    q += " ORDER BY o.priority_score DESC, t.started_at"
    with db_cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall()


def _create_task(order_id: str, stage: str, worker_id: str = None, route=None):
    tid = str(uuid.uuid4())
    with db_cursor() as cur:
        cur.execute("INSERT INTO tasks(id,order_id,stage,worker_id,status,route) VALUES(?,?,?,?,?,?)",
                    (tid, order_id, stage, worker_id, "QUEUED", json.dumps(route) if route else None))
        if worker_id:
            cur.execute("UPDATE workers SET workload=workload+1 WHERE id=?", (worker_id,))
    return tid


@router.post("/tasks/start-picking")
def start_picking(order_id: str = Body(..., embed=True), worker_id: str = Body(None, embed=True)):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        o = cur.fetchone()
        if not o or o["status"] not in ("ALLOCATED", "PARTIALLY_ALLOCATED"):
            raise HTTPException(400, "Order not ready for picking")
        cur.execute("""SELECT p.location FROM order_items oi JOIN products p ON p.id=oi.product_id WHERE oi.order_id=?""", (order_id,))
        locs = [r["location"] for r in cur.fetchall() if r["location"]]
    route = optimize_route(locs)
    # auto-pick available picker if not specified
    if not worker_id:
        with db_cursor() as cur:
            cur.execute("SELECT id FROM workers WHERE role='PICKER' AND available=1 ORDER BY workload ASC LIMIT 1")
            row = cur.fetchone()
            if row:
                worker_id = row["id"]
    tid = _create_task(order_id, "PICKING", worker_id, route)
    with db_cursor() as cur:
        cur.execute("UPDATE tasks SET status='IN_PROGRESS', started_at=? WHERE id=?", (now_iso(), tid))
        cur.execute("UPDATE orders SET status='PICKING' WHERE id=?", (order_id,))
    log_activity("picking", f"Started picking for {o['order_no']}", "order", order_id, meta={"route": route})
    hub.publish("order_updated", {"id": order_id})
    return {"task_id": tid, "route": route}


@router.post("/tasks/{tid}/complete")
def complete_task(tid: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tasks WHERE id=?", (tid,))
        t = cur.fetchone()
        if not t:
            raise HTTPException(404)
        cur.execute("UPDATE tasks SET status='DONE', completed_at=? WHERE id=?", (now_iso(), tid))
        if t["worker_id"]:
            cur.execute("UPDATE workers SET workload=MAX(0, workload-1) WHERE id=?", (t["worker_id"],))
        cur.execute("SELECT * FROM orders WHERE id=?", (t["order_id"],))
        o = cur.fetchone()
        # advance to next stage
        stage_order = {"PICKING": "PACKING", "PACKING": "QC", "QC": "DISPATCH", "DISPATCH": None}
        next_stage = stage_order.get(t["stage"])
        if next_stage:
            # auto-assign worker for next stage
            role_map = {"PACKING": "PACKER", "QC": "QC", "DISPATCH": "DISPATCH"}
            cur.execute("SELECT id FROM workers WHERE role=? AND available=1 ORDER BY workload ASC LIMIT 1",
                        (role_map[next_stage],))
            wr = cur.fetchone()
            wid = wr["id"] if wr else None
            ntid = str(uuid.uuid4())
            cur.execute("INSERT INTO tasks(id,order_id,stage,worker_id,status) VALUES(?,?,?,?,?)",
                        (ntid, t["order_id"], next_stage, wid, "QUEUED"))
            if wid:
                cur.execute("UPDATE workers SET workload=workload+1 WHERE id=?", (wid,))
            cur.execute("UPDATE orders SET status=? WHERE id=?", (next_stage, t["order_id"]))
        else:
            # DISPATCH complete
            cur.execute("UPDATE orders SET status='DISPATCHED', dispatched_at=? WHERE id=?", (now_iso(), t["order_id"]))
            # deduct reserved from physical
            cur.execute("SELECT * FROM order_items WHERE order_id=?", (t["order_id"],))
            for it in cur.fetchall():
                cur.execute("UPDATE products SET physical_stock=MAX(0,physical_stock-?), reserved_stock=MAX(0,reserved_stock-?) WHERE id=?",
                            (it["allocated"], it["allocated"], it["product_id"]))
    log_activity("ops", f"Completed {t['stage']} for {o['order_no']}", "order", t["order_id"])
    hub.publish("order_updated", {"id": t["order_id"]})
    hub.publish("inventory_updated", {})
    return {"ok": True, "next_stage": stage_order.get(t["stage"])}


@router.post("/tasks/{tid}/qc")
def qc_result(tid: str, passed: bool = Body(..., embed=True), notes: str = Body("", embed=True)):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tasks WHERE id=?", (tid,))
        t = cur.fetchone()
        if not t or t["stage"] != "QC":
            raise HTTPException(400, "Not a QC task")
    if passed:
        return complete_task(tid)
    else:
        # Create exception
        with db_cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE id=?", (t["order_id"],))
            o = cur.fetchone()
            cur.execute("INSERT INTO exceptions(id,type,severity,order_id,description,status,created_at) VALUES(?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), "QC_FAIL", "HIGH", t["order_id"],
                         notes or f"QC failed for {o['order_no']}", "OPEN", now_iso()))
            cur.execute("UPDATE tasks SET status='FAILED', completed_at=? WHERE id=?", (now_iso(), tid))
            cur.execute("UPDATE orders SET status='EXCEPTION' WHERE id=?", (t["order_id"],))
        create_alert(
            "QC_FAIL", "HIGH", f"QC failed: {o['order_no']}",
            f"Order: {o['order_no']}\nCustomer: {o['customer_name']}\nReason: {notes or 'Quality check failed.'}\n"
            f"Recommended Action: Inspect flagged items and re-route for rework or replacement.",
            "order", t["order_id"], {"order_no": o["order_no"], "notes": notes},
            "Inspect flagged items and re-route for rework", {"critical_order_risk"},
            event_key=f"QC_FAIL:{t['id']}",
        )
        hub.publish("order_updated", {"id": t["order_id"]})
        return {"ok": True, "exception": True}


@router.get("/pipeline/queues")
def pipeline_queues():
    with db_cursor() as cur:
        result = {}
        for s in STAGES:
            cur.execute("""SELECT t.*, o.order_no, o.customer_name, o.priority, o.priority_score, o.risk_score, w.name as worker_name
                           FROM tasks t LEFT JOIN orders o ON o.id=t.order_id LEFT JOIN workers w ON w.id=t.worker_id
                           WHERE t.stage=? AND t.status IN ('QUEUED','IN_PROGRESS')
                           ORDER BY o.priority_score DESC""", (s,))
            result[s] = cur.fetchall()
    return result