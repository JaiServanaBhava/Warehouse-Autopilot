"""Unit tests for Warehouse Autopilot core logic.

Run with:  python -m pytest backend/tests/ -v
"""
import sys
import os
import pytest
from pathlib import Path

# Make repo root importable
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("GEMINI_API_KEY", "test_key_placeholder")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")


# ─── DB & Schema ──────────────────────────────────────────────────────────────
class TestDatabase:
    """Tests for database initialisation and helpers."""

    def test_init_db_is_idempotent(self):
        """init_db() can be called multiple times without raising."""
        from backend.db import init_db
        init_db()
        init_db()  # second call must not fail

    def test_db_cursor_context_manager(self):
        """db_cursor yields a working cursor and auto-commits."""
        from backend.db import db_cursor, init_db
        init_db()
        with db_cursor() as cur:
            cur.execute("SELECT 1 AS val")
            row = cur.fetchone()
        assert row["val"] == 1

    def test_now_iso_format(self):
        """now_iso() returns a valid ISO-8601 UTC string."""
        from backend.db import now_iso
        from datetime import datetime
        ts = now_iso()
        assert isinstance(ts, str)
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_get_set_setting_roundtrip(self):
        """Settings can be written and read back correctly."""
        from backend.db import init_db, get_setting, set_setting
        init_db()
        set_setting("unit_test_key", "hello_world_123")
        val = get_setting("unit_test_key")
        assert val == "hello_world_123"

    def test_get_setting_default_when_missing(self):
        """get_setting returns the supplied default for unknown keys."""
        from backend.db import init_db, get_setting
        init_db()
        val = get_setting("nonexistent_key_xyz_abc", default="fallback_value")
        assert val == "fallback_value"


# ─── Seed ─────────────────────────────────────────────────────────────────────
class TestSeed:
    """Tests for the demo seed function."""

    def test_seed_demo_runs_and_returns_seeded(self):
        """seed_demo() completes without raising and returns a dict."""
        from backend.db import init_db
        from backend.seed import seed_demo
        init_db()
        result = seed_demo()
        assert isinstance(result, dict)
        # Either freshly seeded or already seeded (skipped) — both are valid
        assert result.get("seeded") is True or result.get("skipped") is True

    def test_products_exist_after_seed(self):
        """At least 10 products are present after seeding."""
        from backend.db import init_db, db_cursor
        from backend.seed import seed_demo
        init_db()
        seed_demo()
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM products")
            row = cur.fetchone()
        assert row["cnt"] >= 10

    def test_orders_exist_after_seed(self):
        """At least 5 orders are present after seeding."""
        from backend.db import init_db, db_cursor
        from backend.seed import seed_demo
        init_db()
        seed_demo()
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM orders")
            row = cur.fetchone()
        assert row["cnt"] >= 5

    def test_workers_exist_after_seed(self):
        """At least 1 worker is present after seeding."""
        from backend.db import init_db, db_cursor
        from backend.seed import seed_demo
        init_db()
        seed_demo()
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM workers")
            row = cur.fetchone()
        assert row["cnt"] >= 1


# ─── Decision Engine ──────────────────────────────────────────────────────────
class TestDecisionEngine:
    """Tests for the core decision / scoring engine."""

    def test_stock_status_normal(self):
        """NORMAL returned when stock is well above all thresholds."""
        from backend.engines import stock_status
        p = {"physical_stock": 100, "reserved_stock": 0, "damaged_stock": 0,
             "usable_stock": 100, "min_stock": 10, "safety_stock": 5, "reorder_level": 20}
        assert stock_status(p) == "NORMAL"

    def test_stock_status_low(self):
        """LOW returned when stock is at or below reorder level."""
        from backend.engines import stock_status
        p = {"physical_stock": 15, "reserved_stock": 0, "damaged_stock": 0,
             "usable_stock": 15, "min_stock": 10, "safety_stock": 5, "reorder_level": 20}
        assert stock_status(p) == "LOW"

    def test_stock_status_critical(self):
        """CRITICAL returned when stock is at or below safety_stock."""
        from backend.engines import stock_status
        p = {"physical_stock": 4, "reserved_stock": 0, "damaged_stock": 0,
             "usable_stock": 4, "min_stock": 10, "safety_stock": 5, "reorder_level": 20}
        assert stock_status(p) == "CRITICAL"

    def test_stock_status_out_of_stock(self):
        """OUT_OF_STOCK returned when usable_stock is zero."""
        from backend.engines import stock_status
        p = {"physical_stock": 0, "reserved_stock": 0, "damaged_stock": 0,
             "usable_stock": 0, "min_stock": 10, "safety_stock": 5, "reorder_level": 20}
        assert stock_status(p) == "OUT_OF_STOCK"

    def test_compute_available_normal(self):
        """compute_available returns max(0, physical - reserved - damaged)."""
        from backend.engines import compute_available
        p = {"physical_stock": 100, "reserved_stock": 20, "damaged_stock": 5}
        assert compute_available(p) == 75

    def test_compute_available_floor_at_zero(self):
        """compute_available never returns a negative number."""
        from backend.engines import compute_available
        p = {"physical_stock": 5, "reserved_stock": 10, "damaged_stock": 2}
        assert compute_available(p) == 0

    def test_compute_available_exact_zero(self):
        """compute_available returns 0 when all stock is consumed."""
        from backend.engines import compute_available
        p = {"physical_stock": 15, "reserved_stock": 10, "damaged_stock": 5}
        assert compute_available(p) == 0

    def test_warehouse_health_returns_required_keys(self):
        """warehouse_health() returns a dict with 'overall' and 'breakdown' keys."""
        from backend.db import init_db
        from backend.seed import seed_demo
        from backend.engines import warehouse_health
        init_db()
        seed_demo()
        health = warehouse_health()
        assert isinstance(health, dict)
        # warehouse_health returns overall score + breakdown
        assert "overall" in health, f"Missing 'overall' in warehouse_health: {list(health.keys())}"
        assert "breakdown" in health, f"Missing 'breakdown' in warehouse_health: {list(health.keys())}"

    def test_autopilot_score_in_valid_range(self):
        """autopilot_score() returns a numeric value between 0 and 100."""
        from backend.db import init_db
        from backend.seed import seed_demo
        from backend.engines import autopilot_score
        init_db()
        seed_demo()
        result = autopilot_score()
        # Score is returned as an int/float directly
        score = int(result) if not isinstance(result, dict) else result.get("overall", result.get("score", 0))
        assert 0 <= score <= 100, f"Score out of range: {score}"


# ─── Gemini Service ───────────────────────────────────────────────────────────
class TestGeminiService:
    """Tests for Gemini API integration layer."""

    def test_configured_returns_false_without_key(self):
        """configured() is False when GEMINI_API_KEY is empty."""
        import backend.services.gemini as gem
        original = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = ""
        result = gem.configured()
        assert result is False
        if original:
            os.environ["GEMINI_API_KEY"] = original

    def test_ask_gemini_graceful_failure_without_key(self):
        """ask_gemini returns ok=False with a clear message when key is missing."""
        import backend.services.gemini as gem
        saved = os.environ.pop("GEMINI_API_KEY", None)
        result = gem.ask_gemini("test prompt", {}, [])
        assert result["ok"] is False
        assert "GEMINI_API_KEY" in result.get("error", "")
        if saved:
            os.environ["GEMINI_API_KEY"] = saved
