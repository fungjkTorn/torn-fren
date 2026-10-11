"""V91 decision policy contract: earliest departure != strongest stock reserve."""
import unittest
from dataclasses import replace
from research import v91_travel_decision_contract as m

NOW=1791650000

def example(item="mex:Jaguar Plushie",wait=60,stock=None,level="research",
            model="candidate_a",survival=None,provider=None,revision=None,
            p=None,n=None,issued=None,source=None):
    at=NOW-20 if issued is None else issued
    hb=NOW-25 if source is None else source
    return m.Opportunity(
        item_key=item,model_id=model,issued_at=at,stock_as_of=hb,
        valid_until=at+300,depart_at=NOW+wait,
        arrive_at=NOW+wait+m.TRAVEL_SECONDS[item.split(":",1)[0]],
        projected_stock_floor=stock,evidence_tier=level,
        provider_update_as_of=provider,
        projected_survival_minutes=survival,
        revision_magnitude_seconds=revision,
        calibrated_success_probability=p,independent_calibration_sample_size=n,
    )


class V91DecisionViewsTests(unittest.TestCase):
    def test_near_term_and_later_views_from_same_model_set(self):
        early=example(wait=30,model="near",stock=50)
        later=example(wait=3600,model="late",stock=1900)
        report=m.evaluate_views([early,later],now=NOW)
        self.assertEqual(report["leave_now"][0]["model_id"],"near")
        self.assertEqual(report["next_opportunity"][0]["model_id"],"near")
        self.assertEqual(report["best_chance"][0]["model_id"],"late")
        self.assertEqual(report["best_chance"][0]["stock_reserve_above_30"],1870)
        self.assertIsNone(report["best_chance"][0]["calibrated_success_probability"])
        self.assertIn("Stock-margin proxy",report["best_chance_warning"])

    def test_quick_view_does_not_silently_expand_to_eight_hours(self):
        c=example(wait=21600,stock=2000)
        v=m.evaluate_views([c],now=NOW)
        self.assertEqual(v["leave_now"],[])
        self.assertEqual(len(v["next_opportunity"]),1)
        self.assertEqual(v["next_opportunity"][0]["exposure"],"FUTURE_WATCH")

    def test_research_only_never_called_ready_even_with_stock_bound(self):
        v=m.evaluate_views([example(wait=0,stock=800,
                        provider=NOW-25)],now=NOW)
        a=v["leave_now"][0]
        self.assertEqual(a["exposure"],"PROVISIONAL_NEAR_TERM")
        self.assertFalse(a["accuracy_verified"])
        self.assertTrue(a["experimental"])

    def test_verified_high_margin_requires_fresh_provider_update_for_qualified(self):
        without=example(wait=10,stock=100,level="validated")
        with_prov=replace(without,provider_update_as_of=NOW-25)
        first=m.evaluate_views([without],now=NOW)["leave_now"][0]
        second=m.evaluate_views([with_prov],now=NOW)["leave_now"][0]
        self.assertEqual(first["exposure"],"PROVISIONAL_NEAR_TERM")
        self.assertEqual(second["exposure"],"QUALIFIED_DEPARTURE_WINDOW")

    def test_does_not_fake_stock_reserve_or_best_rank(self):
        c=example(wait=40,stock=None)
        report=m.evaluate_views([c],now=NOW)
        self.assertEqual(len(report["leave_now"]),1)
        self.assertIsNone(report["leave_now"][0]["stock_reserve_above_30"])
        self.assertEqual(report["best_chance"],[])
        self.assertIn("cannot rank",report["best_chance_warning"])

    def test_rejects_expired_stale_departed_and_bad_flight(self):
        normal=example()
        variants=[
            replace(normal,valid_until=NOW-1),
            replace(normal,stock_as_of=NOW-300),
            replace(normal,depart_at=NOW-1,arrive_at=NOW-1+1020),
            replace(normal,arrive_at=normal.arrive_at+1234),
        ]
        report=m.evaluate_views(variants,now=NOW)
        self.assertEqual(report["valid_candidate_count"],0)
        self.assertEqual(sum(report["excluded_by_reason"].values()),len(variants))

    def test_rejects_invalid_model_probability_and_low_predicted_stock(self):
        model=example(stock=80)
        invalids=[
            replace(model,projected_stock_floor=29),
            replace(model,calibrated_success_probability=.91,
                    independent_calibration_sample_size=60),
            replace(model,calibrated_success_probability=1.15,
                    evidence_tier="validated",independent_calibration_sample_size=60),
            replace(model,provider_update_as_of=NOW-600),
            replace(model,status="EXPERT_ABSTAINED"),
        ]
        r=m.evaluate_views(invalids,now=NOW)
        self.assertEqual(r["valid_candidate_count"],0)
        self.assertEqual(len(r["excluded_by_reason"]),4) # probability failures share reason

    def test_calibrated_probabilities_must_be_backed_by_validated_sample(self):
        p1=example(stock=100,wait=60,model="validated",level="validated",
                   p=.82,n=52)
        p2=example(stock=4000,wait=90,model="research",level="research")
        r=m.evaluate_views([p1,p2],now=NOW)
        self.assertEqual(r["best_chance"][0]["model_id"],"validated")
        self.assertEqual(r["best_chance"][0]["independent_calibration_sample_size"],52)

    def test_item_categories_and_country_filter(self):
        cases=[
            ("mex:Jaguar Plushie","plushies"),
            ("jap:Xanax","medical"),
            ("arg:Ceibo Flower","flowers"),
            ("chi:Panda Plushie","plushies"),
            ("can:Crocus","flowers"),
            ("cay:Stingray Plushie","plushies"),
            ("arg:Patagonian Fossil","fossils"),
            ("arg:Unknown Equipment","other"),
        ]
        for key,cat in cases:
            self.assertEqual(m.item_category(key),cat)
        r=m.evaluate_views([example(),example(item="jap:Xanax",
                           stock=80)],now=NOW,category="medical")
        self.assertEqual([c["item_key"] for c in r["next_opportunity"]],
                         ["jap:Xanax"])

    def test_source_currently_stale_even_when_issuance_was_valid(self):
        source=example(issued=NOW-170,source=NOW-200)
        self.assertEqual(m.validity(source,NOW),"STALE_COLLECTOR_NOW")
        provider=example(provider=NOW-181)
        self.assertEqual(m.validity(provider,NOW),"STALE_PROVIDER_UPDATE")

    def test_invalid_category_fails_closed_without_throwing(self):
        bad=example()
        bad=replace(bad,category="unspecified-unknown")
        r=m.evaluate_views([bad],now=NOW)
        self.assertEqual(r["valid_candidate_count"],0)
        self.assertEqual(r["excluded_by_reason"]["INVALID_CATEGORY"],1)

    def test_one_per_item_while_showing_multiple_different_items(self):
        a=example(wait=20,model="a")
        b=example(wait=40,model="b")
        other=example(item="cay:Stingray Plushie",wait=30,model="c")
        r=m.evaluate_views([b,other,a],now=NOW)
        self.assertEqual([p["model_id"] for p in r["leave_now"]],["a","c"])
        self.assertEqual(len(r["next_opportunity"]),2)

    def test_user_can_change_quick_window_not_hard_country_limit(self):
        c=example(wait=600)
        self.assertEqual(m.evaluate_views([c],now=NOW)["leave_now"],[])
        self.assertEqual(len(m.evaluate_views(
            [c],now=NOW,quick_seconds=900)["leave_now"]),1)
        with self.assertRaises(ValueError):
            m.evaluate_views([c],now=NOW,quick_seconds=4000)

if __name__=="__main__":
    unittest.main()
