"""Canary safety: the public V2 API must retain its original live behavior."""
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from web.app import app
from services.private_champion_shadow_v29 import ENABLED_ENV, TOKEN_ENV


class CanaryIsolationTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)

    def test_private_shadow_returns_404_by_default(self):
        with patch.dict(os.environ,{ENABLED_ENV:"0",TOKEN_ENV:"a"*42}):
            x=self.client.get("/api/research/champion-shadow",
                params={"country":"can","item":"Fire Hydrant"},
                headers={"X-Torn-Fren-Shadow-Token":"a"*42})
        self.assertEqual(x.status_code,404)

    def test_bad_secret_never_returns_predictions(self):
        with patch.dict(os.environ,{ENABLED_ENV:"1",TOKEN_ENV:"a"*42}):
            x=self.client.get("/api/research/champion-shadow",
                params={"country":"can","item":"Fire Hydrant"},
                headers={"X-Torn-Fren-Shadow-Token":"bad-token"})
        self.assertEqual(x.status_code,403)
        self.assertNotIn("Fire Hydrant",x.text)

    def test_live_v2_route_is_still_registered(self):
        paths={r.path for r in app.routes if hasattr(r,"path")}
        from web.private_shadow_v29 import router as private_router
        self.assertIn("/api/research/champion-shadow",
                     {r.path for r in private_router.routes
                      if hasattr(r,"path")},
                     "The module has not registered the private handler")
        print("SHADOW DEBUG module routes:", [x.path for x in private_router.routes])
        print("SHADOW DEBUG app route count:",len(app.routes))
        print("SHADOW DEBUG app routes:", sorted(paths))
        for name in ("/api/history","/api/catalog","/api/admin/health",
                     "/api/research/champion-shadow"):
            self.assertIn(name,paths)
        from web.app import api_history
        self.assertIn("build_live_prediction_v2",api_history.__code__.co_names)
        self.assertNotIn("research_candidate",api_history.__code__.co_names)

    def test_private_auth_requires_new_nonweak_secret(self):
        from services.private_champion_shadow_v29 import authorized
        self.assertFalse(authorized("short",{ENABLED_ENV:"1",TOKEN_ENV:"short"}))
        self.assertFalse(authorized(None,{ENABLED_ENV:"1",TOKEN_ENV:"a"*42}))
        self.assertTrue(authorized("a"*42,{ENABLED_ENV:"1",TOKEN_ENV:"a"*42}))

if __name__=="__main__":
    unittest.main()
