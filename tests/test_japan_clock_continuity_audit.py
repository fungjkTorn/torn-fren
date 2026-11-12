import unittest
from research.japan_xanax.clock_continuity_audit import analyze


class ClockAuditTests(unittest.TestCase):
    def test_provider_switch_clock_rewinds_and_within_provider_regressions_are_distinct(self):
        clocks=[(100,'yata',90,'REPORTED',10),(130,'prometheus',80,'REPORTED',10),
                (160,'prometheus',70,'REPORTED',10),(190,'yata',180,'REPORTED',10)]
        r=analyze(clocks,[],200)
        self.assertEqual(r['counts']['country_provider_switches'],2)
        self.assertEqual(r['counts']['switch_to_older_report_clock'],1)
        self.assertEqual(r['providers']['prometheus']['within_provider_clock_regressions'],1)
        self.assertEqual(r['providers']['yata']['within_provider_clock_regressions'],0)

    def test_missing_future_empty_clocks_never_count_as_recent_reports(self):
        r=analyze([(100,'yata',None,'MISSING',10),(130,'yata',150,'FUTURE',10),
                   (160,'yata',150,'EMPTY_PAYLOAD_REPORTED',0)],[],200)
        self.assertEqual(r['providers']['yata']['report_age_seconds'],{'n':0})

    def test_receipts_do_not_invent_item_events_and_zero_is_physical_zero(self):
        stock=[(1,100,'yata'),(20,29,'yata'),(50,0,'yata'),(120,100,'prometheus'),(150,0,'prometheus')]
        r=analyze([(30,'yata',20,'REPORTED',10),(60,'yata',50,'REPORTED',10),
                   (90,'prometheus',80,'REPORTED',10)],stock,200)
        events=r['stock_event_counts_since_first_clock']
        self.assertEqual(events['same_provider_positive_to_zero'],2)
        self.assertEqual(events.get('same_provider_zero_to_positive',0),0)
        self.assertEqual(events['cross_provider_physical_phase_conflicts'],1)

    def test_future_evidence_is_refused_and_missing_clocks_remain_missing(self):
        self.assertEqual(analyze([],[],200)['status'],'NO_RECENT_JAPAN_CLOCKS')
        with self.assertRaises(ValueError):analyze([(201,'yata',190,'REPORTED',10)],[],200)
        with self.assertRaises(ValueError):analyze([],[(201,0,'yata')],200)


if __name__=='__main__':unittest.main()
