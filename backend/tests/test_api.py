"""Integration tests for FastAPI routes using TestClient.

Run with:  python -m pytest backend/tests/ -v
"""
import sys
import os
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("GEMINI_API_KEY", "test_key_placeholder")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")

from fastapi.testclient import TestClient
from backend.server import app

client = TestClient(app, raise_server_exceptions=False)


# ─── Health ───────────────────────────────────────────────────────────────────
class TestAPIHealth:
    def test_api_root_returns_ok(self):
        """GET /api returns healthy status with expected fields."""
        resp = client.get("/api")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "Warehouse Autopilot" in data["name"]
        assert "version" in data

    def test_frontend_serves_html(self):
        """GET / serves the SPA index.html."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_404_returns_structured_response(self):
        """Non-existent API routes return a structured 404."""
        resp = client.get("/api/nonexistent_xyz_route")
        assert resp.status_code == 404


# ─── Security Headers ─────────────────────────────────────────────────────────
class TestSecurityHeaders:
    def test_x_content_type_options(self):
        resp = client.get("/api")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self):
        resp = client.get("/api")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_x_xss_protection(self):
        resp = client.get("/api")
        assert "X-XSS-Protection" in resp.headers

    def test_content_security_policy_present(self):
        resp = client.get("/api")
        assert "Content-Security-Policy" in resp.headers

    def test_response_time_header(self):
        resp = client.get("/api")
        assert "X-Response-Time" in resp.headers


# ─── Products ─────────────────────────────────────────────────────────────────
class TestProductsAPI:
    def test_get_products_returns_list(self):
        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_products_not_empty(self):
        resp = client.get("/api/products")
        products = resp.json()
        assert len(products) >= 1

    def test_product_schema_fields(self):
        """Each product has the required schema fields."""
        resp = client.get("/api/products")
        product = resp.json()[0]
        required = ("id", "sku", "name", "category", "physical_stock", "unit_price")
        for field in required:
            assert field in product, f"Missing product field: {field}"

    def test_product_stock_status_is_valid(self):
        """Each product has a valid status value."""
        valid_statuses = {"NORMAL", "LOW", "CRITICAL", "OUT_OF_STOCK"}
        resp = client.get("/api/products")
        for p in resp.json():
            # API returns field as 'status' (not 'stock_status')
            assert p.get("status") in valid_statuses


# ─── Orders ───────────────────────────────────────────────────────────────────
class TestOrdersAPI:
    def test_get_orders_returns_list(self):
        resp = client.get("/api/orders")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_orders_not_empty(self):
        resp = client.get("/api/orders")
        assert len(resp.json()) >= 1

    def test_order_schema_fields(self):
        resp = client.get("/api/orders")
        order = resp.json()[0]
        for field in ("id", "order_no", "customer_name", "status"):
            assert field in order, f"Missing order field: {field}"


# ─── Exceptions & Decisions ───────────────────────────────────────────────────
class TestOperationsAPI:
    def test_get_exceptions_returns_list(self):
        resp = client.get("/api/exceptions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_decisions_returns_list(self):
        resp = client.get("/api/decisions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_alerts_returns_list(self):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ─── Settings ─────────────────────────────────────────────────────────────────
class TestSettingsAPI:
    def test_get_settings_returns_dict(self):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_settings_has_notification_toggles(self):
        resp = client.get("/api/settings")
        settings = resp.json()
        # Should have email/whatsapp toggle keys
        assert any("email" in k.lower() for k in settings.keys())


# ─── Workers ──────────────────────────────────────────────────────────────────
class TestWorkersAPI:
    def test_get_workers_returns_list(self):
        resp = client.get("/api/workers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_worker_schema_fields(self):
        resp = client.get("/api/workers")
        workers = resp.json()
        if workers:
            for field in ("id", "name", "role"):
                assert field in workers[0], f"Missing worker field: {field}"
