"""V146: representative issue-locked comparison including mature vs pending."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v146_v145_same_issue_replay as m
from research import v128_full24_earliest_shadow as original
from research.v107_explicit_restock_cycle_baseline import StockObservation as O

T=1791800000
ITEM="uni:Nessie Plushie"


def phases():
    t=T-50000
    result=[O(t,0,"yata")]
    for _ in range(11):
        t+=600
        result.append(O(t,110,"yata"))
        t+=100
        result.append(O(t,105,"prometheus"))
        t+=100
        result.append(O(t,100,"yata"))
        t+=800
        result.append(O(t,0,"yata"))
        t+=100
        result.append(O(t,0,"prometheus"))
        t+=100
        result.append(O(t,0,"yata"))
    return result,t


def make_db(folder):
    src=Path(folder)/"stock.db"
    side=Path(folder)/"shadow.db"
    observations,issued=phases()
    with sqlite3.connect(src) as con:
        con.execute("""CREATE TABLE stock_history(
           id INTEGER PRIMARY KEY,timestamp INTEGER,quantity INTEGER,
           source TEXT,country TEXT,item_name TEXT)""")
        con.execute("""CREATE TABLE collection_gaps(
           start_timestamp INTEGER,end_timestamp INTEGER)""")
        con.execute("""CREATE TABLE poll_heartbeats(
           id INTEGER PRIMARY KEY,timestamp INTEGER,source TEXT,
           mode TEXT, success INTEGER)""")
        con.executemany("""INSERT INTO stock_history(
           timestamp,quantity,source,country,item_name) VALUES (?,?,?,?,?)""",[
           (x.epoch,x.quantity,x.source,"uni","Nessie Plushie")
           for x in observations])
    roster=original.exact_roster()
    record=original.item_record(
        ITEM,roster[ITEM],observations,[],issued=issued)
    with sqlite3.connect(side) as con:
        con.execute("""CREATE TABLE v128_issued(
            item_key TEXT, issued_epoch INTEGER,
            source_status TEXT,decision_status TEXT,payload_json TEXT)""")
        con.execute("""INSERT INTO v128_issued VALUES (?,?,?,?,?)""",(
            ITEM,issued,record["source_status"],record["decision_status"],
            json.dumps(record)))
    return src,side,issued


class SameIssueReplayTests(unittest.TestCase):
    def test_strict_old_recovery_is_not_new_live_success_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            earlier_bytes=(src.read_bytes(),side.read_bytes())
            with patch.object(m,"_pair_score",return_value="HIT"), (
                patch.object(m,"earliest_credible_for_country",
                    side_effect=lambda curve,key: {
                        "status":"EARLIEST_NOW","departure":curve["asof_epoch"],
                        "arrival":curve["asof_epoch"]+original.TRAVEL_SECONDS["uni"],
                        "score":.65,
                    })
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            self.assertEqual(result["exact_item_roster"],24)
            self.assertEqual(result["hourly_issued_cohorts"],1)
            self.assertEqual(result["monte_carlo_replayed"],1)
            row=result["items"][ITEM]
            self.assertEqual(row["recovered"],1)
            self.assertEqual(row["new_proposals"],1)
            self.assertEqual(row["original_proposals"],0)
            self.assertEqual(row["matched_new_vs_now"],1)
            self.assertEqual(row["new_only"],0)
            self.assertFalse(result["real_player_trip_success_certified"])
            self.assertFalse(result["backfill_provenance_frozen_at_original_issue"])
            self.assertFalse(result["new_future_watch_freshly_reconfirmed"])
            self.assertTrue(result["no_writes"])
            self.assertEqual(src.read_bytes(),earlier_bytes[0])
            self.assertEqual(side.read_bytes(),earlier_bytes[1])

    def test_explicit_restock_candidate_compares_on_exact_same_issue(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            recovered={
                "status":"PROVISIONAL_FIRST_REACHABLE_STOCK_WINDOW",
                "issued_epoch":issued,
                "travel_seconds":original.TRAVEL_SECONDS["uni"],
                "projected_windows":[],
                "first_reachable":{
                    "cycle_number":7,
                    "earliest_departure_epoch":issued+300,
                    "arrival_epoch":issued+300+
                                    original.TRAVEL_SECONDS["uni"],
                    "provisional":True,
                },
            }
            with patch.object(m,"first_reachable_stock_cycles",
                              return_value=recovered), (
                 patch.object(m,"_pair_score",return_value="HIT")
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["explicit_proposals"],1)
            self.assertEqual(row["matched_explicit_vs_now"],1)
            self.assertEqual(row["explicit_departure_median_wait_seconds"],300)
            self.assertEqual(row["explicit_only_vs_now"],0)
            self.assertEqual(row["now_only_vs_explicit"],0)
            self.assertFalse(result["source_provider_freshness_certified"])

    def test_stable_v151_is_scored_before_outcomes_with_shared_issue(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            fake={
                "status":"PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE",
                "score_now":0.5,
                "first_reachable":{
                    "departure_epoch":issued+300,
                    "arrival_epoch":issued+300+
                                    original.TRAVEL_SECONDS["uni"],
                    "scenario_stock_fraction":0.75,
                    "cadence_warning":None,
                },
            }
            with patch.object(m,"stable_earliest_departure",
                              return_value=fake), (
                 patch.object(m,"_pair_score",return_value="HIT")
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["stable_proposals"],1)
            self.assertEqual(row["stable_proxy_hit"],1)
            self.assertEqual(row["matched_stable_vs_now"],1)
            self.assertEqual(row["stable_only_vs_now"],0)
            self.assertEqual(row["stable_departure_median_wait_seconds"],300)
            self.assertFalse(result["real_player_trip_success_certified"])

    def test_direct_paired_v151_and_v148_and_delayed_value(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            v151={
                "status":"PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE",
                "score_now":0.4,
                "first_reachable":{
                    "departure_epoch":issued+300,
                    "arrival_epoch":issued+300+original.TRAVEL_SECONDS["uni"],
                    "scenario_stock_fraction":0.75,
                    "cadence_warning":None,
                },
            }
            v148={
                "status":"PROVISIONAL_FIRST_REACHABLE_STOCK_WINDOW",
                "issued_epoch":issued,
                "travel_seconds":original.TRAVEL_SECONDS["uni"],
                "projected_windows":[],
                "first_reachable":{
                    "cycle_number":4,"earliest_departure_epoch":issued+900,
                    "arrival_epoch":issued+900+original.TRAVEL_SECONDS["uni"],
                    "provisional":True,
                },
            }
            def outcome(db,country,item,arrival,now):
                if arrival==issued+300+original.TRAVEL_SECONDS["uni"]:
                    return "HIT"
                return "MISS"
            with patch.object(m,"stable_earliest_departure",return_value=v151), (
                patch.object(m,"first_reachable_stock_cycles",return_value=v148)
            ), patch.object(m,"_pair_score",side_effect=outcome):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["matched_stable_vs_explicit"],1)
            self.assertEqual(row["stable_only_vs_explicit"],1)
            self.assertEqual(row["explicit_only_vs_stable"],0)
            self.assertEqual(row["matched_different_departures"],1)
            self.assertEqual(row["stable_depart_future_proposals"],1)
            self.assertEqual(row["stable_depart_now_proposals"],0)
            self.assertEqual(row["matched_stable_delayed_vs_now"],1)
            self.assertEqual(row["delayed_stable_only_vs_now"],1)

    def test_60sec_candidate_is_paired_with_same_issue_300sec_outcome(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            flight=original.TRAVEL_SECONDS["uni"]
            def planner(key,phases,*,asof,scenarios,
                        departure_step_seconds=300,
                        cycle_sampling="independent"):
                self.assertEqual(asof,issued)
                self.assertEqual(phases["last_observation"].epoch,issued)
                step=departure_step_seconds
                departure=issued+(60 if step==60 else 300)
                return {
                    "status":"PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE",
                    "score_now":0.2,
                    "score_bins":[0.2]*(481 if step==60 else 97),
                    "first_next_restock_onset_median_seconds":360,
                    "first_reachable":{
                        "departure_epoch":departure,
                        "arrival_epoch":departure+flight,
                        "scenario_stock_fraction":0.75,
                        "cadence_warning":None,
                    },
                }
            def score(db,country,item,arrival,now):
                return "HIT" if arrival==issued+60+flight else "MISS"
            with patch.object(m,"stable_earliest_departure",
                              side_effect=planner),(
                patch.object(m,"_pair_score",side_effect=score)
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["fine60_proposals"],1)
            self.assertEqual(row["fine60_earlier_than_coarse"],1)
            self.assertEqual(row["fine60_vs_coarse_matched"],1)
            self.assertEqual(row["fine60_only_vs_coarse"],1)
            self.assertEqual(row["coarse_only_vs_fine60"],0)
            self.assertEqual(row["fine60_vs_now_matched"],1)
            self.assertEqual(row["fine60_only_vs_now"],1)
            self.assertEqual(row["fine60_departure_median_wait_seconds"],60)

    def test_paired_cycle_challenger_has_strict_same_issue_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            flight=original.TRAVEL_SECONDS["uni"]
            def planner(key,history,*,asof,scenarios,
                        departure_step_seconds=300,
                        cycle_sampling="independent"):
                self.assertEqual(asof,issued)
                self.assertEqual(history["last_observation"].epoch,issued)
                delay=(600 if cycle_sampling=="paired_complete" else
                       60 if departure_step_seconds==60 else 300)
                bins=(481 if departure_step_seconds==60 else 97)
                return {
                    "status":"PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE",
                    "score_now":0.3,"score_bins":[0.3]*bins,
                    "first_next_restock_onset_median_seconds":450,
                    "first_reachable":{
                        "departure_epoch":issued+delay,
                        "arrival_epoch":issued+delay+flight,
                        "scenario_stock_fraction":0.7,
                        "cadence_warning":None,
                    }}
            def score(db,country,item,arrival,now):
                return "HIT" if arrival==issued+600+flight else "MISS"
            with patch.object(m,"stable_earliest_departure",
                              side_effect=planner),(
                 patch.object(m,"_pair_score",side_effect=score)
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["paired_proposals"],1)
            self.assertEqual(row["paired_proxy_hit"],1)
            self.assertEqual(row["paired_vs_independent_matched"],1)
            self.assertEqual(row["paired_only_vs_independent"],1)
            self.assertEqual(row["independent_only_vs_paired"],0)
            self.assertEqual(row["paired_only_vs_leave_now"],1)
            self.assertEqual(row["paired_median_wait_seconds"],600)
            self.assertFalse(result["real_player_trip_success_certified"])

    def test_v157_routing_is_frozen_before_future_outcome_scoring(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            flight=original.TRAVEL_SECONDS["uni"]
            def model(key,phases,*,asof,scenarios,
                      departure_step_seconds=300,
                      cycle_sampling="independent"):
                self.assertEqual(asof,issued)
                self.assertEqual(phases["last_observation"].epoch,issued)
                delay=(600 if cycle_sampling=="paired_complete" else
                       60 if departure_step_seconds==60 else 300)
                return {
                    "status":"PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE",
                    "score_now":.2,
                    "score_bins":[.2]*(481 if departure_step_seconds==60 else 97),
                    "first_next_restock_onset_median_seconds":800,
                    "first_reachable":{
                        "departure_epoch":issued+delay,
                        "arrival_epoch":issued+delay+flight,
                        "wait_seconds":delay,
                        "scenario_stock_fraction":.65,
                        "cadence_warning":None,
                    },
                }
            def select(key,history,*,asof):
                self.assertEqual(asof,issued)
                self.assertEqual(history["last_observation"].epoch,issued)
                return {
                    "selected_sampling":"paired_complete",
                    "reason":"PREQUENTIAL_FIRST_CYCLE_SURVIVAL_IMPROVEMENT",
                    "heldout_episodes":7,
                }
            def score(db,country,item,arrival,now):
                return "HIT" if arrival==issued+600+flight else "MISS"
            with patch.object(m,"stable_earliest_departure",side_effect=model),(
                 patch.object(m,"prequential_item_route",side_effect=select)
            ), patch.object(m,"_pair_score",side_effect=score):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["prequential_proposals"],1)
            self.assertEqual(row["prequential_paired_selected"],1)
            self.assertEqual(row["prequential_vs_independent_matched"],1)
            self.assertEqual(row["prequential_only_vs_independent"],1)
            self.assertEqual(row["independent_only_vs_prequential"],0)
            self.assertEqual(row["prequential_only_vs_now"],1)
            self.assertEqual(row["prequential_scored_issue_hours"],1)
            self.assertFalse(result["real_player_trip_success_certified"])

    def test_v158_flight_horizon_route_is_asof_and_scored_on_same_arrival(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            flight=original.TRAVEL_SECONDS["uni"]
            def model(key,phases,*,asof,scenarios,
                      departure_step_seconds=300,
                      cycle_sampling="independent"):
                self.assertEqual(asof,issued)
                self.assertEqual(phases["last_observation"].epoch,issued)
                delay=(600 if cycle_sampling=="paired_complete" else
                       60 if departure_step_seconds==60 else 300)
                return {
                    "status":"PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE",
                    "score_now":.2,
                    "score_bins":[.2]*(481 if departure_step_seconds==60 else 97),
                    "first_next_restock_onset_median_seconds":800,
                    "first_reachable":{
                        "departure_epoch":issued+delay,
                        "arrival_epoch":issued+delay+flight,
                        "wait_seconds":delay,"scenario_stock_fraction":.65,
                        "cadence_warning":None,
                    },
                }
            def select(key,history,*,asof):
                self.assertEqual(asof,issued)
                self.assertEqual(history["last_observation"].epoch,issued)
                return {
                    "selected_sampling":"paired_complete",
                    "reason":"PREQUENTIAL_FLIGHT_HORIZON_PAIRED_LIFT",
                    "validation_origin_count":6,
                }
            def score(db,country,item,arrival,now):
                return "HIT" if arrival==issued+600+flight else "MISS"
            with patch.object(m,"stable_earliest_departure",side_effect=model),(
                 patch.object(m,"flight_horizon_item_route",side_effect=select)
            ), patch.object(m,"_pair_score",side_effect=score):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["flight_horizon_proposals"],1)
            self.assertEqual(row["flight_horizon_selected_paired"],1)
            self.assertEqual(row["flight_horizon_vs_independent_matched"],1)
            self.assertEqual(row["flight_horizon_only_vs_independent"],1)
            self.assertEqual(row["independent_only_vs_flight_horizon"],0)
            self.assertEqual(row["flight_horizon_only_vs_now"],1)
            self.assertEqual(row["flight_horizon_valid_origins"],6)
            self.assertTrue(
                result["issue_phase_episode_audit"][
                    "not_independent_future_restock_proof"])
            # The tiny fixture can have an unknown reconstructed onset;
            # V159 must not invent an independent episode just because
            # a mocked model happened to produce a matched WIN.
            phase_totals=result["issue_phase_episode_audit"]["totals"]
            self.assertLessEqual(
                phase_totals["raw_paired_exclusive_issue_wins"],
                row["paired_only_vs_independent"])
            self.assertLessEqual(
                phase_totals["v158_net_exclusive_issue_wins"],
                row["flight_horizon_only_vs_independent"])
            self.assertFalse(result["real_player_trip_success_certified"])

    def test_stable_no_candidate_still_preserves_no_data_vs_score_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            fake={
                "status":"NO_TWO_BIN_SUPPORTED_DEPARTURE",
                "score_now":0.1,
                "first_reachable":None,
            }
            with patch.object(m,"stable_earliest_departure",return_value=fake):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["stable_proposals"],0)
            self.assertEqual(row["stable_status:NO_TWO_BIN_SUPPORTED_DEPARTURE"],1)
            self.assertEqual(row["matched_stable_vs_now"],0)

    def test_a_mutated_historical_snapshot_is_not_claimed_matched(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            with sqlite3.connect(side) as con:
                raw=json.loads(con.execute(
                    "SELECT payload_json FROM v128_issued").fetchone()[0])
                raw["last_stock_quantity"]=100000
                con.execute("UPDATE v128_issued SET payload_json=?",
                            (json.dumps(raw),))
            with patch.object(m,"empirical_arrival_scores") as scorer:
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
                scorer.assert_not_called()
            self.assertEqual(result["monte_carlo_replayed"],0)
            self.assertEqual(result["items"][ITEM][
                "ISSUED_SOURCE_SNAPSHOT_MISMATCH"],1)

    def test_unmatured_new_outcome_cannot_count_as_hit_or_miss(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            with patch.object(m,"_pair_score",return_value="PENDING"), (
                patch.object(m,"earliest_credible_for_country",
                    side_effect=lambda curve,key: {
                        "status":"EARLIEST_WAIT_SUPPORTED",
                        "departure":curve["asof_epoch"]+600,
                        "arrival":curve["asof_epoch"]+600+
                                  original.TRAVEL_SECONDS["uni"],
                        "score":.7,
                    })
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+800,max_model_evals=10)
            item=result["items"][ITEM]
            self.assertEqual(item["PENDING"],1)
            self.assertEqual(item["matched_new_vs_now"],0)
            self.assertEqual(item["new_proxy_hit"] if "new_proxy_hit" in item
                             else 0,0)

    def test_recency_restock_evaluated_against_exact_same_future_event(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            # Extra collector changes are AFTER the saved issue time.
            with sqlite3.connect(src) as db:
                db.executemany(
                    "INSERT INTO stock_history(timestamp,quantity,source,country,item_name) VALUES(?,?,?,?,?)",
                    [(issued+500,110,"yata","uni","Nessie Plushie"),
                     (issued+1000,0,"yata","uni","Nessie Plushie")])
            def v151_model(key,history,*,asof,scenarios,
                           departure_step_seconds=300,
                           cycle_sampling="independent"):
                self.assertEqual(asof,issued)
                self.assertEqual(history["last_observation"].epoch,issued)
                return {"status":"NO_TWO_BIN_SUPPORTED_DEPARTURE",
                        "score_now":0.1,"first_reachable":None,
                        "first_next_restock_onset_median_seconds":550,
                        "peak_scenario_stock_fraction":0.4,
                        "adjacent_supported_bin_count":0}
            with patch.object(m,"stable_earliest_departure",
                              side_effect=v151_model):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+1500,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["next_restock_scored"],1)
            self.assertEqual(row["next_restock_abs_error_total_seconds"],50)
            self.assertEqual(row.get("recent_recent_3_scored",0),1,
                             msg=str({k:v for k,v in row.items()
                                      if k.startswith("recency_") or
                                         k.startswith("restock:")}))
            self.assertEqual(row["recent_recent_3_paired"],1)
            self.assertEqual(row["v151_beats_recent_recent_3"],1)
            self.assertEqual(row["recent_recent_3_beats_v151"],0)

    def test_replay_input_limits_guard_mutation_and_unbounded_cpu(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            for args in ({"collector":src,"sidecar":src,"now":issued},
                         {"collector":src,"sidecar":side,
                          "now":issued,"max_model_evals":0},
                         {"collector":src,"sidecar":side,"now":issued,"days":99}):
                with self.subTest(args=args),self.assertRaises(ValueError):
                    m.replay(**args)


if __name__=="__main__":
    unittest.main()
