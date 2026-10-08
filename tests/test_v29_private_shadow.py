"""Zero-network tests of opt-in private V29 shadow and its V2 rollback boundary."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.private_champion_shadow_v29 import (
    ENABLED_ENV, TOKEN_ENV, make_shadow_snapshot, authorized,
    ShadowUnauthorized, ShadowUnavailable,
)

REGISTRY = Path(__file__).resolve().parents[1]/"research"/"all_236_champions_v26.json"
SECRET = "research-only-strong-nonproduction-test-token-44"


def good_env():
    return {ENABLED_ENV:"1",TOKEN_ENV:SECRET}


def fake_baseline(country,item,record_audit):
    assert not record_audit
    return {
        "travel_reliability":"unreliable",
        "ready_for_live_guidance":False,
        "display_prediction":{
            "prediction_number":2,
            "projected":True,
            "recommended_leave_by_timestamp":1792000000,
            "recommended_arrival_timestamp":1792008940,
        },
    }


class ShadowModelContractTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with self.assertRaises(ShadowUnavailable):
            make_shadow_snapshot("jap","Xanax",SECRET,v2_fn=fake_baseline,
                                 environ={},registry_path=REGISTRY)
        self.assertFalse(authorized(SECRET,{}))

    def test_private_token_required(self):
        with self.assertRaises(ShadowUnauthorized):
            make_shadow_snapshot("jap","Xanax","incorrect",v2_fn=fake_baseline,
                                 environ=good_env(),registry_path=REGISTRY)
        self.assertFalse(authorized(SECRET,{ENABLED_ENV:"1", TOKEN_ENV:"short"}))
        self.assertTrue(authorized(SECRET,good_env()))

    def test_existing_v2_only_no_champion_suggestion(self):
        data=make_shadow_snapshot("jap","Xanax",SECRET,v2_fn=fake_baseline,
                                  environ=good_env(),registry_path=REGISTRY)
        self.assertEqual(data["key"],"jap:Xanax")
        self.assertEqual(data["candidate_model_family"],"japan_xanax_specialist")
        self.assertFalse(data["champion_executed"])
        self.assertFalse(data["candidate_promoted"])
        self.assertFalse(data["chance_calibrated"])
        self.assertEqual(data["baseline"]["model"],"existing_live_v2_reference_only")
        self.assertEqual(data["baseline"]["recommended_leave_by_timestamp"],1792000000)
        self.assertEqual(data["baseline"]["prediction_number"],2)
        self.assertNotIn(SECRET,json.dumps(data))

    def test_research_registry_has_all_catalog_items(self):
        r=json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(len(r["items"]),236)
        data=make_shadow_snapshot("uni","Nessie Plushie",SECRET,v2_fn=fake_baseline,
                                  environ=good_env(),registry_path=REGISTRY)
        self.assertEqual(data["candidate_model_family"],"recent_phase_template")
        self.assertEqual(data["champion_status"],"FROZEN_CANDIDATE_NOT_INTEGRATED")

    def test_unknown_model_not_bypassing_catalog(self):
        with self.assertRaises(KeyError):
            make_shadow_snapshot("jap","Not Real",SECRET,v2_fn=fake_baseline,
                                 environ=good_env(),registry_path=REGISTRY)
        with self.assertRaises(ValueError):
            make_shadow_snapshot("invalid","Xanax",SECRET,v2_fn=fake_baseline,
                                 environ=good_env(),registry_path=REGISTRY)

    def test_fallback_on_v2_runtime_error(self):
        def failure(*a,**kw):raise RuntimeError("secrets and filesystem traces must not leak")
        result=make_shadow_snapshot("jap","Xanax",SECRET,v2_fn=failure,
                                    environ=good_env(),registry_path=REGISTRY)
        self.assertEqual(result["baseline"]["status"],"unavailable")
        self.assertNotIn("secrets",json.dumps(result))
        self.assertFalse(result["champion_executed"])

    def test_absent_model_prediction_does_not_invent_departure(self):
        result=make_shadow_snapshot(
            "jap","Xanax",SECRET,v2_fn=lambda *args,**kw: {"display_prediction":None},
            environ=good_env(),registry_path=REGISTRY
        )
        self.assertEqual(result["baseline"]["status"],"no_reachable_prediction")
        self.assertIsNone(result["baseline"]["recommended_leave_by_timestamp"])

    def test_reject_bogus_registry(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"registry.json"
            p.write_text(json.dumps({"schema":"wrong","items":{}}))
            with self.assertRaises(ShadowUnavailable):
                make_shadow_snapshot("jap","Xanax",SECRET,v2_fn=fake_baseline,
                                     environ=good_env(),registry_path=p)

    def test_route_closed_by_default_and_token_gated(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.private_shadow_v29 import router
        app=FastAPI()
        app.include_router(router)
        cli=TestClient(app)
        with patch.dict(os.environ,{ENABLED_ENV:"0",TOKEN_ENV:SECRET}):
            r=cli.get("/api/research/champion-shadow",params={"country":"jap","item":"Xanax"},
                      headers={"X-Torn-Fren-Shadow-Token":SECRET})
            self.assertEqual(r.status_code,404)
        with patch.dict(os.environ,{ENABLED_ENV:"1",TOKEN_ENV:SECRET}):
            r=cli.get("/api/research/champion-shadow",params={"country":"jap","item":"Xanax"})
            self.assertEqual(r.status_code,403)


if __name__=="__main__":
    unittest.main()
