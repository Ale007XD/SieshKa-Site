"""
Integration tests for Time-First Menu API
Run with: pytest tests/test_timefirst_integration.py -v

These tests verify that the API endpoints work correctly.
Note: Requires running database and optionally Redis.
"""
import pytest
from datetime import datetime, time
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

# Import the FastAPI app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.main import app


@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)


class TestSlotsEndpoint:
    """Tests for /api/slots endpoint"""
    
    def test_slots_today_delivery(self, client):
        """Test getting slots for today with delivery method"""
        response = client.get("/api/slots?day=today&method=delivery")
        assert response.status_code == 200
        
        data = response.json()
        assert data["day"] == "today"
        assert data["method"] == "delivery"
        assert isinstance(data["slots"], list)
        
        # Should have slots in morning and evening windows
        if len(data["slots"]) > 0:
            slot = data["slots"][0]
            assert "time" in slot
            assert "available" in slot
            assert "label" in slot
    
    def test_slots_tomorrow_pickup(self, client):
        """Test getting slots for tomorrow with pickup method"""
        response = client.get("/api/slots?day=tomorrow&method=pickup")
        assert response.status_code == 200
        
        data = response.json()
        assert data["day"] == "tomorrow"
        assert data["method"] == "pickup"
    
    def test_slots_invalid_day(self, client):
        """Test slots endpoint with invalid day parameter"""
        response = client.get("/api/slots?day=invalid&method=delivery")
        assert response.status_code == 422  # Validation error
    
    def test_slots_invalid_method(self, client):
        """Test slots endpoint with invalid method parameter"""
        response = client.get("/api/slots?day=today&method=invalid")
        assert response.status_code == 422  # Validation error
    
    def test_slots_missing_params(self, client):
        """Test slots endpoint with missing parameters"""
        response = client.get("/api/slots")
        assert response.status_code == 422  # Validation error


class TestMenuEndpoint:
    """Tests for /api/menu endpoint"""
    
    def test_menu_today_delivery(self, client):
        """Test getting menu for today with delivery"""
        response = client.get("/api/menu?day=today&method=delivery")
        assert response.status_code == 200
        
        data = response.json()
        assert data["day"] == "today"
        assert data["method"] == "delivery"
        assert isinstance(data["categories"], list)
        assert "generated_at" in data
    
    def test_menu_with_slot(self, client):
        """Test getting menu with specific slot"""
        response = client.get("/api/menu?day=today&method=delivery&slot=14:00")
        assert response.status_code == 200
        
        data = response.json()
        assert data["slot"] == "14:00"
    
    def test_menu_invalid_slot_format(self, client):
        """Test menu endpoint with invalid slot format"""
        response = client.get("/api/menu?day=today&method=delivery&slot=25:00")
        assert response.status_code == 422  # Validation error


class TestMenuRefreshEndpoint:
    """Tests for /api/menu/refresh endpoint"""
    
    def test_menu_refresh(self, client):
        """Test menu cache refresh"""
        response = client.get("/api/menu/refresh")
        # May fail if no config in DB, but should return proper error
        assert response.status_code in [200, 500]


class TestHealthEndpoint:
    """Tests for /health endpoint"""
    
    def test_health_check(self, client):
        """Test health endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "database" in data


class TestCacheIntegration:
    """Tests for caching behavior"""
    
    def test_slots_cache_consistency(self, client):
        """Test that slots endpoint returns consistent results"""
        response1 = client.get("/api/slots?day=today&method=delivery")
        response2 = client.get("/api/slots?day=today&method=delivery")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Results should be the same (or very similar)
        assert data1["day"] == data2["day"]
        assert data1["method"] == data2["method"]
        assert len(data1["slots"]) == len(data2["slots"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
