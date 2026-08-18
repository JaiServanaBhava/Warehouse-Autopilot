import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'c:/WareHouse')
from app.backend.db import init_db, db_cursor
from app.backend.seed import seed_demo
from app.backend.services.qr_passport import (
    get_or_create_qr_passport, regenerate_qr_passport,
    verify_qr_passport
)

print("--- 1. Initializing DB and Seeding ---")
init_db()
seed_demo(reset=True)

with db_cursor() as cur:
    cur.execute("SELECT * FROM products WHERE sku='CAM-601'")
    p = cur.fetchone()

print(f"Product: {p['sku']} — {p['name']} (ID: {p['id']}, Physical: {p['physical_stock']})")

print("\n--- 2. Generating QR Intelligence Passport ---")
passport = get_or_create_qr_passport(p['id'])
print(f"Snapshot Version: v{passport['snapshot_version']}")
print(f"Snapshot Usable: {passport['snapshot_usable_stock']}")
print(f"Snapshot Status: {passport['snapshot_status']}")
print(f"Snapshot Action: {passport['snapshot_action']}")
print("QR Payload Text:\n" + passport['snapshot_payload'])
assert passport['qr_image_url'].startswith("data:image/png;base64,"), "QR Base64 generation failed!"

print("\n--- 3. Running Initial Reality Check Verification ---")
v1 = verify_qr_passport(payload_text=passport['snapshot_payload'], product_id=p['id'])
print(f"Verdict: {v1['verdict']} | Message: {v1['message']}")
assert v1['matched'] is True, "Initial snapshot should match live state!"

print("\n--- 4. Changing Inventory (Simulating Live Stock Mutation) ---")
with db_cursor() as cur:
    cur.execute("UPDATE products SET physical_stock=physical_stock-10 WHERE id=?", (p['id'],))

# Check passport stale detection
passport_stale = get_or_create_qr_passport(p['id'])
print(f"Is QR Stale after stock change? {passport_stale['is_stale']} (Snapshot usable: {passport_stale['snapshot_usable_stock']}, Live usable: {passport_stale['live_state']['usable_stock']})")
assert passport_stale['is_stale'] is True, "QR should be marked stale when inventory changes!"

v2 = verify_qr_passport(payload_text=passport['snapshot_payload'], product_id=p['id'])
print(f"Reality Check after mutation: {v2['verdict']} | Message: {v2['message']}")
assert v2['matched'] is False, "Reality check must detect difference!"
print(f"Difference detected: {v2['difference']['usable_diff']} units mismatch")

print("\n--- 5. Regenerating QR Snapshot ---")
passport_regen = regenerate_qr_passport(p['id'])
print(f"New Version: v{passport_regen['snapshot_version']} (Generated: {passport_regen['generated_at']})")
print(f"New Usable in QR: {passport_regen['snapshot_usable_stock']}")
assert passport_regen['snapshot_version'] == 2, "Snapshot version should increment!"

v3 = verify_qr_passport(payload_text=passport_regen['snapshot_payload'], product_id=p['id'])
print(f"Reality Check on regenerated QR: {v3['verdict']} | Message: {v3['message']}")
assert v3['matched'] is True, "Regenerated snapshot must match live state!"

print("\nALL QR INTELLIGENCE PASSPORT TESTS PASSED 100%!")
