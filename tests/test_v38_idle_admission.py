"""Deterministic CPU admission validation with no VM sampling or modifications."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.v38_idle_admission import (
    parse_cpu, parse_pressure, assess, inspect
)

def sample(total, idle, steal=0):
    # user, nice, system, idle, iowait, irq, softirq, steal
    return (total, idle, steal)

class IdleAdmissionTests(unittest.TestCase):
    def test_parse_actual_linux_format(self):
        self.assertEqual(parse_cpu("cpu  200 3 70 650 2 8 12 5 0 0"), (950,650,5))
        pressure=parse_pressure(
            "some avg10=44.07 avg60=47.07 avg300=47.14 total=100\n"
            "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
        self.assertEqual(pressure,{"some":44.07,"full":0.0})

    def test_vm_idle_plus_psi_allows_bounded_canary_despite_high_load(self):
        result=assess(sample(1000,500),sample(2000,820),
                      {"some":44.07,"full":0.0},slots=2,load1=2.4)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["idle_fraction"],0.32)
        self.assertEqual(result["estimated_idle_cores"],0.64)
        self.assertEqual(result["admission_mode"],"measured_linux_idle_psi")

    def test_deny_insufficient_true_idle(self):
        result=assess(sample(1000,500),sample(2000,740),
                      {"some":10.0,"full":0.0},slots=2,load1=0.1)
        self.assertFalse(result["allowed"])

    def test_deny_psi_pressure_or_full_stall(self):
        for pressure in ({"some":57.0,"full":0.0},
                         {"some":20.0,"full":5.0}):
            result=assess(sample(1000,500),sample(2000,850),
                          pressure,slots=2,load1=2.4)
            self.assertFalse(result["allowed"])

    def test_deny_hypervisor_steal_and_excessive_load(self):
        self.assertFalse(assess(sample(1000,500),sample(2000,850,100),
                               {"some":20.0,"full":0.0},slots=2,load1=2)["allowed"])
        self.assertFalse(assess(sample(1000,500),sample(2000,850),
                               {"some":20.0,"full":0.0},slots=2,load1=5)["allowed"])

    def test_sample_failed_closed_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            stat=Path(directory)/"stat"
            psi=Path(directory)/"pressure"
            stat.write_text("cpu 200 0 0 500 0 0 0 0\n")
            psi.write_text("some avg10=40 total=0\nfull avg10=0 total=0\n")
            report=inspect(stat_file=stat,psi_file=psi,slots=2,
                           sleeper=lambda seconds: None,load1=2.4)
            self.assertFalse(report["allowed"])
            self.assertEqual(report["reason"],"MEASURED_HEADROOM_UNAVAILABLE")
            self.assertEqual(stat.read_text(),"cpu 200 0 0 500 0 0 0 0\n")

    def test_sampler_deterministic_with_two_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            stat=Path(directory)/"stat"
            psi=Path(directory)/"pressure"
            stat.write_text("cpu 500 0 0 500 0 0 0 0\n")
            psi.write_text("some avg10=44.07 total=0\nfull avg10=0 total=0\n")
            def advance(_):
                stat.write_text("cpu 1180 0 0 820 0 0 0 0\n")
            report=inspect(stat_file=stat,psi_file=psi,slots=2,
                           sleeper=advance,load1=2.4)
            self.assertTrue(report["allowed"])
            self.assertEqual(report["idle_fraction"],0.32)

if __name__=="__main__":unittest.main()
