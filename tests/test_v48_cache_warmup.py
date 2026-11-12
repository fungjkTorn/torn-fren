"""V48 unattended opt-in research warmup cannot affect current 19 models."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from research import v48_cache_warmup as m


REQUIRED={
 "torn-fren-v38-private-shadow.timer",
 "torn-fren-web.service",
 "torn-fren-poller.service",
 "torn-fren-bot.service",
}


class V48WarmupTests(unittest.TestCase):
    def test_missing_required_unit_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"cached.db"
            result=m.work_once("/missing",out,
                active=lambda name:name in REQUIRED-{"torn-fren-bot.service"},
                capacity=lambda:{"allowed":True},
                runner=Mock(side_effect=AssertionError("must never run")))
            self.assertEqual(result["status"],"PREREQUISITE_SERVICE_INACTIVE")
            self.assertFalse(out.exists())

    def test_do_not_compete_with_active_nineteen_model_cycle(self):
        runner=Mock()
        result=m.work_once("/missing","/missing/cache.db",
            active=lambda name:name in REQUIRED or name=="torn-fren-v38-private-shadow.service",
            capacity=lambda:{"allowed":True},runner=runner)
        self.assertEqual(result["status"],"DEFERRED_19_MODEL_RESEARCH_ACTIVE")
        runner.assert_not_called()

    def test_cpu_pressure_abstains_before_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"cached.db"
            result=m.work_once("/missing",out,
                active=lambda name:name in REQUIRED,
                capacity=lambda:{"allowed":False},
                runner=Mock(side_effect=AssertionError("should not run")))
            self.assertEqual(result["status"],"DEFERRED_HOST_CPU_PRESSURE")
            self.assertFalse(out.exists())

    def test_round_robin_and_persistent_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"cached.db"
            calls=[]
            def fake(db,cache,target,now,*,budget_seconds,max_decisions):
                self.assertEqual(cache,out)
                self.assertEqual(budget_seconds,40)
                self.assertEqual(max_decisions,24)
                calls.append(target)
                return {"status":"BUILDING_RESOLVED_EXPERT_CACHE",
                        "executed_decisions":14}
            for _ in range(3):
                r=m.work_once("/missing",out,
                    active=lambda name:name in REQUIRED,
                    capacity=lambda:{"allowed":True},
                    runner=fake)
                self.assertEqual(r["status"],"V48_TICK_COMPLETE")
                self.assertFalse(r["modified_collector"])
                self.assertFalse(r["modified_v38_sidecar"])
            self.assertEqual(calls,["monkey","chamois","monkey"])
            st=m.read_status(out)
            self.assertEqual(st["next_target"],"chamois")
            self.assertIsNotNone(st["last_attempt"])

    def test_existing_cache_rows_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"cached.db"
            with sqlite3.connect(out) as c:
                c.execute("""CREATE TABLE expert_resolutions (
                    item_key TEXT, anchor_ts INTEGER, expert_id INTEGER)""")
                c.execute("""INSERT INTO expert_resolutions VALUES (
                    'arg:Monkey Plushie',12345,0)""")
            def no_work(*a,**kw):
                return {"status":"BUILDING_RESOLVED_EXPERT_CACHE"}
            m.work_once("/missing",out,
                active=lambda name:name in REQUIRED,
                capacity=lambda:{"allowed":True},runner=no_work)
            self.assertEqual(m.read_status(out)["cached_rows"]["arg:Monkey Plushie"],1)

    def test_status_missing_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"missing.db"
            self.assertEqual(m.read_status(out)["status"],"CACHE_MISSING")
            self.assertFalse(out.exists())


if __name__=="__main__":
    unittest.main()
