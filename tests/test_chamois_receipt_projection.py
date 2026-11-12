"""Regression for final-pair Chamois 31+ zero-grace policy selector.

Receipt columns must match the grade_trip provider-freshness contract; source
clocks used to resolve an expert outcome are causal evidence, not a heuristic.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v169_incremental_checkpoint_selector as selector_mod


class ChamoisReceiptProjectionTests(unittest.TestCase):
    def test_resolved_checkpoint_label_gets_four_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'fixture.sqlite'
            with sqlite3.connect(path) as db:
                db.executescript('''
                    CREATE TABLE stock_history (
                        id INTEGER PRIMARY KEY, timestamp INTEGER, quantity INTEGER,
                        source TEXT, country TEXT, item_name TEXT);
                    CREATE TABLE poll_heartbeats (
                        id INTEGER PRIMARY KEY, timestamp INTEGER, mode TEXT, success INTEGER);
                    CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER);
                    CREATE TABLE country_stock_observations (
                        id INTEGER PRIMARY KEY, received_epoch INTEGER,
                        country_update_epoch INTEGER, clock_status TEXT,
                        source TEXT, country TEXT);
                    INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                        VALUES (3900,31,'provider','swi','Chamois Plushie'),
                               (4050,31,'provider','swi','Chamois Plushie');
                    INSERT INTO poll_heartbeats(timestamp,mode,success)
                        VALUES (3900,'poll-cycle',1),(4050,'poll-cycle',1);
                    INSERT INTO country_stock_observations(
                        received_epoch,country_update_epoch,clock_status,source,country)
                        VALUES (3950,3949,'REPORTED','provider','swi');
                ''')

            class FakePlanner:
                def __init__(self, *args, **kwargs): pass
                def plan(self, q): return None

            # Drive the actual SELECT + grade_trip call, without fitting any
            # 24-bank model or depending on production data.
            def fake_simulate(planner, tl, start, travel, *, grace, label_at_arrival):
                label = label_at_arrival(4000)
                return {'status':'RESOLVED_EXPERT_DECISION','success':label,'resolved_at':4000}

            selector = selector_mod.IncrementalCheckpointSelector(
                'swi:Chamois Plushie',min_qty=31,grace=0,
                policy_consistent_labels=True,reuse_resolved_plans=False)
            selector._eligible = lambda *args: [1000]
            with patch.object(selector_mod,'Timeline',return_value=object()), \
                 patch.object(selector_mod,'load_gaps',return_value=([],[])), \
                 patch.object(selector_mod,'EXPERTS',((1,7200,3600),)), \
                 patch.object(selector_mod,'FastTemplatePlanner',FakePlanner), \
                 patch.object(selector_mod,'simulate_one',side_effect=fake_simulate), \
                 patch.object(selector_mod,'score_experts',return_value={
                     'expert_index':0,'posterior_score':0.75,'resolved_count':1}):
                selection = selector.update_and_select(path, 5000)
            self.assertEqual(selection['status'],'SELECTED')
            self.assertEqual(selector.entries[(1000,0)][0], 1)
            self.assertEqual(selection['arrival_stock_threshold'],31)
            self.assertEqual(selection['arrival_grace_seconds'],0)

if __name__ == '__main__': unittest.main()