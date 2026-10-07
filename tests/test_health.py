"""Tests for the health endpoint."""

import unittest

from fastapi.testclient import TestClient

from app.main import app


class HealthEndpointTests(unittest.TestCase):
    def test_health_returns_service_status(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "ok", "service": "beyondcv-ai"}
        )


if __name__ == "__main__":
    unittest.main()
