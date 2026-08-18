"""Products & inventory routes."""
from fastapi import APIRouter, HTTPException
from ..db import db_cursor, now_iso
from ..schemas import ProductIn, ProductUpdate, StockOp
from ..engines import (
    compute_available, stock_status, days_until_stockout,
    recommended_reorder, forecast_product, log_activity, audit
)
from ..services.alert import create_alert, resolve_alert
from ..events import hub
import uuid, json

router = APIRouter()


def _enrich(p: dict) -> dict:
    p = dict(p)
    p["available_stock"] = compute_available(p)
    p["status"] = stock_status(p)
    p["days_until_stockout"] = days_until_stockout(p)
    p["recommended_reorder"] = recommended_reorder(p)
    return p


@router.get("/products")
def list_products(search: str = "", category: str = "", status: str = ""):
    q = "SELECT * FROM products WHERE 1=1"
    args = []
    if search:
        q += " AND (sku LIKE ? OR name LIKE ?)"
        args += [f"%{search}%", f"%{search}%"]
    if category:
        q += " AND category=?"
        args.append(category)
    q += " ORDER BY name"
    with db_cursor() as cur:
        cur.execute(q, args)
        products = [_enrich(p) for p in cur.fetchall()]
    if status:
        products = [p for p in products if p["status"] == status]
    return products


@router.post("/products")
def create_product(body: ProductIn):
    pid = str(uuid.uuid4())
    with db_cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO products(id,sku,name,category,supplier,location,physical_stock,reserved_stock,damaged_stock,min_stock,safety_stock,reorder_level,avg_daily_demand,unit_price,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, body.sku, body.name, body.category, body.supplier, body.location,
                 body.physical_stock, 0, 0, body.min_stock, body.safety_stock, body.reorder_level,
                 body.avg_daily_demand, body.unit_price, now_iso())
            )
        except Exception as e:
            raise HTTPException(400, str(e))
    log_activity("product", f"Created product {body.sku}", "product", pid)
    audit("CREATE", "product", pid, new=body.model_dump())
    hub.publish("inventory_updated", {})
    return {"id": pid}


@router.put("/products/{pid}")
def update_product(pid: str, body: ProductUpdate):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (pid,))
        old = cur.fetchone()
        if not old:
            raise HTTPException(404, "Not found")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            sets = ", ".join(f"{k}=?" for k in updates)
            cur.execute(f"UPDATE products SET {sets} WHERE id=?", list(updates.values()) + [pid])
    audit("UPDATE", "product", pid, old=old, new=updates)
    log_activity("product", f"Updated product {old['sku']}", "product", pid)
    hub.publish("inventory_updated", {})
    return {"ok": True}


@router.delete("/products/{pid}")
def delete_product(pid: str):
    with db_cursor() as cur:
        cur.execute("DELETE FROM products WHERE id=?", (pid,))
    log_activity("product", "Product deleted", "product", pid)
    hub.publish("inventory_updated", {})
    return {"ok": True}


@router.get("/products/{pid}")
def get_product(pid: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (pid,))
        p = cur.fetchone()
        if not p:
            raise HTTPException(404)
        cur.execute("SELECT * FROM inventory_history WHERE product_id=? ORDER BY at DESC LIMIT 25", (pid,))
        history = cur.fetchall()
    return {"product": _enrich(p), "forecast": forecast_product(p), "history": history}


def _record_history(product_id, type_, delta, reason, location=None):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO inventory_history(id,product_id,type,delta,reason,location,at) VALUES(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), product_id, type_, delta, reason, location, now_iso())
        )


def _affected_orders(product_id: str, needed_total: int):
    """Open orders that still need this product, most urgent first."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT o.id, o.order_no, o.priority, o.order_value, oi.quantity, oi.allocated
               FROM order_items oi JOIN orders o ON o.id = oi.order_id
               WHERE oi.product_id=? AND o.status NOT IN ('DISPATCHED','CANCELLED')
                 AND oi.quantity > oi.allocated
               ORDER BY o.priority_score DESC""",
            (product_id,),
        )
        rows = cur.fetchall()
    return rows


def _alternate_location(product_id: str, p: dict):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM products WHERE category=? AND id!=? AND physical_stock>0 ORDER BY physical_stock DESC LIMIT 1",
            (p["category"], product_id),
        )
        alt = cur.fetchone()
    return alt


def _check_alerts(product_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (product_id,))
        p = cur.fetchone()
    if not p:
        return
    p = _enrich(p)
    status = p["status"]

    if status == "NORMAL":
        # situation recovered — auto-resolve any active shortage alerts for this SKU
        resolve_alert(f"OUT_OF_STOCK:{product_id}")
        resolve_alert(f"CRITICAL_STOCK:{product_id}")
        return

    affected = _affected_orders(product_id, p["available_stock"])
    needed_total = sum(max(0, r["quantity"] - r["allocated"]) for r in affected)
    order_nos = [r["order_no"] for r in affected[:5]]
    at_risk_value = sum((r["order_value"] or 0) for r in affected)
    critical_order = any(r["priority"] == "CRITICAL" for r in affected)
    high_value = at_risk_value >= 10000

    alt = _alternate_location(product_id, p)
    if alt:
        transfer_qty = min(alt["physical_stock"], max(1, needed_total - p["available_stock"]))
        recommended_action = f"Transfer {transfer_qty} units from {alt['location']} ({alt['sku']})"
    else:
        recommended_action = f"Reorder {p['recommended_reorder']} units from {p['supplier']}"

    meta = {
        "sku": p["sku"], "product_name": p["name"],
        "usable_stock": p["available_stock"], "required": needed_total,
        "shortage": max(0, needed_total - p["available_stock"]),
        "affected_orders": order_nos, "estimated_impact": at_risk_value,
        "recommended_reorder": p["recommended_reorder"],
    }

    if status == "OUT_OF_STOCK":
        severity = "CRITICAL" if (affected and critical_order) else ("HIGH" if affected else "CRITICAL")
        rule_keys = {"critical_shortage", "oos_order"}
        if high_value:
            rule_keys.add("high_value_risk")
        title = f"Out of stock: {p['sku']}"
        body = (
            f"Product: {p['name']}\nSKU: {p['sku']}\nUsable stock: {p['available_stock']}\n"
            f"Required (open orders): {needed_total}\nShortage: {meta['shortage']}\n"
            f"Affected Orders: {', '.join(order_nos) or 'None yet'}\n"
            f"Priority: {severity}\nEstimated Business Impact: ₹{at_risk_value:,.0f}\n"
            f"Recommended Action: {recommended_action}\n"
            f"Reason: Available inventory is insufficient to fulfill pending orders."
        )
        create_alert("OUT_OF_STOCK", severity, title, body, "product", product_id,
                     meta, recommended_action, rule_keys, event_key=f"OUT_OF_STOCK:{product_id}")
        from ..services.alert import send_supplier_reorder_email
        send_supplier_reorder_email(p["sku"], p["name"], p["supplier"], max(25, p["recommended_reorder"]), f"Stock is 0 units at {p['location']}")

    elif status == "CRITICAL":
        severity = "CRITICAL" if (affected and critical_order) else "HIGH"
        rule_keys = {"critical_shortage"}
        if high_value:
            rule_keys.add("high_value_risk")
        title = f"Critical stock: {p['sku']}"
        body = (
            f"Product: {p['name']}\nSKU: {p['sku']}\nUsable stock: {p['available_stock']}\n"
            f"Required (open orders): {needed_total}\nShortage: {meta['shortage']}\n"
            f"Affected Orders: {', '.join(order_nos) or 'None yet'}\n"
            f"Priority: {severity}\nEstimated Business Impact: ₹{at_risk_value:,.0f}\n"
            f"Recommended Action: {recommended_action}"
        )
        create_alert("CRITICAL_STOCK", severity, title, body, "product", product_id,
                     meta, recommended_action, rule_keys, event_key=f"CRITICAL_STOCK:{product_id}")
        from ..services.alert import send_supplier_reorder_email
        send_supplier_reorder_email(p["sku"], p["name"], p["supplier"], max(20, p["recommended_reorder"]), f"Stock breached critical minimum ({p['available_stock']} units left)")

    elif status == "LOW":
        title = f"Low stock: {p['sku']}"
        body = f"{p['available_stock']} usable units left of {p['name']}. Consider reordering {p['recommended_reorder']}."
        create_alert("LOW_STOCK", "LOW", title, body, "product", product_id,
                     meta, f"Reorder {p['recommended_reorder']} units", {"low_stock"},
                     event_key=f"LOW_STOCK:{product_id}")
        from ..services.alert import send_supplier_reorder_email
        send_supplier_reorder_email(p["sku"], p["name"], p["supplier"], p["recommended_reorder"], f"Low stock alert ({p['available_stock']} units remaining)")

    # projected stockout — forward-looking, separate from the current-state alerts above
    forecast = forecast_product(p)
    if forecast["days_until_stockout"] <= 2 and p["avg_daily_demand"] > 0 and status != "OUT_OF_STOCK":
        create_alert(
            "PROJECTED_STOCKOUT", "MEDIUM" if forecast["days_until_stockout"] > 0.5 else "HIGH",
            f"Projected stockout: {p['sku']}",
            f"{p['name']} will run out in ~{forecast['days_until_stockout']} days at current demand. "
            f"Recommended reorder: {forecast['recommended_reorder']}.",
            "product", product_id, meta, f"Reorder {forecast['recommended_reorder']} units",
            {"projected_stockout"}, event_key=f"PROJECTED_STOCKOUT:{product_id}",
        )
    else:
        resolve_alert(f"PROJECTED_STOCKOUT:{product_id}")


@router.post("/inventory/receive")
def receive_stock(op: StockOp):
    if op.quantity <= 0:
        raise HTTPException(400, "Quantity must be positive")
    with db_cursor() as cur:
        cur.execute("UPDATE products SET physical_stock=physical_stock+? WHERE id=?", (op.quantity, op.product_id))
    _record_history(op.product_id, "RECEIVE", op.quantity, op.reason or "Stock received")
    log_activity("inventory", f"Received {op.quantity} units", "product", op.product_id)
    mark_qr_stale(op.product_id)
    hub.publish("inventory_updated", {"product_id": op.product_id})
    _check_alerts(op.product_id)
    return {"ok": True}


@router.post("/inventory/remove")
def remove_stock(op: StockOp):
    if op.quantity <= 0:
        raise HTTPException(400, "Quantity must be positive")
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (op.product_id,))
        p = cur.fetchone()
        if not p:
            raise HTTPException(404)
        available = compute_available(p)
        if op.quantity > available:
            raise HTTPException(400, f"Cannot remove {op.quantity}; only {available} usable")
        cur.execute("UPDATE products SET physical_stock=physical_stock-? WHERE id=?", (op.quantity, op.product_id))
    _record_history(op.product_id, "REMOVE", -op.quantity, op.reason or "Stock removed")
    log_activity("inventory", f"Removed {op.quantity} units of {p['sku']}", "product", op.product_id)
    mark_qr_stale(op.product_id)
    hub.publish("inventory_updated", {"product_id": op.product_id})
    _check_alerts(op.product_id)
    return {"ok": True}


@router.post("/inventory/damage")
def mark_damaged(op: StockOp):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (op.product_id,))
        p = cur.fetchone()
        if not p or compute_available(p) < op.quantity:
            raise HTTPException(400, "Not enough usable stock")
        cur.execute("UPDATE products SET damaged_stock=damaged_stock+? WHERE id=?", (op.quantity, op.product_id))
    _record_history(op.product_id, "DAMAGE", op.quantity, op.reason or "Marked damaged")
    log_activity("inventory", f"Marked {op.quantity} damaged", "product", op.product_id)
    mark_qr_stale(op.product_id)
    hub.publish("inventory_updated", {})
    _check_alerts(op.product_id)
    return {"ok": True}


@router.post("/inventory/adjust")
def adjust_stock(op: StockOp):
    """Set physical stock to specified quantity."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (op.product_id,))
        p = cur.fetchone()
        if not p:
            raise HTTPException(404)
        delta = op.quantity - p["physical_stock"]
        cur.execute("UPDATE products SET physical_stock=? WHERE id=?", (op.quantity, op.product_id))
    _record_history(op.product_id, "ADJUST", delta, op.reason or "Adjustment")
    log_activity("inventory", f"Adjusted stock by {delta}", "product", op.product_id)
    mark_qr_stale(op.product_id)
    hub.publish("inventory_updated", {})
    _check_alerts(op.product_id)
    return {"ok": True}


@router.post("/inventory/transfer")
def transfer_stock(op: StockOp):
    if not op.location:
        raise HTTPException(400, "New location required")
    with db_cursor() as cur:
        cur.execute("UPDATE products SET location=? WHERE id=?", (op.location, op.product_id))
    _record_history(op.product_id, "TRANSFER", 0, f"Moved to {op.location}", op.location)
    log_activity("inventory", f"Transferred to {op.location}", "product", op.product_id)
    mark_qr_stale(op.product_id)
    hub.publish("inventory_updated", {})
    return {"ok": True}


@router.get("/inventory/alternate/{pid}")
def alternate_locations(pid: str):
    """Find other products with the same SKU root or category/higher stock as alternates."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (pid,))
        p = cur.fetchone()
        if not p:
            raise HTTPException(404)
        cur.execute("SELECT * FROM products WHERE category=? AND id!=? ORDER BY physical_stock DESC LIMIT 5",
                    (p["category"], pid))
        alts = [_enrich(r) for r in cur.fetchall()]
    return {"product": _enrich(p), "alternates": alts}


# =========================================================================
# QR INTELLIGENCE PASSPORT ROUTES
# =========================================================================
from ..services.qr_passport import (
    get_or_create_qr_passport, regenerate_qr_passport,
    verify_qr_passport, mark_qr_stale
)
from pydantic import BaseModel
from typing import Optional


class QRVerifyIn(BaseModel):
    payload: Optional[str] = None
    product_id: Optional[str] = None
    scanned_usable: Optional[int] = None
    scanned_version: Optional[int] = None


@router.get("/products/{pid}/qr-passport")
def get_qr_passport(pid: str):
    """Fetch or initialize QR Intelligence Passport snapshot."""
    passport = get_or_create_qr_passport(pid)
    if not passport:
        raise HTTPException(404, "Product not found")
    return passport


@router.post("/products/{pid}/qr-passport/regenerate")
def regenerate_qr(pid: str):
    """Regenerate QR Intelligence Passport snapshot and increment version."""
    passport = regenerate_qr_passport(pid)
    if not passport:
        raise HTTPException(404, "Product not found")
    return passport


@router.post("/products/qr-passport/verify")
def verify_qr(body: QRVerifyIn):
    """Verify scanned QR snapshot data against live warehouse state."""
    result = verify_qr_passport(
        payload_text=body.payload or "",
        product_id=body.product_id,
        scanned_usable=body.scanned_usable,
        scanned_version=body.scanned_version
    )
    return result