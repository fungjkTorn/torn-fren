import json
import tempfile
import unittest
from pathlib import Path

from research.v30_native_parity_probe import (
    compare_exact,sample_rows,source_provenance,sha256,
)


class NativeParityProvenanceTests(unittest.TestCase):
    def test_saved_v21_and_newer_snapshots_are_incompatible(self):
        old="9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761"
        latest="d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583"
        x=source_provenance({"settings":{"db_sha256":old}},latest)
        self.assertEqual(x["status"],"CROSS_SNAPSHOT")
        self.assertFalse(x["same_snapshot_proven"])

    def test_missing_old_master_db_digest_is_unverified(self):
        current="a"*64
        x=source_provenance({"schema":"old_master"},current)
        self.assertEqual(x["status"],"UNKNOWN_SOURCE_DB_HASH")
        self.assertFalse(x["same_snapshot_proven"])

    def test_same_input_can_be_verifiable(self):
        x=source_provenance({"settings":{"db_sha256":"f"*64}},"f"*64)
        self.assertTrue(x["same_snapshot_proven"])
        self.assertEqual(x["status"],"SAME_DB_VERIFIED")

    def test_invalid_claimed_digest_rejected(self):
        with self.assertRaises(ValueError):
            source_provenance({"settings":{"db_sha256":"garbage"}},"f"*64)

    def test_declared_digest_not_overriding_embedded_provenance(self):
        x=source_provenance({"settings":{"db_sha256":"a"*64}},"b"*64,
                            declared_source_sha256="b"*64)
        self.assertEqual(x["source_sha256"],"a"*64)
        self.assertFalse(x["same_snapshot_proven"])

    def test_exact_departure_uses_same_starts_no_intersection_gaming(self):
        recorded=[{"start":100,"departure":200,"success":True},
                  {"start":400,"departure":500,"success":False}]
        actual=[{"start":100,"departure":200,"success":True},
                {"start":400,"departure":None,"success":False}]
        data=compare_exact(recorded,actual)
        self.assertEqual((data["matches"],data["n"],data["match_rate"]),(1,2,.5))
        self.assertIsNone(data["rows"][1]["departure_error_seconds"])

    def test_dropped_or_shifted_sessions_forbidden(self):
        with self.assertRaises(ValueError):
            compare_exact([{"start":100,"departure":200}],[ ])
        with self.assertRaises(ValueError):
            compare_exact([{"start":100,"departure":200}],
                          [{"start":101,"departure":200}])

    def test_start_sampling_is_deterministic_and_label_blind(self):
        a=[{"start":i*900,"departure":i*900+1200,"success":i%2==0} for i in range(20)]
        b=[dict(x,success=not x["success"]) for x in a]
        aa=sample_rows(a,5);bb=sample_rows(b,5)
        self.assertEqual([x["start"] for x in aa],[x["start"] for x in bb])
        self.assertEqual(len(aa),5)

    def test_sha256_of_existing_local_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x"
            p.write_bytes(b"hi")
            self.assertEqual(sha256(p),
                             "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4")


if __name__=="__main__":
    unittest.main()
