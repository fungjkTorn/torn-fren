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
