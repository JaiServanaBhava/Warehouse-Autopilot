import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'c:/WareHouse')

from app.backend.db import init_db, db_cursor, get_setting, set_setting
from app.backend.seed import seed_demo

print("--- 1. Initializing DB and Setting Test Recipients ---")
init_db()
set_setting("company_email", "manager-alerts@warehouse-autopilot.internal")
set_setting("whatsapp_number", "+918019753996")
set_setting("supplier_po_recipient", "logitech-supplier@procurement-hub.com")

print("Company Alert Target:", get_setting("company_email"))
print("WhatsApp Target:", get_setting("whatsapp_number"))
print("Supplier PO Target:", get_setting("supplier_po_recipient"))

print("\n--- 2. Executing Demo Reset / Startup Dispatch ---")
res = seed_demo(reset=True, custom_recipient="manager-alerts@warehouse-autopilot.internal")
print("Seed/Reset Result:", res)

print("\n--- 3. Verifying Dispatched Outbox Messages ---")
with db_cursor() as cur:
    cur.execute("SELECT * FROM outbox ORDER BY created_at DESC LIMIT 10")
    outbox = cur.fetchall()

po_emails = [o for o in outbox if o["channel"] == "SUPPLIER_PO_EMAIL"]
company_emails = [o for o in outbox if o["channel"] == "EMAIL" or o["channel"] == "BUSINESS_EMAIL"]
whatsapp_msgs = [o for o in outbox if o["channel"] == "WHATSAPP"]

print(f"\nDispatched Supplier Purchase Orders ({len(po_emails)}):")
for p in po_emails:
    print(f" - To: {p['recipient']} | Subject: {p['subject']} | Status: {p['status']}")

print(f"\nDispatched Company Alert Emails ({len(company_emails)}):")
for e in company_emails:
    print(f" - To: {e['recipient']} | Subject: {e['subject']} | Status: {e['status']}")

print(f"\nDispatched WhatsApp Alerts ({len(whatsapp_msgs)}):")
for w in whatsapp_msgs:
    print(f" - To: {w['recipient']} | Subject: {w['subject']} | Status: {w['status']}")

assert len(po_emails) >= 1, "Must dispatch at least 1 Supplier Purchase Order email on startup/reset!"
assert len(company_emails) >= 1, "Must dispatch at least 1 Company Operational Alert email on startup/reset!"
assert len(whatsapp_msgs) >= 1, "Must dispatch at least 1 WhatsApp alert on startup/reset!"

print("\nALL STARTUP & DEMO RESET REAL-TIME DISPATCH TESTS PASSED 100%!")
