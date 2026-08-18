"""Product QR Intelligence Passport Service.
Generates dynamic, human-readable operational snapshots for physical warehouse scanning,
maintains snapshot versions, verifies reality vs snapshot, and tracks stale state.
"""
import io
import base64
import re
from datetime import datetime, timezone
import qrcode
from PIL import Image

from ..db import db_cursor, now_iso
from ..engines import (
    compute_available, stock_status, days_until_stockout,
    recommended_reorder, log_activity
)
from ..events import hub


ACTION_MESSAGES = {
    "NORMAL": "STATUS: NORMAL | ACTION: NONE",
    "LOW": "STATUS: LOW | ACTION: MONITOR / REPLENISH",
    "CRITICAL": "STATUS: CRITICAL | ACTION: PRIORITY REPLENISHMENT",
    "OUT_OF_STOCK": "STATUS: OUT OF STOCK | ACTION: REPLENISH IMMEDIATELY",
    "DAMAGED": "STATUS: DAMAGED | ACTION: DO NOT ALLOCATE",
}


def get_action_message(status: str, p: dict) -> str:
    if p.get("damaged_stock", 0) > 0 and p.get("physical_stock", 0) == p.get("damaged_stock", 0):
        return ACTION_MESSAGES["DAMAGED"]
    return ACTION_MESSAGES.get(status, f"STATUS: {status} | ACTION: PROCEED WITH CAUTION")


def generate_qr_base64(payload_text: str) -> str:
    """Generates high-contrast, scannable PNG QR code encoded as base64 data URI."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"


def build_passport_payload(p: dict, version: int, generated_at: str) -> tuple[str, str, int, str]:
    """Builds clean, human-readable plaintext snapshot payload for normal phone cameras."""
    usable = compute_available(p)
    status = stock_status(p)
    runway_days = days_until_stockout(p)
    runway_str = f"{runway_days:.1f} DAYS" if isinstance(runway_days, (int, float)) and runway_days < 999 else "STABLE"
    action = get_action_message(status, p)
    
    lines = [
        "WAREHOUSE PRODUCT PASSPORT",
        f"SKU: {p.get('sku', 'UNKNOWN')}",
        f"PRODUCT: {p.get('name', 'UNKNOWN')}",
        f"LOCATION: {p.get('location', 'UNASSIGNED')}",
        f"STATUS: {status}",
        f"PHYSICAL: {p.get('physical_stock', 0)}",
        f"RESERVED: {p.get('reserved_stock', 0)}",
        f"DAMAGED: {p.get('damaged_stock', 0)}",
        f"USABLE: {usable}",
        f"RUNWAY: {runway_str}",
        f"ACTION: {action.split('| ACTION: ')[-1] if '| ACTION: ' in action else action}",
        f"SNAPSHOT_VERSION: {version}",
        f"GENERATED: {generated_at[:19]}Z",
    ]
    payload_text = "\n".join(lines)
    return payload_text, status, usable, action


def get_or_create_qr_passport(product_id: str) -> dict:
    """Retrieves existing QR passport snapshot or initializes version 1."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (product_id,))
        p = cur.fetchone()
        if not p:
            return None
        
        cur.execute("SELECT * FROM product_qr_snapshots WHERE product_id=?", (product_id,))
        snap = cur.fetchone()
        
        live_usable = compute_available(p)
        live_status = stock_status(p)
        live_action = get_action_message(live_status, p)
        
        if not snap:
            # Create first snapshot
            gen_time = now_iso()
            version = 1
            payload, status, usable, action = build_passport_payload(p, version, gen_time)
            cur.execute(
                """INSERT INTO product_qr_snapshots(
                    product_id, snapshot_version, generated_at, snapshot_payload,
                    snapshot_usable_stock, snapshot_status, snapshot_location,
                    snapshot_action, is_stale
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (product_id, version, gen_time, payload, usable, status, p.get("location", ""), action)
            )
            qr_image = generate_qr_base64(payload)
            return {
                "product_id": product_id,
                "sku": p["sku"],
                "name": p["name"],
                "category": p["category"],
                "supplier": p["supplier"],
                "location": p["location"],
                "snapshot_version": version,
                "generated_at": gen_time,
                "snapshot_payload": payload,
                "snapshot_usable_stock": usable,
                "snapshot_status": status,
                "snapshot_action": action,
                "is_stale": False,
                "qr_image_url": qr_image,
                "live_state": {
                    "usable_stock": live_usable,
                    "status": live_status,
                    "physical_stock": p["physical_stock"],
                    "reserved_stock": p["reserved_stock"],
                    "damaged_stock": p["damaged_stock"],
                    "location": p["location"],
                    "action": live_action,
                }
            }
        else:
            # Check if live state matches snapshot
            is_stale = bool(
                snap["is_stale"] or
                snap["snapshot_usable_stock"] != live_usable or
                snap["snapshot_status"] != live_status or
                snap["snapshot_location"] != p["location"]
            )
            qr_image = generate_qr_base64(snap["snapshot_payload"])
            return {
                "product_id": product_id,
                "sku": p["sku"],
                "name": p["name"],
                "category": p["category"],
                "supplier": p["supplier"],
                "location": p["location"],
                "snapshot_version": snap["snapshot_version"],
                "generated_at": snap["generated_at"],
                "snapshot_payload": snap["snapshot_payload"],
                "snapshot_usable_stock": snap["snapshot_usable_stock"],
                "snapshot_status": snap["snapshot_status"],
                "snapshot_action": snap["snapshot_action"],
                "is_stale": is_stale,
                "qr_image_url": qr_image,
                "live_state": {
                    "usable_stock": live_usable,
                    "status": live_status,
                    "physical_stock": p["physical_stock"],
                    "reserved_stock": p["reserved_stock"],
                    "damaged_stock": p["damaged_stock"],
                    "location": p["location"],
                    "action": live_action,
                }
            }


def regenerate_qr_passport(product_id: str) -> dict:
    """Regenerates QR passport, increments snapshot version, updates payload, and resets stale flag."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id=?", (product_id,))
        p = cur.fetchone()
        if not p:
            return None
        
        cur.execute("SELECT snapshot_version FROM product_qr_snapshots WHERE product_id=?", (product_id,))
        existing = cur.fetchone()
        new_version = (existing["snapshot_version"] + 1) if existing else 1
        
        gen_time = now_iso()
        payload, status, usable, action = build_passport_payload(p, new_version, gen_time)
        
        cur.execute(
            """INSERT OR REPLACE INTO product_qr_snapshots(
                product_id, snapshot_version, generated_at, snapshot_payload,
                snapshot_usable_stock, snapshot_status, snapshot_location,
                snapshot_action, is_stale
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (product_id, new_version, gen_time, payload, usable, status, p.get("location", ""), action)
        )
        
    log_activity("product", f"Regenerated QR Passport v{new_version} for {p['sku']}", "product", product_id)
    hub.publish("inventory_updated", {"product_id": product_id, "qr_version": new_version})
    
    qr_image = generate_qr_base64(payload)
    live_usable = compute_available(p)
    live_status = stock_status(p)
    return {
        "product_id": product_id,
        "sku": p["sku"],
        "name": p["name"],
        "snapshot_version": new_version,
        "generated_at": gen_time,
        "snapshot_payload": payload,
        "snapshot_usable_stock": usable,
        "snapshot_status": status,
        "snapshot_action": action,
        "is_stale": False,
        "qr_image_url": qr_image,
        "live_state": {
            "usable_stock": live_usable,
            "status": live_status,
            "location": p["location"],
        }
    }


def verify_qr_passport(payload_text: str = "", product_id: str = None, scanned_usable: int = None, scanned_version: int = None) -> dict:
    """Verifies scanned QR snapshot data against live warehouse state and reports discrepancies."""
    extracted = {}
    if payload_text:
        # Parse plaintext fields
        for line in payload_text.strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                extracted[key.strip().upper()] = val.strip()
    
    sku = extracted.get("SKU")
    scanned_usable = int(extracted.get("USABLE", scanned_usable if scanned_usable is not None else 0)) if (extracted.get("USABLE") or scanned_usable is not None) else None
    scanned_version = int(extracted.get("SNAPSHOT_VERSION", scanned_version if scanned_version is not None else 1)) if (extracted.get("SNAPSHOT_VERSION") or scanned_version is not None) else 1
    scanned_status = extracted.get("STATUS", "")
    scanned_location = extracted.get("LOCATION", "")
    scanned_generated = extracted.get("GENERATED", "")

    with db_cursor() as cur:
        if product_id:
            cur.execute("SELECT * FROM products WHERE id=?", (product_id,))
        elif sku:
            cur.execute("SELECT * FROM products WHERE sku=?", (sku,))
        else:
            return {"valid": False, "error": "No SKU or Product ID provided in snapshot payload."}
        
        p = cur.fetchone()
        if not p:
            return {
                "valid": False,
                "error": f"Product with SKU '{sku or product_id}' does not exist or was removed."
            }
        
        live_usable = compute_available(p)
        live_status = stock_status(p)
        live_loc = p.get("location", "")
        
        diff_usable = (scanned_usable - live_usable) if scanned_usable is not None else 0
        diff_status = scanned_status and scanned_status != live_status
        diff_loc = scanned_location and scanned_location != live_loc
        
        is_match = (diff_usable == 0 and not diff_status and not diff_loc)
        
        if is_match:
            verdict = "MATCH"
            message = "✓ QR snapshot matches live warehouse state."
        else:
            verdict = "OUTDATED"
            reasons = []
            if diff_usable != 0:
                reasons.append(f"Usable stock difference: {abs(diff_usable)} unit(s) (QR shows {scanned_usable}, Live is {live_usable})")
            if diff_status:
                reasons.append(f"Status mismatch: QR is {scanned_status}, Live is {live_status}")
            if diff_loc:
                reasons.append(f"Location mismatch: QR is {scanned_location}, Live is {live_loc}")
            message = f"⚠️ QR SNAPSHOT IS OUTDATED — {'; '.join(reasons)}. Regenerate QR label recommended."
            
        return {
            "valid": True,
            "matched": is_match,
            "verdict": verdict,
            "message": message,
            "product": {
                "id": p["id"],
                "sku": p["sku"],
                "name": p["name"],
            },
            "snapshot_data": {
                "usable_stock": scanned_usable,
                "status": scanned_status,
                "location": scanned_location,
                "version": scanned_version,
                "generated_at": scanned_generated,
            },
            "live_data": {
                "usable_stock": live_usable,
                "status": live_status,
                "physical_stock": p["physical_stock"],
                "reserved_stock": p["reserved_stock"],
                "damaged_stock": p["damaged_stock"],
                "location": live_loc,
            },
            "difference": {
                "usable_diff": diff_usable,
                "status_diff": diff_status,
                "location_diff": diff_loc,
            }
        }


def mark_qr_stale(product_id: str):
    """Marks QR snapshot stale when inventory changes."""
    with db_cursor() as cur:
        cur.execute("UPDATE product_qr_snapshots SET is_stale=1 WHERE product_id=?", (product_id,))
