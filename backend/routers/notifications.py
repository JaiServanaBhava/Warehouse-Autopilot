"""Notification settings, alerts, outbox, and real delivery test endpoints."""
from fastapi import APIRouter, Body, HTTPException, Query
from ..db import get_setting, set_setting, db_cursor, now_iso
from ..services.email import send_email
from ..services.notification import send_whatsapp
from ..services.desktop import send_desktop_notification
from ..services.alert import create_alert, _log_notification
from ..events import hub

router = APIRouter(prefix="", tags=["Notifications & Alerts"])

EMAIL_KEYS = {
    "automatic_email_enabled", "email_recipient", "company_email", "sender_email", "company_name",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "email_rule_critical_shortage", "email_rule_critical_order_risk", "email_rule_oos_order",
    "email_rule_projected_stockout", "email_rule_high_value_risk", "email_rule_major_loss",
    "email_rule_low_stock", "email_rule_startup_digest", "email_rule_demo_reset",
}
WA_KEYS = {
    "automatic_whatsapp_enabled", "whatsapp_number", "twilio_account_sid",
    "twilio_auth_token", "twilio_whatsapp_from", "whatsapp_rule_critical_shortage",
    "whatsapp_rule_cannot_fulfill", "whatsapp_rule_critical_order_risk",
    "whatsapp_rule_high_value_risk", "whatsapp_rule_major_loss", "whatsapp_rule_low_stock",
    "whatsapp_rule_startup_digest", "whatsapp_rule_demo_reset",
}


@router.get("/notifications/settings")
def notification_settings():
    keys = EMAIL_KEYS | WA_KEYS | {"desktop_notifications_enabled", "user_active"}
    data = {k: get_setting(k, "") for k in keys}
    for k in ("smtp_password", "twilio_auth_token"):
        data[k] = "••••••••" if data.get(k) else ""
    return data


@router.put("/notifications/settings/{key}")
def update_notification_setting(key: str, value: str = Body(..., embed=True)):
    allowed = EMAIL_KEYS | WA_KEYS | {"desktop_notifications_enabled", "user_active"}
    if key not in allowed:
        raise HTTPException(400, "Unsupported notification setting")
    set_setting(key, str(value))
    hub.publish("settings", {"key": key, "value": str(value)})
    return {"ok": True, "key": key, "value": str(value)}


@router.get("/notifications/active-email")
def get_active_email():
    return {
        "company_email": get_setting("company_email", "manager@warehouse.com"),
        "email_recipient": get_setting("email_recipient", "manager@warehouse.com"),
    }


@router.put("/notifications/active-email")
def set_active_email(email: str = Body(..., embed=True)):
    email = (email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Please provide a valid email address.")
    set_setting("company_email", email)
    set_setting("email_recipient", email)
    hub.publish("settings", {"key": "company_email", "value": email})
    return {"ok": True, "company_email": email}


@router.post("/notifications/test-email")
async def test_email(recipient: str = Body(None, embed=True), note: str = Body(None, embed=True)):
    target = recipient or get_setting("company_email") or get_setting("email_recipient", "manager@warehouse.com")
    subject = "Warehouse Autopilot — Real-Time Alert Engine Test"
    body_text = (
        f"This is a real-time operational test email from Warehouse Autopilot.\n\n"
        f"Recipient target: {target}\n"
        f"Dispatched at: {now_iso()}\n"
        f"Custom Note: {note or 'Live real-time delivery verified.'}\n\n"
        f"Warehouse Autopilot is actively monitoring inventory, orders, and fulfillment pipelines."
    )
    result = await send_email(
        subject=subject,
        body_text=body_text,
        recipient=target,
        severity="INFO",
        details={"Test Trigger": "Manual / UI Request", "Target Inbox": target, "Timestamp": now_iso()},
        action_text="Delivery verified. No action required.",
    )
    _log_notification(
        alert_id="",
        channel="TEST_EMAIL",
        recipient=target,
        result=result,
        subject=subject,
        body=body_text,
        severity="INFO",
    )
    send_desktop_notification("Test Email Sent", f"Delivered test alert to {target}", "INFO")
    return {**result, "recipient": target}


@router.post("/notifications/test-whatsapp")
async def test_whatsapp(number: str = Body(None, embed=True)):
    target = number or get_setting("whatsapp_number", "+919876543210")
    result = await send_whatsapp(
        f"🚨 Warehouse Autopilot — WhatsApp test dispatch at {now_iso()}. Live real-time delivery verified.",
        target,
    )
    _log_notification(
        alert_id="",
        channel="TEST_WHATSAPP",
        recipient=target,
        result=result,
        subject="WhatsApp Test Dispatch",
        body="WhatsApp test notification",
        severity="INFO",
    )
    send_desktop_notification("Test WhatsApp Sent", f"Delivered WhatsApp test to {target}", "INFO")
    return {**result, "recipient": target}


# =============== ALERTS & OUTBOX ENDPOINTS ===============
@router.get("/alerts")
def list_alerts(status: str = "", severity: str = "", limit: int = 40):
    q = "SELECT * FROM alerts WHERE 1=1"
    args = []
    if status:
        q += " AND status=?"; args.append(status)
    if severity:
        q += " AND severity=?"; args.append(severity)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with db_cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall()


@router.get("/outbox")
def list_outbox(channel: str = "", status: str = "", limit: int = 50):
    q = "SELECT * FROM outbox WHERE 1=1"
    args = []
    if channel:
        q += " AND channel LIKE ?"; args.append(f"%{channel}%")
    if status:
        q += " AND status=?"; args.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with db_cursor() as cur:
        cur.execute(q, args)
        return cur.fetchall()


@router.post("/outbox/{oid}/resend")
async def resend_outbox_item(oid: str):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM outbox WHERE id=?", (oid,))
        item = cur.fetchone()
        if not item:
            raise HTTPException(404, "Outbox item not found")

    if "EMAIL" in item["channel"].upper():
        res = await send_email(item["subject"], item["body"], item["recipient"], severity=item.get("severity", "CRITICAL"))
    else:
        res = await send_whatsapp(item["body"], item["recipient"])

    with db_cursor() as cur:
        cur.execute("UPDATE outbox SET status=?, sent_at=? WHERE id=?", (res["status"], now_iso(), oid))
    hub.publish("notification_updated", {"channel": item["channel"], "status": res["status"]})
    return {"ok": True, "status": res["status"]}


@router.delete("/outbox")
def clear_outbox():
    with db_cursor() as cur:
        cur.execute("DELETE FROM outbox")
    hub.publish("notification_updated", {})
    return {"ok": True}
