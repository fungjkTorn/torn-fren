"""Opt-in, read-only V38 API defaults disabled; does not compute predictions."""
import os
import unittest
from unittest.mock import patch
from fastapi import HTTPException

from web.app import api_v38_research_predictions


class ExperimentalAPITests(unittest.TestCase):
    def test_disabled_without_flag(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(HTTPException) as caught:
                api_v38_research_predictions()
            self.assertEqual(caught.exception.status_code,404)

    def test_enabled_but_missing_sidecar_abstains(self):
        with patch.dict(os.environ,{"TORN_FREN_V38_EXPERIMENTAL_API":"1"},clear=True):
            result=api_v38_research_predictions()
            self.assertTrue(result["fallback_required"])
            self.assertEqual(result["status"],"SIDECAR_NOT_CONFIGURED")

    def test_reads_only_precomputed_data(self):
        with patch.dict(os.environ,{
            "TORN_FREN_V38_EXPERIMENTAL_API":"1",
            "TORN_FREN_V38_SNAPSHOT_DB":"/tmp/not-important.db",
        },clear=True):
            with patch("web.app.read_v38_snapshots",return_value={"status":"NO_SNAPSHOT"}) as reader:
                d=api_v38_research_predictions(country="UNI",item="Heather")
        self.assertTrue(d["experimental"])
        self.assertFalse(d["probability_calibrated"])
        self.assertEqual(d["source"],"PRECOMPUTED_SIDECAR_ONLY")
        self.assertEqual(reader.call_args.kwargs["key"],"uni:Heather")
        self.assertEqual(reader.call_args.kwargs["limit"],236)

    def test_no_half_item_queries(self):
        with patch.dict(os.environ,{
            "TORN_FREN_V38_EXPERIMENTAL_API":"1",
            "TORN_FREN_V38_SNAPSHOT_DB":"/tmp/side.db",
        },clear=True):
            with self.assertRaises(HTTPException) as caught:
                api_v38_research_predictions(country="uni")
            self.assertEqual(caught.exception.status_code,400)


if __name__=="__main__":
    unittest.main()
