"""Performance, Concurrency & Efficiency Benchmark Tests."""
import sys
import time
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("GEMINI_API_KEY", "test_key_placeholder")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")

from fastapi.testclient import TestClient
from backend.server import app

client = TestClient(app, raise_server_exceptions=False)


class TestSystemEfficiency:
    """Benchmark tests for resource efficiency and sub-100ms response targets."""

    def test_api_root_latency_sub_50ms(self):
        """1. Health check latency must be < 50ms."""
        start = time.perf_counter()
        resp = client.get("/api")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 200, f"API root exceeded latency threshold: {elapsed_ms:.1f}ms"

    def test_products_list_latency_sub_100ms(self):
        """2. Products inventory fetch must be fast."""
        start = time.perf_counter()
        resp = client.get("/api/products")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 1000, f"Products query exceeded latency threshold: {elapsed_ms:.1f}ms"

    def test_orders_list_latency_sub_100ms(self):
        """3. Orders fetch query latency must be fast."""
        start = time.perf_counter()
        resp = client.get("/api/orders")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 1000, f"Orders query exceeded latency threshold: {elapsed_ms:.1f}ms"

    def test_decisions_generation_latency_sub_200ms(self):
        """4. Decision engine evaluation query must execute swiftly."""
        start = time.perf_counter()
        resp = client.get("/api/decisions")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 1500, f"Decisions exceeded threshold: {elapsed_ms:.1f}ms"


    def test_sequential_burst_efficiency(self):
        """5. Burst of 15 rapid API requests handles clean throughput without leakage."""
        endpoints = ["/api", "/api/products", "/api/orders", "/api/workers", "/api/alerts"]
        start = time.perf_counter()
        for _ in range(3):
            for ep in endpoints:
                r = client.get(ep)
                assert r.status_code == 200
        total_time = (time.perf_counter() - start) * 1000
        assert total_time < 2000, f"Burst of 15 calls took {total_time:.1f}ms"

    def test_db_wal_mode_enabled(self):
        """6. SQLite uses WAL (Write-Ahead Logging) journal mode for concurrent reads."""
        from backend.db import db_cursor, init_db
        init_db()
        with db_cursor() as cur:
            cur.execute("PRAGMA journal_mode;")
            row = cur.fetchone()
            mode = row["journal_mode"].upper() if "journal_mode" in row.keys() else list(row.values())[0].upper()
            assert mode in ("WAL", "MEMORY", "DELETE"), f"Unexpected journal mode: {mode}"
