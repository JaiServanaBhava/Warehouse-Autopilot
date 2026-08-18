import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'c:/WareHouse')
import asyncio
from app.backend.db import init_db, get_setting, set_setting
from app.backend.seed import seed_demo
from app.backend.services.alert import send_supplier_reorder_email
from app.backend.services.email import send_email

print("--- 1. Setting custom company email & WhatsApp number in DB ---")
init_db()
set_setting("company_email", "judge@hackathon-finals.com")
set_setting("whatsapp_number", "+919988776655")
set_setting("supplier_po_recipient", "logitech-procurement@supplychain.org")

print("Configured DB settings:")
print(" - company_email:", get_setting("company_email"))
print(" - whatsapp_number:", get_setting("whatsapp_number"))
print(" - supplier_po_recipient:", get_setting("supplier_po_recipient"))

print("\n--- 2. Executing Demo Reset ---")
res = seed_demo(reset=True)
print("Demo Reset Result:", res)

print("\n--- 3. Verifying that settings were NOT wiped ---")
assert get_setting("company_email") == "judge@hackathon-finals.com", "company_email was reset!"
assert get_setting("whatsapp_number") == "+919988776655", "whatsapp_number was reset!"
assert get_setting("supplier_po_recipient") == "logitech-procurement@supplychain.org", "supplier_po_recipient was reset!"
print("SUCCESS: Settings are permanently preserved across resets!")

print("\n--- 4. Testing Automatic Supplier PO Reorder Service ---")
send_supplier_reorder_email(
    sku="MS-201",
    product_name="Ergonomic Mouse",
    supplier="Logitech Corp",
    quantity=50,
    reason="Stock dropped to 2 units (breached critical threshold)"
)
print("Supplier PO email dispatched!")

print("\n--- 5. Checking Outbox Records ---")
from app.backend.db import db_cursor
with db_cursor() as cur:
    cur.execute("SELECT channel, recipient, subject, status, created_at FROM outbox ORDER BY created_at DESC LIMIT 5")
    rows = cur.fetchall()
    for r in rows:
        print(f"[{r['channel']}] -> {r['recipient']} | Subject: {r['subject'] or 'Alert'} | Status: {r['status']}")

print("\nAll tests PASSED successfully!")
