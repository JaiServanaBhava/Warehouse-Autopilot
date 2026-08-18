"""Orders + priority + allocation routes."""
from fastapi import APIRouter, HTTPException
from ..db import db_cursor, now_iso
from ..schemas import OrderIn
from ..engines import (
    compute_priority, compute_risk, allocate_inventory, release_allocation,
    log_activity, audit
)
from ..services.alert import create_alert, resolve_alert
from ..events import hub
import uuid, json
from datetime import datetime, timezone

router = APIRouter()


def _load_items(order_id: str) -> list:
    with db_cursor() as cur:
        cur.execute("""SELECT oi.*, p.name as pname, p.sku, p.location, p.physical_stock, p.reserved_stock, p.damaged_stock, p.avg_daily_demand
                       FROM order_items oi JOIN products p ON p.id=oi.product_id WHERE oi.order_id=?""", (order_id,))
        rows = cur.fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r["id"], "product_id": r["product_id"], "quantity": r["quantity"],
            "allocated": r["allocated"], "picked": r["picked"],
            "product_name": r["pname"], "sku": r["sku"], "location": r["location"],
            "product": {
                "physical_stock": r["physical_stock"], "reserved_stock": r["reserved_stock"],
                "damaged_stock": r["damaged_stock"], "avg_daily_demand": r["avg_daily_demand"]
            }
        })
    return items


def _enrich_order(o: dict) -> dict:
    items = _load_items(o["id"])
    prio = compute_priority(o, items)
    risk = compute_risk(o, items)
    with db_cursor() as cur:
        cur.execute("UPDATE orders SET priority=?, priority_score=?, priority_reasons=?, risk_score=?, risk_reasons=? WHERE id=?",
                    (prio["priority"], prio["score"], json.dumps(prio["reasons"]),
                     risk["score"], json.dumps(risk["reasons"]), o["id"]))
    o = dict(o)
    o["priority"] = prio["priority"]
    o["priority_score"] = prio["score"]
    o["priority_reasons"] = prio["reasons"]
    o["risk_score"] = risk["score"]
    o["risk_level"] = risk["level"]
    o["risk_reasons"] = risk["reasons"]
    o["items"] = items
    if o["status"] not in ("DISPATCHED", "CANCELLED"):
        _order_risk_alert(o, risk)
    return o


def _order_risk_alert(o: dict, risk: dict):
    """React to a real, computed risk level for an order — no random ticks."""
    if risk["level"] not in ("HIGH", "CRITICAL"):
        resolve_alert(f"ORDER_AT_RISK:{o['id']}")
        return
    severity = "CRITICAL" if (risk["level"] == "CRITICAL" or o.get("customer_priority") in ("VIP", "HIGH")) else "HIGH"
    high_value = (o.get("order_value") or 0) >= 10000
    rule_keys = {"critical_order_risk"}
    if high_value:
        rule_keys.add("high_value_risk")
    body = (
        f"Order: {o['order_no']}\nCustomer: {o['customer_name']}\n"
        f"Priority: {o.get('customer_priority')}\nOrder value: ₹{(o.get('order_value') or 0):,.0f}\n"
        f"Risk score: {risk['score']} ({risk['level']})\nReasons: {'; '.join(risk['reasons'])}\n"
        f"Recommended Action: Expedite picking/allocation or transfer stock to cover the shortfall."
    )
    create_alert(
        "ORDER_AT_RISK", severity, f"Order at risk: {o['order_no']}", body,
        "order", o["id"],
        {"order_no": o["order_no"], "customer": o["customer_name"], "risk_score": risk["score"],
         "order_value": o.get("order_value"), "reasons": risk["reasons"]},
        "Expedite picking/allocation or transfer stock", rule_keys,
        event_key=f"ORDER_AT_RISK:{o['id']}",
    )


@router.get("/orders")
def list_orders(status: str = "", priority: str = ""):
    q = "SELECT * FROM orders WHERE 1=1"
    args = []
    if status:
        q += " AND status=?"; args.append(status)
    q += " ORDER BY created_at DESC"
    with db_cursor() as cur:
        cur.execute(q, args)
        orders = [_enrich_order(o) for o in cur.fetchall()]
    if priority:
        orders = [o for o in orders if o["priority"] == priority]
    orders.sort(key=lambda x: -x["priority_score"])
    return orders


@router.get("/orders/{oid}")
def get_order(oid: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id=?", (oid,))
        o = cur.fetchone()
        if not o:
            raise HTTPException(404)
    return _enrich_order(o)


@router.post("/orders")
def create_order(body: OrderIn):
    oid = str(uuid.uuid4())
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as c FROM orders")
        count = cur.fetchone()["c"]
        order_no = f"WO-{1000 + count + 1}"
        total = 0
        # calculate value from items
        item_rows = []
        for it in body.items:
            cur.execute("SELECT * FROM products WHERE id=?", (it.product_id,))
            p = cur.fetchone()
            if not p:
                raise HTTPException(400, f"Product {it.product_id} not found")
            total += it.quantity * p["unit_price"]
            item_rows.append((str(uuid.uuid4()), oid, it.product_id, it.quantity))
        order_value = body.order_value if body.order_value else total
        cur.execute(
            "INSERT INTO orders(id,order_no,customer_name,customer_email,customer_priority,required_by,order_value,status,created_at,priority,priority_score,priority_reasons,risk_score,risk_reasons) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (oid, order_no, body.customer_name, body.customer_email, body.customer_priority, body.required_by,
             order_value, "CREATED", now_iso(), "MEDIUM", 0, "[]", 0, "[]")
        )
        for ir in item_rows:
            cur.execute("INSERT INTO order_items(id,order_id,product_id,quantity,allocated,picked) VALUES(?,?,?,?,0,0)", ir)
    log_activity("order", f"Created order {order_no}", "order", oid)
    audit("CREATE", "order", oid, new=body.model_dump())
    # auto priority + attempt allocation
    with db_cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id=?", (oid,))
        o = cur.fetchone()
    _enrich_order(o)
    result = allocate_inventory(oid)
    if result.get("status") == "PARTIALLY_ALLOCATED":
        shortfalls = [it for it in result.get("items", []) if it.get("short")]
        fully_unfulfillable = all(it.get("allocated_now", 0) == 0 for it in shortfalls) and len(shortfalls) == len(result.get("items", []))
        severity = "CRITICAL" if (body.customer_priority in ("VIP", "HIGH") or fully_unfulfillable) else "HIGH"
        event_type = "CANNOT_FULFILL" if fully_unfulfillable else "PARTIAL_ALLOCATION"
        rule_keys = {"critical_order_risk"}
        if fully_unfulfillable:
            rule_keys.add("cannot_fulfill")
        if (body.order_value or order_value) >= 10000:
            rule_keys.add("high_value_risk")
        short_lines = "\n".join(f"- {s['sku']}: need {s['needed']}, short {s['short']}" for s in shortfalls)
        body_text = (
            f"Order: {order_no}\nCustomer: {body.customer_name}\nPriority: {body.customer_priority}\n"
            f"Order value: ₹{order_value:,.0f}\n\nShortages:\n{short_lines}\n\n"
            f"Reason: Available inventory is insufficient to fully allocate this order."
        )
        create_alert(
            event_type, severity,
            f"{'Cannot fulfill' if fully_unfulfillable else 'Partial allocation'}: {order_no}",
            body_text, "order", oid,
            {"order_no": order_no, "customer": body.customer_name, "shortfalls": shortfalls, "order_value": order_value},
            "Transfer stock from an alternate location or expedite reorder", rule_keys,
            event_key=f"ALLOCATION:{oid}",
        )
    hub.publish("order_updated", {"id": oid})
    return {"id": oid, "order_no": order_no, "allocation": result}



@router.put("/orders/{oid}/customer-email")
def update_customer_email(oid: str, email: str):
    """Set the business contact email for an order. Critical events use this recipient."""
    email = (email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(400, "A valid company email is required")
    with db_cursor() as cur:
        cur.execute("SELECT id FROM orders WHERE id=?", (oid,))
        if not cur.fetchone():
            raise HTTPException(404, "Order not found")
        cur.execute("UPDATE orders SET customer_email=? WHERE id=?", (email, oid))
    hub.publish("order_updated", {"id": oid})
    return {"ok": True, "order_id": oid, "customer_email": email}

@router.post("/orders/{oid}/cancel")
def cancel_order(oid: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id=?", (oid,))
        o = cur.fetchone()
        if not o:
            raise HTTPException(404)
    release_allocation(oid)
    with db_cursor() as cur:
        cur.execute("UPDATE orders SET status='CANCELLED' WHERE id=?", (oid,))
    log_activity("order", f"Cancelled {o['order_no']}", "order", oid)
    hub.publish("order_updated", {"id": oid})
    return {"ok": True}


@router.post("/orders/{oid}/hold")
def hold_order(oid: str):
    with db_cursor() as cur:
        cur.execute("UPDATE orders SET on_hold=1 WHERE id=?", (oid,))
    hub.publish("order_updated", {"id": oid})
    return {"ok": True}


@router.post("/orders/{oid}/resume")
def resume_order(oid: str):
    with db_cursor() as cur:
        cur.execute("UPDATE orders SET on_hold=0 WHERE id=?", (oid,))
    hub.publish("order_updated", {"id": oid})
    return {"ok": True}


@router.post("/orders/{oid}/allocate")
def reallocate(oid: str):
    result = allocate_inventory(oid)
    return result


@router.post("/orders/{oid}/release")
def release(oid: str):
    release_allocation(oid)
    with db_cursor() as cur:
        cur.execute("UPDATE orders SET status='CREATED' WHERE id=?", (oid,))
    hub.publish("order_updated", {"id": oid})
    return {"ok": True}


@router.get("/orders/{oid}/explain")
def explain_order(oid: str):
    """Explain delays/risks + recommend actions."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id=?", (oid,))
        o = cur.fetchone()
    if not o:
        raise HTTPException(404)
    o = _enrich_order(o)
    reasons = []
    recommendations = []
    for it in o["items"]:
        avail = it["product"]["physical_stock"] - it["product"]["reserved_stock"] - it["product"]["damaged_stock"]
        short = it["quantity"] - it["allocated"]
        if short > 0 and avail < short:
            reasons.append(f"{it['sku']} shortage: need {short}, only {avail} usable")
            recommendations.append(f"Transfer/reorder {short - avail} × {it['sku']}")
    if o["status"] in ("CREATED", "PRIORITIZED"):
        reasons.append("Picking not started")
        recommendations.append("Assign picker immediately")
    return {"order": o, "reasons": reasons, "recommendations": recommendations}