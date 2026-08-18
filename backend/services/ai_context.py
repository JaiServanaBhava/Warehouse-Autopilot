"""Compact, live warehouse context for the AI copilot."""
import json
from ..db import db_cursor, get_setting
from ..engines import warehouse_health, business_impact, autopilot_score


def _rows(sql, params=()):
    with db_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def build_warehouse_context(query: str = "") -> dict:
    q = (query or "").strip()
    # Core live metrics: these are calculated by the application, not the LLM.
    health = warehouse_health()
    impact = business_impact()
    autopilot = autopilot_score()

    products = _rows("""
        SELECT id, sku, name, category, supplier, location, physical_stock,
               reserved_stock, damaged_stock, min_stock, safety_stock,
               reorder_level, avg_daily_demand, unit_price
        FROM products ORDER BY sku LIMIT 250
    """)
    orders = _rows("""
        SELECT id, order_no, customer_name, required_by, order_value, status,
               priority, priority_score, priority_reasons, risk_score,
               risk_reasons, on_hold, created_at
        FROM orders WHERE status NOT IN ('DISPATCHED','CANCELLED')
        ORDER BY risk_score DESC, priority_score DESC LIMIT 150
    """)
    order_items = _rows("""
        SELECT oi.order_id, o.order_no, oi.product_id, p.sku, p.name,
               oi.quantity, oi.allocated, oi.picked
        FROM order_items oi
        LEFT JOIN orders o ON o.id=oi.order_id
        LEFT JOIN products p ON p.id=oi.product_id
        ORDER BY o.order_no LIMIT 400
    """)
    exceptions = _rows("""
        SELECT id, type, severity, order_id, product_id, description,
               resolution, status, created_at
        FROM exceptions WHERE status='OPEN'
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
             WHEN 'MEDIUM' THEN 2 ELSE 1 END DESC, created_at DESC LIMIT 100
    """)
    alerts = _rows("""
        SELECT id, type, severity, title, body, entity_type, entity_id,
               recommended_action, status, email_status, whatsapp_status, created_at
        FROM alerts WHERE status='ACTIVE'
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
             WHEN 'MEDIUM' THEN 2 ELSE 1 END DESC, created_at DESC LIMIT 100
    """)
    decisions = _rows("""
        SELECT id, problem, severity, recommendation, reason, confidence,
               impact, alternatives, status, created_at
        FROM decisions WHERE status='PENDING'
        ORDER BY confidence DESC LIMIT 50
    """)
    tasks = _rows("""
        SELECT t.id, t.order_id, o.order_no, t.stage, t.worker_id,
               t.status, t.started_at, t.route
        FROM tasks t LEFT JOIN orders o ON o.id=t.order_id
        WHERE t.status IN ('QUEUED','IN_PROGRESS')
        ORDER BY t.stage, t.status LIMIT 200
    """)
    workers = _rows("""
        SELECT id, name, role, available, workload, efficiency, current_task
        FROM workers ORDER BY workload DESC LIMIT 100
    """)
    activity = _rows("SELECT kind, message, entity_type, entity_id, at FROM activity ORDER BY at DESC LIMIT 30")

    # If the user names a particular SKU/order, add focused records even if they
    # fall outside the compact default lists.
    focused = {}
    if q:
        with db_cursor() as cur:
            like = f"%{q}%"
            cur.execute("SELECT * FROM products WHERE sku LIKE ? OR name LIKE ? LIMIT 20", (like, like))
            focused["matching_products"] = cur.fetchall()
            cur.execute("SELECT * FROM orders WHERE order_no LIKE ? OR customer_name LIKE ? LIMIT 20", (like, like))
            focused["matching_orders"] = cur.fetchall()

    return {
        "warehouse": {
            "name": get_setting("warehouse_name", "Central DC"),
            "company": get_setting("company_name", "Warehouse"),
        },
        "health": health,
        "business_impact": impact,
        "autopilot": autopilot,
        "products": products,
        "orders": orders,
        "order_items": order_items,
        "open_exceptions": exceptions,
        "active_alerts": alerts,
        "pending_decisions": decisions,
        "active_tasks": tasks,
        "workers": workers,
        "recent_activity": activity,
        "focused_matches": focused,
    }
