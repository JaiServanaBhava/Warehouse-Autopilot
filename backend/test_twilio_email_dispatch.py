import sys
import io
import asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'c:/WareHouse')

from app.backend.services.email import send_email, _send_sync
from app.backend.db import get_setting

print("--- Testing Twilio Comms Email API Dispatch ---")
print("Recipient:", get_setting("company_email"))
print("Twilio Sender:", get_setting("twilio_email_from"))

res = _send_sync(
    subject="🚨 WAREHOUSE AUTOPILOT: Critical Shortage Detected (KB-303)",
    body_text="Mechanical Keyboard (KB-303) is at 0 units. Immediate replenishment required.",
    recipient="jaiservanabhava@gmail.com",
    html_body="<h2>Warehouse Alert</h2><p><b>Mechanical Keyboard (KB-303)</b> is at 0 units in Zone A03.</p>"
)

print("\nTwilio Email Dispatch Result:", res)

if res["status"] in ("SENT", "DISABLED"):
    print("SUCCESS: Twilio Comms Email dispatch handler functioning properly!")
else:
    print("Failed with status:", res["status"], res.get("error"))
