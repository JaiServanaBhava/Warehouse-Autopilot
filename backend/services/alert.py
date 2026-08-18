"""Real-time alert engine with multi-channel dispatch (Email, Desktop, WhatsApp).

This module turns warehouse events into:
  severity calculation -> alert record -> channel selection -> real-time dispatch

All alerts are persisted, pushed over SSE immediately, dispatched to configured channels
(Email, Desktop OS toast, WhatsApp), and logged into the outbox.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

from ..db import db_cursor, now_iso, get_setting
from ..events import hub
from . import email as email_service
from . import notification as whatsapp_service
from . import desktop as desktop_service

SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

EMAIL_RULE_KEYS = {
    "critical_shortage", "critical_order_risk", "oos_order",
    "projected_stockout", "high_value_risk", "major_loss", "low_stock",
    "startup_digest", "demo_reset",
}
WHATSAPP_RULE_KEYS = {
    "critical_shortage", "cannot_fulfill", "critical_order_risk",
    "high_value_risk", "major_loss", "low_stock",
    "startup_digest", "demo_reset",
}


def _uid() -> str:
    return str(uuid.uuid4())


def _bool(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


def _rules_enabled(rule_keys: set, prefix: str) -> bool:
    for k in rule_keys:
        setting_key = f"{prefix}_rule_{k}"
        if _bool(get_setting(setting_key, "true")):
            return True
    return False


def _desktop_enabled() -> bool:
    return _bool(get_setting("desktop_notifications_enabled", "true"))


def _user_active() -> bool:
    return _bool(get_setting("user_active", "true"))


def create_alert(
    event_type: str,
    severity: str,
    title: str,
    body: str,
    entity_type: str = "",
    entity_id: str = "",
    meta: dict = None,
    recommended_action: str = "",
    rule_keys: set = None,
    event_key: str = None,
) -> dict:
    """Create or update an alert for a real warehouse event and fan it out."""
    meta = meta or {}
    rule_keys = rule_keys or set()
    event_key = event_key or f"{event_type}:{entity_id}"
    now = now_iso()

    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM alerts WHERE event_key=? AND status='ACTIVE' ORDER BY created_at DESC LIMIT 1",
            (event_key,),
        )
        existing = cur.fetchone()

        materially_changed = True
        if existing:
            old_sev = SEVERITY_RANK.get(existing["severity"], 0)
            new_sev = SEVERITY_RANK.get(severity, 0)
            same_body = (existing["body"] or "") == body
            if new_sev <= old_sev and same_body:
                materially_changed = False

        if existing and not materially_changed:
            cur.execute(
                "UPDATE alerts SET updated_at=? WHERE id=?", (now, existing["id"])
            )
            alert_id = existing["id"]
            alert_row = dict(existing)
            alert_row["updated_at"] = now
            escalate = False
        elif existing:
            alert_id = existing["id"]
            cur.execute(
                """UPDATE alerts SET severity=?, title=?, body=?, meta=?, recommended_action=?,
                   status='ACTIVE', updated_at=?, desktop_status='-', email_status='-', whatsapp_status='-'
                   WHERE id=?""",
                (severity, title, body, json.dumps(meta), recommended_action, now, alert_id),
            )
            cur.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
            alert_row = cur.fetchone()
            escalate = True
        else:
            alert_id = _uid()
            cur.execute(
                """INSERT INTO alerts(id,event_key,type,severity,title,body,entity_type,entity_id,meta,
                   recommended_action,status,desktop_status,email_status,whatsapp_status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (alert_id, event_key, event_type, severity, title, body, entity_type, entity_id,
                 json.dumps(meta), recommended_action, "ACTIVE", "-", "-", "-", now, now),
            )
            cur.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
            alert_row = cur.fetchone()
            escalate = True

    if not escalate:
        return alert_row

    # 1. Desktop Notification in Python
    desktop_status = "-"
    if _desktop_enabled():
        desktop_service.send_desktop_notification(title, body, severity)
        desktop_status = "SENT"

    # 2. Channel rules
    want_email = (severity in ("CRITICAL", "HIGH")) and (_rules_enabled(rule_keys, "email") or not rule_keys)
    # WhatsApp is strictly limited to top-priority critical events
    want_whatsapp = (severity == "CRITICAL" or event_type in ("CANNOT_FULFILL", "OUT_OF_STOCK", "MAJOR_BUSINESS_LOSS", "SYSTEM_STARTUP", "DEMO_RESET")) and _rules_enabled(rule_keys, "whatsapp")

    with db_cursor() as cur:
        cur.execute("UPDATE alerts SET desktop_status=? WHERE id=?", (desktop_status, alert_id))

    # Push to SSE hub for instant live UI feedback
    alert_payload = {
        "id": alert_id, "type": event_type, "severity": severity, "title": title,
        "body": body, "entity_type": entity_type, "entity_id": entity_id,
        "meta": meta, "recommended_action": recommended_action, "created_at": now,
    }
    hub.publish("alert", alert_payload)
    if severity in ("HIGH", "CRITICAL"):
        hub.publish("critical_alert", alert_payload)

    # 3. Email Dispatch
    if want_email:
        _dispatch_background(_send_business_email_and_log(
            alert_id, title, body, severity, entity_type, entity_id, meta, event_type, recommended_action
        ))
    else:
        _mark_channel(alert_id, "email_status", "-")

    # 4. WhatsApp Dispatch (Twilio / Simulator)
    if want_whatsapp:
        wa_body = _format_whatsapp(title, body, severity, recommended_action)
        _dispatch_background(_send_whatsapp_and_log(alert_id, wa_body, severity))
    else:
        _mark_channel(alert_id, "whatsapp_status", "-")

    with db_cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE id=?", (alert_id,))
        alert_row = cur.fetchone()
    return alert_row


def _dispatch_background(coro):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        asyncio.run(coro)


def _mark_channel(alert_id: str, column: str, value: str):
    with db_cursor() as cur:
        cur.execute(f"UPDATE alerts SET {column}=? WHERE id=?", (value, alert_id))


async def _send_business_email_and_log(
    alert_id: str, title: str, body: str, severity: str,
    entity_type: str, entity_id: str, meta: dict, event_type: str,
    recommended_action: str = "",
):
    """Automatically contact companies and warehouse management regarding the event."""
    recipients = []
    orders = []

    with db_cursor() as cur:
        if entity_type == "order" and entity_id:
            cur.execute("SELECT * FROM orders WHERE id=?", (entity_id,))
            row = cur.fetchone()
            if row:
                orders = [row]
        elif entity_type == "product" and entity_id:
            cur.execute("""SELECT DISTINCT o.* FROM orders o
                           JOIN order_items oi ON oi.order_id=o.id
                           WHERE oi.product_id=? AND o.status NOT IN ('DISPATCHED','CANCELLED')""", (entity_id,))
            orders = cur.fetchall()
        elif entity_type == "exception" and entity_id:
            cur.execute("""SELECT o.* FROM exceptions e JOIN orders o ON o.id=e.order_id
                           WHERE e.id=?""", (entity_id,))
            row = cur.fetchone()
            if row:
                orders = [row]

    # Gather customer emails from affected orders
    for order in orders:
        email = (order.get("customer_email") or "").strip()
        if email and email not in {r[1] for r in recipients}:
            recipients.append((order, email))

    # Always include the company/operations manager email
    manager_email = get_setting("company_email") or get_setting("email_recipient") or "manager@warehouse.com"
    if manager_email and manager_email not in {r[1] for r in recipients}:
        recipients.append(({"order_no": "SYSTEM", "customer_name": "Operations Team"}, manager_email))

    if not recipients:
        result = {"status": "DISABLED", "error": "No company or manager email configured"}
        _log_notification(alert_id, "BUSINESS_EMAIL", "", result, subject=title, body=body, severity=severity)
        _mark_channel(alert_id, "email_status", result["status"])
        hub.publish("notification_updated", {"alert_id": alert_id, "channel": "BUSINESS_EMAIL", "status": result["status"]})
        return

    statuses = []
    for order, recipient in recipients:
        order_no = order.get("order_no", "SYSTEM")
        company = order.get("customer_name", "Warehouse Management")
        subject = f"🚨 URGENT [{severity}] — {title}"
        action = recommended_action or "Our operations team is actively working to resolve this issue."
        email_body = (
            f"Dear {company} Team,\n\n"
            f"This is an automated real-time notification regarding warehouse operations.\n\n"
            f"ALERT SUMMARY\n{title}\n\n"
            f"DETAILS\n{body}\n\n"
            f"RECOMMENDED ACTION\n{action}\n\n"
            f"Regards,\nWarehouse Autopilot Operations Hub"
        )
        details = {
            "Alert Level": severity,
            "Reference": order_no,
            "Event Type": event_type,
            "Timestamp": now_iso(),
        }
        if meta and isinstance(meta, dict):
            for k in ("sku", "shortage", "usable_stock", "order_value"):
                if k in meta:
                    details[k.replace("_", " ").title()] = meta[k]

        result = await email_service.send_email(
            subject=subject,
            body_text=email_body,
            recipient=recipient,
            severity=severity,
            details=details,
            action_text=action,
        )
        statuses.append(result["status"])
        _log_notification(alert_id, "BUSINESS_EMAIL", recipient, result, subject=subject, body=email_body, severity=severity)

    final_status = "SENT" if any(x == "SENT" for x in statuses) else (statuses[0] if statuses else "FAILED")
    _mark_channel(alert_id, "email_status", final_status)
    hub.publish("notification_updated", {"alert_id": alert_id, "channel": "BUSINESS_EMAIL", "status": final_status, "recipients": len(recipients)})


async def _send_whatsapp_and_log(alert_id: str, body: str, severity: str = "CRITICAL"):
    recipient = get_setting("whatsapp_number") or "+919876543210"
    result = await whatsapp_service.send_whatsapp(body, recipient)
    _log_notification(alert_id, "WHATSAPP", recipient, result, subject=f"WhatsApp {severity}", body=body, severity=severity)
    _mark_channel(alert_id, "whatsapp_status", result["status"])
    hub.publish("notification_updated", {"alert_id": alert_id, "channel": "WHATSAPP", "status": result["status"]})


def _log_notification(alert_id: str, channel: str, recipient: str, result: dict, subject: str = "", body: str = "", severity: str = ""):
    sent_at = now_iso() if result.get("status") == "SENT" else None
    outbox_id = _uid()
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO outbox(id,alert_id,channel,recipient,subject,body,severity,status,
               provider_message_id,error_message,created_at,sent_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (outbox_id, alert_id or "", channel, recipient or "", subject or "", body or "", severity or "", result["status"],
             result.get("provider_message_id"), result.get("error"), now_iso(), sent_at),
        )
    # Broadcast outbox item over SSE for immediate live outbox list refresh
    hub.publish("outbox_created", {
        "id": outbox_id,
        "channel": channel,
        "recipient": recipient,
        "subject": subject,
        "status": result["status"],
        "severity": severity,
        "created_at": now_iso(),
    })


def _format_whatsapp(title: str, body: str, severity: str, action: str = "") -> str:
    company = get_setting("company_name", "Warehouse")
    lines = [
        f"🚨 *WAREHOUSE ALERT — {severity}*",
        f"Facility: {company}",
        "",
        f"*{title}*",
        body[:300] + ("..." if len(body) > 300 else ""),
    ]
    if action:
        lines.extend(["", f"👉 *Action:* {action}"])
    return "\n".join(lines)


def resolve_alert(event_key: str, resolution: str = "Situation resolved"):
    """Mark an ACTIVE alert as resolved."""
    now = now_iso()
    with db_cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE event_key=? AND status='ACTIVE'", (event_key,))
        rows = cur.fetchall()
        for r in rows:
            cur.execute(
                "UPDATE alerts SET status='RESOLVED', resolved_at=?, updated_at=? WHERE id=?",
                (now, now, r["id"]),
            )
    if rows:
        hub.publish("alert_resolved", {"event_key": event_key})


def send_supplier_reorder_email(sku: str, product_name: str, supplier: str, quantity: int, reason: str = ""):
    """Dispatches automated Purchase Order email to supplier / procurement contact."""
    if not _bool(get_setting("auto_reorder_email_enabled", "true")):
        return None
    recipient = get_setting("supplier_po_recipient") or "supplier-orders@logistics-hub.com"
    subject = f"📦 AUTOMATED PURCHASE ORDER: Urgent Restock for {sku} ({quantity} units)"
    body = (
        f"Dear {supplier} Procurement Team,\n\n"
        f"This is an automated purchase order issued by Warehouse Autopilot.\n\n"
        f"ORDER SPECIFICATIONS:\n"
        f"• Product: {product_name}\n"
        f"• SKU: {sku}\n"
        f"• Quantity Required: {quantity} units\n"
        f"• Urgency: IMMEDIATE RESTOCK\n"
        f"• Reason: {reason or 'Stock level breached critical minimum threshold.'}\n"
        f"• Destination: Central DC Warehouse — Inbound Receiving Bay 2\n\n"
        f"Please confirm receipt and estimated delivery ETA immediately.\n\n"
        f"Regards,\nWarehouse Autopilot Automated Order Service"
    )
    details = {
        "Document": "Automated Purchase Order (PO)",
        "Supplier": supplier,
        "SKU": sku,
        "Product Name": product_name,
        "Order Quantity": f"{quantity} units",
        "Trigger": "Low/Critical Stock Auto-Service",
        "PO Target Inbox": recipient,
    }
    action = "Awaiting supplier fulfillment confirmation and delivery tracking."

    # Dispatch in background
    async def _send_po():
        res = await email_service.send_email(
            subject=subject,
            body_text=body,
            recipient=recipient,
            severity="HIGH",
            details=details,
            action_text=action,
        )
        _log_notification(
            alert_id="",
            channel="SUPPLIER_PO_EMAIL",
            recipient=recipient,
            result=res,
            subject=subject,
            body=body,
            severity="HIGH",
        )
    _dispatch_background(_send_po())


def send_system_digest_email(title: str, summary: str, is_reset: bool = False, recipient: str = None):
    """Generates and dispatches a comprehensive operational digest email in real-time."""
    recipient = recipient or get_setting("company_email") or get_setting("email_recipient") or "manager@warehouse.com"
    event_type = "DEMO_RESET" if is_reset else "SYSTEM_STARTUP"

    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as c FROM products WHERE physical_stock=0")
        oos_count = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM exceptions WHERE status='OPEN'")
        open_exc = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM orders WHERE status NOT IN ('DISPATCHED','CANCELLED')")
        open_orders = cur.fetchone()["c"]
        cur.execute("SELECT * FROM products WHERE physical_stock=0 LIMIT 1")
        oos_sample = cur.fetchone()

    details = {
        "Status": "ONLINE & MONITORING",
        "Out of Stock SKUs": f"{oos_count} product(s)",
        "Active Exceptions": f"{open_exc} open issue(s)",
        "Pending Orders": f"{open_orders} orders in fulfillment pipeline",
        "Triggered By": "Demo Reset Request" if is_reset else "System Startup Lifecycle",
        "Recipient": recipient,
    }

    body = (
        f"{summary}\n\n"
        f"Live System Snapshot:\n"
        f"• Out-of-Stock Products: {oos_count}\n"
        f"• Active Exceptions: {open_exc}\n"
        f"• Active Orders: {open_orders}\n\n"
        f"All autonomous autopilot safety rules and real-time monitoring are active."
    )

    action = "Review pending Autopilot decisions and verify high-priority order allocations."

    # Create alert record
    alert_row = create_alert(
        event_type=event_type,
        severity="CRITICAL" if (oos_count > 0 or open_exc > 0) else "INFO",
        title=title,
        body=body,
        entity_type="system",
        entity_id="global",
        meta=details,
        recommended_action=action,
        rule_keys={"startup_digest" if not is_reset else "demo_reset"},
        event_key=f"{event_type}:{now_iso()[:13]}",
    )

    # Automatically trigger supplier reorder PO email for out-of-stock product
    if oos_sample:
        send_supplier_reorder_email(
            sku=oos_sample["sku"],
            product_name=oos_sample["name"],
            supplier=oos_sample["supplier"],
            quantity=30,
            reason=f"Automatic reorder on {event_type} — Stock is at 0 units",
        )

    return alert_row
