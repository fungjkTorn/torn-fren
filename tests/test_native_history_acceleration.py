from contextlib import contextmanager
import statistics
import unittest
from unittest.mock import patch
from services.native_history_acceleration import immutable_history_queries


class ImmutableHistoryTests(unittest.TestCase):
    def test_exact_integer_means_query_reuse_and_exception_cleanup(self):
        from services import history_service as h
        calls=[]
        class Connection:
            closed=False
            def close(self):self.closed=True
        con=Connection()
        def query(*args):calls.append(args);return ('unchanged',args)
        names=('_collection_coverage','_collection_gap_overlap','_event_boundary_is_clean',
               '_get_poll_cycle_start_timestamp','_get_successful_poll_timestamps',
               '_historical_observation_timestamps')
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in names:stack.enter_context(patch.object(h,name,query))
            connect=stack.enter_context(patch.object(h,'_connect',return_value=con))
            mean=h._leave_one_out_mean
            with self.assertRaisesRegex(RuntimeError,'forced'):
                with immutable_history_queries(h):
                    for values in ([1], [1,2,4], [10**30,10**30+1,10**30+5], [1.5,2.5,3.0]):
                        for i in range(len(values)):
                            others=values[:i]+values[i+1:]
                            self.assertEqual(statistics.mean(others) if others else None,h._leave_one_out_mean(values,i))
                    self.assertEqual(h._collection_coverage(1,9),h._collection_coverage(1,9))
                    self.assertEqual(1,len(calls))
                    with h._connect() as borrowed:self.assertIs(con,borrowed)
                    self.assertFalse(con.closed)
                    raise RuntimeError('forced')
            self.assertTrue(con.closed);self.assertIs(connect,h._connect)
            self.assertIs(mean,h._leave_one_out_mean)
            for name in names:self.assertIs(query,getattr(h,name))
            connect.assert_called_once_with()

    def test_indexed_gap_checks_match_native_boundaries_and_nested_gaps(self):
        from types import SimpleNamespace
        from services import history_service as h
        from services.plushie_flower_dynamic_planner_v20 import overlaps_gap
        engine=SimpleNamespace(overlaps_gap=overlaps_gap)
        class Connection:
            def close(self):pass
        with patch.object(h,'_connect',return_value=Connection()):
            with immutable_history_queries(h,engine):
                for gaps in ([],[(10.,20.)],[(10.,100.),(20.,30.),(40.,float('inf'))]):
                    for a in (-1,10,19,20,21,30,100,101):
                        for b in (-1,10,19,20,21,30,100,101):
                            self.assertEqual(overlaps_gap(gaps,a,b),engine.overlaps_gap(gaps,a,b),(gaps,a,b))
        self.assertIs(overlaps_gap,engine.overlaps_gap)

    def test_tiny_cycle_counts_equal_previous_scan(self):
        import random
        from services import history_service as h
        rng=random.Random(174)
        rows=[(0,0)]
        for i in range(200):
            rows.extend([(i*300+60,rng.choice([1,4,50,10000,10000,10000])),(i*300+120,0)])
        coverage={'valid':True,'max_gap_seconds':0,'method':'fixture'}
        with patch.object(h,'_collection_coverage',return_value=coverage),patch.object(h,'_event_boundary_is_clean',return_value=True):
            cycles,active,waits=h._build_validated_cycles(rows)
        completed=[c for c in cycles if c.get('complete')]
        for wait in waits:
            expected=sum(1 for c in completed if c.get('tiny_restock') and wait['from_depletion']<c['restock_time']<wait['to_restock'])
            self.assertEqual(expected,wait['bridged_tiny_restock_count'])
        self.assertTrue(any(w['bridged_tiny_restock_count'] for w in waits))
