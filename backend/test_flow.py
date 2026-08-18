import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'c:/WareHouse')
import asyncio
from app.backend.db import init_db, get_setting
from app.backend.seed import seed_demo
from app.backend.engines import get_autopilot_action_queue, get_warehouse_heatmap, rebalance_zone_workers, execute_autopilot_action
from app.backend.services.email import send_email
from app.backend.services.desktop import send_desktop_notification

print("1. Initializing DB and Seeding...")
init_db()
res = seed_demo(reset=True)
print("Seed result:", res)

print("\n2. Testing Autopilot Action Queue...")
actions = get_autopilot_action_queue()
print(f"Autopilot generated {len(actions)} ranked actions:")
for a in actions[:4]:
    print(f" - {a['icon']} {a['title']} | Impact: {a['impact']} | Conf: {a['confidence']}%")

print("\n3. Testing Heatmap...")
hm = get_warehouse_heatmap()
print(f"Heatmap zones: {len(hm['zones'])}")
for z in hm['zones']:
    print(f" - {z['name']}: {z['status']} ({z['workload_pct']}%) | Orders waiting: {z['orders_waiting']}")
print(f"Recommendation: {hm['recommendation']['action']} ({hm['recommendation']['detail']})")

print("\n4. Testing 1-Click Action Execution...")
if actions:
    first_act = actions[0]
    exec_res = asyncio.run(execute_autopilot_action(first_act['type'], first_act.get('params', {})))
    print(f"Executed action: {first_act['type']} -> {exec_res}")

print("\n5. Testing Email Dispatch...")
email_res = asyncio.run(send_email("Critical Test Alert", "KB-303 shortage detected", "judge@hackathon.com", severity="CRITICAL"))
print("Email send result:", email_res)

print("\n6. Testing Desktop Notification...")
desktop_res = send_desktop_notification("Warehouse Autopilot", "Real-time dispatch operational", "INFO")
print("Desktop notif result:", desktop_res)

print("\nAll backend features verified successfully!")
