"""Demo data seeder with customer emails, shortage states, and real-time alert triggers."""
import uuid
import json
from datetime import datetime, timezone, timedelta
from .db import db_cursor, now_iso, init_db, get_setting
from .services.alert import create_alert, send_system_digest_email
from .engines import allocate_inventory, compute_risk, compute_priority

LOCATIONS = ["A01", "A02", "A03", "A04", "A07", "B01", "B04", "B12", "C02", "C03"]

PRODUCTS = [
    ("KB-102", "Wireless Keyboard", "Electronics", "Logitech Corp", "A03", 4, 5, 10, 20, 6, 800),
    ("MS-201", "Optical Mouse", "Electronics", "Logitech Corp", "A01", 45, 10, 15, 30, 8, 450),
    ("HP-301", "Bluetooth Headphones", "Electronics", "Sony Ltd", "A02", 22, 8, 12, 25, 4, 2100),
    ("MN-401", "27\" LED Monitor", "Electronics", "Dell Inc", "B01", 8, 3, 5, 12, 1.5, 15000),
    ("USB-501", "USB-C Hub", "Accessories", "Anker", "A04", 60, 15, 20, 40, 10, 1200),
    ("CAM-601", "Webcam HD", "Electronics", "Logitech Corp", "A07", 2, 4, 6, 15, 3, 3500),
    ("SP-701", "Bluetooth Speaker", "Electronics", "JBL", "B04", 30, 6, 10, 20, 5, 2800),
    ("PW-801", "Power Bank 20K", "Accessories", "Mi", "B12", 55, 12, 15, 30, 7, 1800),
    ("CB-901", "HDMI Cable 2m", "Accessories", "Amazon Basics", "C02", 120, 20, 25, 50, 12, 350),
    ("RT-102", "Wi-Fi Router", "Networking", "TP-Link", "C03", 6, 4, 8, 18, 2, 4500),
    ("SG-201", "SSD 1TB", "Storage", "Samsung", "A02", 18, 5, 8, 20, 3, 6500),
    ("KB-303", "Mechanical Keyboard", "Electronics", "Keychron", "A03", 0, 3, 5, 12, 2, 8500),
    ("MS-402", "Gaming Mouse", "Electronics", "Razer", "A01", 14, 5, 8, 18, 3.5, 3200),
    ("HD-501", "External HDD 2TB", "Storage", "WD", "B01", 25, 6, 10, 20, 3, 5500),
    ("CH-601", "Wireless Charger", "Accessories", "Belkin", "A04", 40, 8, 12, 25, 5, 1500),
    ("ST-701", "Laptop Stand", "Accessories", "Nulaxy", "B04", 32, 10, 14, 28, 6, 1200),
    ("LP-801", "Ring Light 10\"", "Accessories", "Neewer", "C02", 16, 5, 8, 15, 2.5, 1800),
    ("MC-901", "Condenser Mic", "Electronics", "Blue Yeti", "A07", 9, 3, 5, 12, 1.5, 9500),
    ("PR-101", "Wireless Presenter", "Accessories", "Logitech Corp", "A01", 28, 6, 10, 20, 4, 2200),
    ("TB-202", "Graphics Tablet", "Electronics", "Wacom", "B12", 5, 3, 5, 10, 1, 12000),
]

WORKERS = [
    ("Aarav Sharma", "PICKER", 92),
    ("Priya Patel", "PICKER", 88),
    ("Rohan Verma", "PACKER", 90),
    ("Meera Iyer", "QC", 95),
    ("Karan Singh", "DISPATCH", 87),
]

CUSTOMERS = [
    ("Acme Retail Ltd", "VIP", "procurement@acmeretail.com"),
    ("QuickMart India", "HIGH", "ops@quickmart.in"),
    ("Digital Ninja Store", "NORMAL", "inventory@digitalninja.io"),
    ("TechnoBazaar", "HIGH", "supply@technobazaar.com"),
    ("Home Essentials Co", "NORMAL", "orders@homeessentials.com"),
    ("StartupCloud Inc", "VIP", "procurement@startupcloud.io"),
    ("City Electronics", "NORMAL", "buyer@cityelectronics.com"),
    ("PowerZone Ltd", "LOW", "fulfillment@powerzone.in"),
]


def _uid():
    return str(uuid.uuid4())


def seed_demo(reset: bool = False, custom_recipient: str = None):
    init_db()
    with db_cursor() as cur:
        if reset:
            for t in ["order_items", "orders", "tasks", "exceptions", "decisions", "alerts",
                      "activity", "audit_log", "outbox", "inventory_history", "workers", "products"]:
                cur.execute(f"DELETE FROM {t}")
        cur.execute("SELECT COUNT(*) as c FROM products")
        if cur.fetchone()["c"] > 0 and not reset:
            return {"skipped": True}

        product_ids = {}
        for sku, name, cat, sup, loc, stock, min_s, safety, reorder, demand, price in PRODUCTS:
            pid = _uid()
            product_ids[sku] = pid
            cur.execute(
                "INSERT INTO products(id,sku,name,category,supplier,location,physical_stock,reserved_stock,damaged_stock,min_stock,safety_stock,reorder_level,avg_daily_demand,unit_price,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, sku, name, cat, sup, loc, stock, 0, 0, min_s, safety, reorder, demand, price, now_iso())
            )
        # damaged: mark 2 units of MS-201 damaged
        cur.execute("UPDATE products SET damaged_stock=2 WHERE sku='MS-201'")

        for name, role, eff in WORKERS:
            cur.execute(
                "INSERT INTO workers(id,name,role,available,workload,efficiency,current_task) VALUES(?,?,?,?,?,?,?)",
                (_uid(), name, role, 1, 0, eff, None)
            )

        # Orders
        now = datetime.now(timezone.utc)
        order_ids = []
        for i in range(25):
            cust, pri, email = CUSTOMERS[i % len(CUSTOMERS)]
            order_id = _uid()
            order_ids.append(order_id)
            hours_ahead = [2, 4, 6, 8, 12, 18, 24, 36, 48, 72][i % 10]
            required_by = (now + timedelta(hours=hours_ahead)).isoformat()
            order_no = f"WO-{1000 + i}"
            skus = list(product_ids.keys())
            n_items = 1 + (i % 3)
            picked = [skus[(i * 3 + k) % len(skus)] for k in range(n_items)]
            total_val = 0
            for sku in picked:
                qty = 1 + (i + hash(sku)) % 5
                cur.execute("SELECT unit_price FROM products WHERE id=?", (product_ids[sku],))
                p = cur.fetchone()
                total_val += qty * p["unit_price"]
                cur.execute(
                    "INSERT INTO order_items(id,order_id,product_id,quantity,allocated,picked) VALUES(?,?,?,?,?,?)",
                    (_uid(), order_id, product_ids[sku], qty, 0, 0)
                )
            cur.execute(
                "INSERT INTO orders(id,order_no,customer_name,customer_email,customer_priority,required_by,order_value,status,created_at,priority,priority_score,priority_reasons,risk_score,risk_reasons) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (order_id, order_no, cust, email, pri, required_by, total_val, "CREATED",
                 (now - timedelta(hours=i)).isoformat(), "MEDIUM", 0, "[]", 0, "[]")
            )

        # One active exception (missing item on KB-102)
        exc_id = _uid()
        cur.execute(
            "INSERT INTO exceptions(id,type,severity,order_id,product_id,description,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (exc_id, "MISSING_ITEM", "HIGH", None, product_ids["KB-102"],
             "KB-102: expected 4 units at A03, only 2 physically present", "OPEN", now_iso())
        )

    # Initial order allocations and risk calculations
    for oid in order_ids[:15]:
        allocate_inventory(oid)

    # Seed active live tasks across all 4 fulfillment stages (Picking -> Packing -> QC -> Dispatch)
    with db_cursor() as cur:
        cur.execute("SELECT id, role FROM workers WHERE available=1")
        workers_by_role = {}
        for w in cur.fetchall():
            workers_by_role.setdefault(w["role"], []).append(w["id"])

        # Stage 1: PICKING (Orders 0, 1, 2, 3)
        pickers = workers_by_role.get("PICKER", [])
        for i, oid in enumerate(order_ids[0:4]):
            wid = pickers[i % len(pickers)] if pickers else None
            tid = _uid()
            cur.execute("UPDATE orders SET status='PICKING' WHERE id=?", (oid,))
            cur.execute("INSERT INTO tasks(id,order_id,stage,worker_id,status,started_at) VALUES(?,?,?,?,?,?)",
                        (tid, oid, "PICKING", wid, "IN_PROGRESS", now_iso()))
            if wid:
                cur.execute("UPDATE workers SET workload=workload+1 WHERE id=?", (wid,))

        # Stage 2: PACKING (Orders 4, 5, 6)
        packers = workers_by_role.get("PACKER", [])
        for i, oid in enumerate(order_ids[4:7]):
            wid = packers[i % len(packers)] if packers else None
            tid = _uid()
            cur.execute("UPDATE orders SET status='PACKING' WHERE id=?", (oid,))
            cur.execute("INSERT INTO tasks(id,order_id,stage,worker_id,status,started_at) VALUES(?,?,?,?,?,?)",
                        (tid, oid, "PACKING", wid, "IN_PROGRESS", now_iso()))
            if wid:
                cur.execute("UPDATE workers SET workload=workload+1 WHERE id=?", (wid,))

        # Stage 3: QC (Orders 7, 8)
        qc_workers = workers_by_role.get("QC", [])
        for i, oid in enumerate(order_ids[7:9]):
            wid = qc_workers[i % len(qc_workers)] if qc_workers else None
            tid = _uid()
            cur.execute("UPDATE orders SET status='QC' WHERE id=?", (oid,))
            cur.execute("INSERT INTO tasks(id,order_id,stage,worker_id,status,started_at) VALUES(?,?,?,?,?,?)",
                        (tid, oid, "QC", wid, "IN_PROGRESS", now_iso()))
            if wid:
                cur.execute("UPDATE workers SET workload=workload+1 WHERE id=?", (wid,))

        # Stage 4: DISPATCH (Orders 9, 10, 11)
        dispatch_workers = workers_by_role.get("DISPATCH", [])
        for i, oid in enumerate(order_ids[9:12]):
            wid = dispatch_workers[i % len(dispatch_workers)] if dispatch_workers else None
            tid = _uid()
            cur.execute("UPDATE orders SET status='DISPATCH' WHERE id=?", (oid,))
            cur.execute("INSERT INTO tasks(id,order_id,stage,worker_id,status,started_at) VALUES(?,?,?,?,?,?)",
                        (tid, oid, "DISPATCH", wid, "QUEUED", now_iso()))
            if wid:
                cur.execute("UPDATE workers SET workload=workload+1 WHERE id=?", (wid,))

    # Initial critical shortage alert for KB-303 (0 stock)
    create_alert(
        event_type="OUT_OF_STOCK",
        severity="CRITICAL",
        title="Out of stock: KB-303",
        body="Mechanical Keyboard (KB-303) is at 0 units in Zone A03. Active customer demand requires 12 units.",
        entity_type="product",
        entity_id=product_ids["KB-303"],
        meta={"sku": "KB-303", "usable_stock": 0, "shortage": 12, "order_value": 34000},
        recommended_action="Expedite emergency reorder of 24 units from Keychron.",
        rule_keys={"critical_shortage", "oos_order"},
        event_key=f"OUT_OF_STOCK:{product_ids['KB-303']}",
    )

    # Trigger Real-Time Digest Email (both on startup and on demo reset!)
    recipient = custom_recipient or get_setting("company_email") or get_setting("email_recipient") or "manager@warehouse.com"
    send_system_digest_email(
        title="Warehouse Autopilot — Live State & Shortage Alert",
        summary="Warehouse state initialized. 1 critical stockout (KB-303) and 1 open exception detected.",
        is_reset=reset,
        recipient=recipient,
    )

    return {"seeded": True, "recipient": recipient}
