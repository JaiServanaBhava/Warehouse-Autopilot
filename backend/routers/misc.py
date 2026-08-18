from fastapi import APIRouter, HTTPException, Body, Request
from fastapi.responses import StreamingResponse
from ..db import db_cursor, now_iso, get_setting, set_setting
from ..schemas import ExceptionIn
from ..engines import (
    generate_decisions, persist_decision, warehouse_health, business_impact,
    autopilot_score, compute_available, log_activity, allocate_inventory,
    forecast_product, stock_status, get_autopilot_action_queue,
    execute_autopilot_action, get_warehouse_heatmap, rebalance_zone_workers
)
from ..services.alert import create_alert, resolve_alert
from ..events import hub
from ..seed import seed_demo
import uuid, json, asyncio
from datetime import datetime, timezone, timedelta

router = APIRouter()


# =============== EXCEPTIONS ===============
@router.get("/exceptions")
def list_exceptions(status: str = ""):
    q = "SELECT e.*, o.order_no, p.sku, p.name as product_name FROM exceptions e LEFT JOIN orders o ON o.id=e.order_id LEFT JOIN products p ON p.id=e.product_id WHERE 1=1"
    args = []
    if status:
        q += " AND e.status=?"; args.append(status)
    q += " ORDER BY e.created_at DESC"
    with db_cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall()


@router.post("/exceptions")
def create_exception(body: ExceptionIn):
    eid = str(uuid.uuid4())
    with db_cursor() as cur:
        cur.execute("INSERT INTO exceptions(id,type,severity,order_id,product_id,description,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (eid, body.type, body.severity, body.order_id, body.product_id, body.description, "OPEN", now_iso()))
    log_activity("exception", f"Exception: {body.description}", "exception", eid)
    create_alert(
        body.type, body.severity, f"Exception: {body.type}", body.description,
        "exception", eid, {"exception_type": body.type}, "Review and resolve the exception",
        {"critical_order_risk"} if body.severity in ("HIGH", "CRITICAL") else set(),
        event_key=f"EXCEPTION:{eid}",
    )
    hub.publish("exception", {"id": eid})
    return {"id": eid}


@router.post("/exceptions/{eid}/resolve")
def resolve_exception(eid: str, resolution: str = Body("Resolved by manager", embed=True)):
    with db_cursor() as cur:
        cur.execute("UPDATE exceptions SET status='RESOLVED', resolved_at=?, resolution=? WHERE id=?",
                    (now_iso(), resolution, eid))
    log_activity("exception", f"Resolved exception", "exception", eid)
    hub.publish("exception", {"id": eid})
    return {"ok": True}


# =============== DECISIONS ===============
@router.get("/decisions")
def list_decisions(regenerate: bool = True):
    if regenerate:
        # persist newly generated decisions
        decisions = generate_decisions()
        # clear pending, keep applied/dismissed
        with db_cursor() as cur:
            cur.execute("DELETE FROM decisions WHERE status='PENDING'")
        for d in decisions:
            persist_decision(d)
    with db_cursor() as cur:
        cur.execute("SELECT * FROM decisions ORDER BY created_at DESC LIMIT 50")
        rows = cur.fetchall()
    for r in rows:
        try:
            r["impact"] = json.loads(r["impact"]) if r["impact"] else {}
            r["alternatives"] = json.loads(r["alternatives"]) if r["alternatives"] else []
        except Exception:
            pass
    return rows


@router.post("/decisions/{did}/apply")
def apply_decision(did: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM decisions WHERE id=?", (did,))
        d = cur.fetchone()
        if not d:
            raise HTTPException(404)
        impact = json.loads(d["impact"]) if d["impact"] else {}
    result = ""
    # apply simple heuristics based on decision content
    if "product_id" in impact and "units_needed" in impact:
        # simulate reorder: add stock
        pid = impact["product_id"]; qty = impact["units_needed"]
        with db_cursor() as cur:
            cur.execute("UPDATE products SET physical_stock=physical_stock+? WHERE id=?", (qty, pid))
        result = f"Received {qty} units for {impact.get('product_id')[:8]}"
        hub.publish("inventory_updated", {})
    elif "stage" in impact:
        result = f"Reassigned worker to {impact['stage']}"
        # move first available idle worker to that stage's role role_map
        role_map = {"PICKING": "PICKER", "PACKING": "PACKER", "QC": "QC", "DISPATCH": "DISPATCH"}
        target_role = role_map.get(impact["stage"], "PACKER")
        with db_cursor() as cur:
            cur.execute("SELECT id FROM workers WHERE role!=? AND available=1 ORDER BY workload ASC LIMIT 1", (target_role,))
            w = cur.fetchone()
            if w:
                cur.execute("UPDATE workers SET role=? WHERE id=?", (target_role, w["id"]))
        hub.publish("worker_updated", {})
    else:
        result = "Decision noted"
    with db_cursor() as cur:
        cur.execute("UPDATE decisions SET status='APPLIED', applied_at=?, result=?, actual=? WHERE id=?",
                    (now_iso(), result, json.dumps({"result": result}), did))
    log_activity("decision", f"Applied: {d['recommendation']}", "decision", did)
    hub.publish("decision_applied", {"id": did})
    return {"ok": True, "result": result}


@router.post("/decisions/{did}/dismiss")
def dismiss_decision(did: str):
    with db_cursor() as cur:
        cur.execute("UPDATE decisions SET status='DISMISSED' WHERE id=?", (did,))
    hub.publish("decision_applied", {})
    return {"ok": True}


@router.post("/decisions/apply-safe")
def apply_safe_actions():
    """Apply all high-confidence, independent decisions."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM decisions WHERE status='PENDING' AND confidence>=80 ORDER BY confidence DESC LIMIT 5")
        pending = cur.fetchall()
    applied = 0
    for d in pending:
        apply_decision(d["id"])
        applied += 1
    return {"applied": applied}


@router.get("/decisions/{did}/simulate")
def simulate_decision(did: str):
    """Simulate ACT vs DO-NOTHING states without mutating DB."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM decisions WHERE id=?", (did,))
        d = cur.fetchone()
        if not d:
            raise HTTPException(404)
        impact = json.loads(d["impact"]) if d["impact"] else {}
    current = warehouse_health()
    b_impact = business_impact()
    # Estimated improvements based on decision confidence & type
    conf = d["confidence"] / 100
    delta = int(15 * conf)
    simulated = {
        "overall": min(100, current["overall"] + delta),
        "breakdown": current["breakdown"],
    }
    do_nothing = {
        "overall": max(0, current["overall"] - int(10 * conf)),
    }
    return {
        "current": current,
        "act": simulated,
        "do_nothing": do_nothing,
        "impact": {
            "delayed_orders_change": {"current": b_impact["orders_at_risk"], "act": max(0, b_impact["orders_at_risk"] - int(3 * conf)), "do_nothing": b_impact["orders_at_risk"] + 4},
            "potential_loss": {"current": b_impact["potential_loss"], "act": int(b_impact["potential_loss"] * (1 - conf * 0.7)), "do_nothing": int(b_impact["potential_loss"] * 1.6)},
        },
        "explanation": f"Applying '{d['recommendation']}' has {d['confidence']}% confidence based on: {d['reason']}"
    }


# =============== GENERIC SETTINGS (non-alert) ===============
# Alert/email/WhatsApp/notification settings live under /api/notifications/settings
# (routers/alerts.py). This stays for general app settings like warehouse_name,
# automation_enabled and the presence flag.
@router.get("/settings")
def get_settings():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM settings")
        return {r["key"]: r["value"] for r in cur.fetchall()}


@router.put("/settings/{key}")
def update_setting(key: str, value: str = Body(..., embed=True)):
    set_setting(key, value)
    hub.publish("settings", {"key": key, "value": value})
    return {"ok": True}


# =============== ANALYTICS / DASHBOARD ===============
BUSINESS_LOSS_THRESHOLD = 25000


def _check_business_loss_alert(impact: dict):
    """React to real, computed business impact — not a timer or fake value."""
    if impact.get("potential_loss", 0) < BUSINESS_LOSS_THRESHOLD:
        resolve_alert("MAJOR_BUSINESS_LOSS:global")
        return
    body = (
        f"Orders at risk: {impact['orders_at_risk']}\n"
        f"Value at risk: ₹{impact['total_value_at_risk']:,.0f}\n"
        f"Estimated penalty: ₹{impact['estimated_penalty']:,.0f}\n"
        f"Potential loss: ₹{impact['potential_loss']:,.0f}\n\n"
        f"Reason: Multiple orders are at risk of delay/failure due to stock shortages or fulfillment bottlenecks.\n"
        f"Recommended Action: Review Decisions and apply high-confidence recommendations."
    )
    create_alert(
        "MAJOR_BUSINESS_LOSS", "CRITICAL", "Major estimated business loss", body,
        "system", "", impact, "Review and apply pending decisions", {"major_loss"},
        event_key="MAJOR_BUSINESS_LOSS:global",
    )


@router.get("/dashboard")
def dashboard():
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as c, SUM(physical_stock) as ps, SUM(reserved_stock) as rs, SUM(damaged_stock) as ds FROM products")
        p = cur.fetchone()
        cur.execute("SELECT * FROM products")
        prods = cur.fetchall()
        cur.execute("SELECT status, COUNT(*) as c FROM orders GROUP BY status")
        order_stats = {r["status"]: r["c"] for r in cur.fetchall()}
        cur.execute("SELECT priority, COUNT(*) as c FROM orders WHERE status NOT IN ('DISPATCHED','CANCELLED') GROUP BY priority")
        prio_stats = {r["priority"]: r["c"] for r in cur.fetchall()}
        cur.execute("SELECT stage, COUNT(*) as c FROM tasks WHERE status IN ('QUEUED','IN_PROGRESS') GROUP BY stage")
        queues = {r["stage"]: r["c"] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) as c FROM exceptions WHERE status='OPEN'")
        open_exc = cur.fetchone()["c"]
        cur.execute("SELECT * FROM activity ORDER BY at DESC LIMIT 12")
        activity = cur.fetchall()
        cur.execute("SELECT * FROM decisions WHERE status='PENDING' ORDER BY confidence DESC LIMIT 5")
        recs = cur.fetchall()
    for r in recs:
        try:
            r["impact"] = json.loads(r["impact"]) if r["impact"] else {}
            r["alternatives"] = json.loads(r["alternatives"]) if r["alternatives"] else []
        except Exception:
            pass

    low = sum(1 for pr in prods if stock_status(pr) in ("LOW", "CRITICAL"))
    oos = sum(1 for pr in prods if stock_status(pr) == "OUT_OF_STOCK")
    total_stock = p["ps"] or 0
    reserved = p["rs"] or 0
    damaged = p["ds"] or 0
    available = total_stock - reserved - damaged
    health = warehouse_health()
    impact = business_impact()
    autopilot = autopilot_score()
    _check_business_loss_alert(impact)

    return {
        "products_total": p["c"] or 0,
        "total_stock": total_stock,
        "available_stock": available,
        "reserved_stock": reserved,
        "damaged_stock": damaged,
        "low_stock_products": low,
        "out_of_stock_products": oos,
        "order_stats": order_stats,
        "priority_stats": prio_stats,
        "queues": queues,
        "open_exceptions": open_exc,
        "health": health,
        "impact": impact,
        "autopilot": autopilot,
        "recent_activity": activity,
        "recommendations": recs,
        "warehouse_name": get_setting("warehouse_name", "Central DC"),
    }


@router.get("/analytics/health")
def health_endpoint():
    return warehouse_health()


@router.get("/analytics/impact")
def impact_endpoint():
    return business_impact()


@router.get("/analytics/risk-radar")
def risk_radar():
    """Future risk projections in 3h intervals."""
    slots = []
    with db_cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE status NOT IN ('DISPATCHED','CANCELLED')")
        orders = cur.fetchall()
        cur.execute("SELECT * FROM products")
        products = cur.fetchall()
    now = datetime.now(timezone.utc)
    for h in [0, 3, 6, 9, 12]:
        t = now + timedelta(hours=h)
        risks = []
        for o in orders:
            try:
                deadline = datetime.fromisoformat(o["required_by"].replace("Z", "+00:00"))
                left = (deadline - t).total_seconds() / 3600
                if left < 2:
                    risks.append(f"{o['order_no']} deadline")
            except Exception:
                pass
        # product stockouts
        for pr in products:
            demand = pr["avg_daily_demand"]
            projected = compute_available(pr) - int(demand * (h / 24))
            if projected <= 0:
                risks.append(f"{pr['sku']} stockout")
        level = "CRITICAL" if len(risks) >= 3 else "HIGH" if len(risks) >= 1 else "NORMAL"
        slots.append({"hour_offset": h, "time": t.isoformat(), "level": level, "risks": risks[:4]})
    return slots


@router.get("/analytics/dependency-graph/{eid}")
def dep_graph(eid: str):
    """Show impact graph for an exception."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM exceptions WHERE id=?", (eid,))
        e = cur.fetchone()
        if not e:
            raise HTTPException(404)
        cur.execute("SELECT * FROM orders WHERE status NOT IN ('DISPATCHED','CANCELLED')")
        orders = cur.fetchall()
    nodes = [{"id": "exc", "label": e["description"], "type": "exception"}]
    edges = []
    if e["product_id"]:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id=?", (e["product_id"],))
            p = cur.fetchone()
        if p:
            nodes.append({"id": "prod", "label": f"{p['sku']} {p['name']}", "type": "product"})
            edges.append({"from": "exc", "to": "prod"})
            # affected orders
            for o in orders:
                with db_cursor() as cur:
                    cur.execute("SELECT * FROM order_items WHERE order_id=? AND product_id=?", (o["id"], p["id"]))
                    if cur.fetchone():
                        nodes.append({"id": o["id"], "label": o["order_no"], "type": "order"})
                        edges.append({"from": "prod", "to": o["id"]})
    return {"nodes": nodes, "edges": edges}


# =============== AUTOPILOT ACTION QUEUE ===============
@router.get("/autopilot/actions")
def list_autopilot_actions():
    """Live ranked 1-click action queue: Impact -> Reason -> Confidence -> Execute."""
    return get_autopilot_action_queue()


@router.post("/autopilot/actions/execute")
async def execute_action(body: dict = Body(...)):
    action_type = body.get("type")
    params = body.get("params", {})
    if not action_type:
        raise HTTPException(400, "Action type is required")
    return await execute_autopilot_action(action_type, params)


# =============== BOTTLENECK HEATMAP & WORKER REBALANCING ===============
@router.get("/warehouse/heatmap")
def heatmap():
    """Zone congestion, active orders, worker loads, and auto-recommendations."""
    return get_warehouse_heatmap()


@router.post("/warehouse/rebalance-workers")
def rebalance_workers():
    """Executes automated worker rebalancing across overloaded zones."""
    return rebalance_zone_workers()


# =============== DEMO / SEED ===============
@router.post("/demo/reset")
def reset_demo(body: dict = Body(default={})):
    custom_email = body.get("company_email") or body.get("email")
    if custom_email and "@" in custom_email:
        set_setting("company_email", custom_email.strip())
        set_setting("email_recipient", custom_email.strip())
    res = seed_demo(reset=True, custom_recipient=custom_email)
    hub.publish("reset", {"recipient": res.get("recipient")})
    return {"ok": True, "recipient": res.get("recipient")}


@router.get("/activity")
def recent_activity(limit: int = 40):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM activity ORDER BY at DESC LIMIT ?", (limit,))
        return cur.fetchall()


@router.get("/audit")
def audit_log(limit: int = 100):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM audit_log ORDER BY at DESC LIMIT ?", (limit,))
        return cur.fetchall()


@router.get("/search")
def global_search(q: str):
    q = f"%{q}%"
    with db_cursor() as cur:
        cur.execute("SELECT id, sku, name FROM products WHERE sku LIKE ? OR name LIKE ? LIMIT 10", (q, q))
        products = cur.fetchall()
        cur.execute("SELECT id, order_no, customer_name FROM orders WHERE order_no LIKE ? OR customer_name LIKE ? LIMIT 10", (q, q))
        orders = cur.fetchall()
        cur.execute("SELECT id, description FROM exceptions WHERE description LIKE ? LIMIT 10", (q,))
        excs = cur.fetchall()
    return {"products": products, "orders": orders, "exceptions": excs}


# =============== WAREHOUSE MAP ===============
@router.get("/warehouse/map")
def warehouse_map():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products")
        products = cur.fetchall()
        cur.execute("SELECT stage, order_id, worker_id FROM tasks WHERE status IN ('QUEUED','IN_PROGRESS')")
        tasks = cur.fetchall()
    zones = {}
    for p in products:
        loc = p["location"] or "A01"
        z = zones.setdefault(loc, {"location": loc, "products": [], "status": "NORMAL", "issues": 0})
        st = stock_status(p)
        z["products"].append({
            "id": p["id"], "sku": p["sku"], "name": p["name"],
            "physical": p["physical_stock"], "reserved": p["reserved_stock"],
            "damaged": p["damaged_stock"], "available": compute_available(p), "status": st
        })
        if st in ("CRITICAL", "OUT_OF_STOCK"):
            z["issues"] += 1
    for z in zones.values():
        if any(p["status"] == "OUT_OF_STOCK" for p in z["products"]):
            z["status"] = "OUT_OF_STOCK"
        elif any(p["status"] == "CRITICAL" for p in z["products"]):
            z["status"] = "CRITICAL"
        elif any(p["status"] == "LOW" for p in z["products"]):
            z["status"] = "LOW"
        else:
            z["status"] = "NORMAL"
    return list(zones.values())


# =============== SSE ===============
@router.get("/events/stream")
async def sse_stream(request: Request):
    q = hub.subscribe()

    async def gen():
        try:
            # send initial hello
            yield "data: {\"event\":\"ready\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })