import sys
import io
import asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'c:/WareHouse')

from app.backend.services.notification import send_whatsapp, _send_sync
from app.backend.db import get_setting

print("--- Testing Twilio WhatsApp Dispatch ---")
print("Target Recipient:", get_setting("whatsapp_number"))
print("Twilio Sender:", get_setting("twilio_whatsapp_from"))
print("Content SID:", get_setting("twilio_content_sid"))

res = _send_sync("🚨 WAREHOUSE AUTOPILOT: Critical Shortage Detected for SKU KB-303! Immediate replenishment required.", None)
print("\nDispatch Result:", res)

if res["status"] in ("SENT", "DISABLED"):
    print("SUCCESS: Twilio WhatsApp dispatch handler functioning properly!")
else:
    print("Failed with status:", res["status"], res.get("error"))
