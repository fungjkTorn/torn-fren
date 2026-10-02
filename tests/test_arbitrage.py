import unittest

from modules.arbitrage import BazaarListing, BuyOffer, evaluate_offer, scan_arbitrage


class ArbitrageEngineTests(unittest.TestCase):
    def test_meteorite_bulk_uses_multiple_sellers(self):
        listings = [
            BazaarListing(
                item_name="Meteorite Fragment",
                unit_price=455_000,
                quantity=8,
                source="tornw3b",
                seller_name="Seller A",
            ),
            BazaarListing(
                item_name="Meteorite Fragment",
                unit_price=460_000,
                quantity=22,
                source="tornw3b",
                seller_name="Seller B",
            ),
            BazaarListing(
                item_name="Meteorite Fragment",
                unit_price=468_000,
                quantity=40,
                source="tornw3b",
                seller_name="Seller C",
            ),
            BazaarListing(
                item_name="Meteorite Fragment",
                unit_price=490_000,
                quantity=100,
                source="tornw3b",
                seller_name="Too Expensive",
            ),
        ]

        offer = BuyOffer(
            item_name="Meteorite Fragment",
            unit_price=505_000,
            source="torn_exchange",
            buyer_name="Example Trader",
        )

        result = evaluate_offer(
            listings,
            offer,
            min_profit_per_item=20_000,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.quantity, 70)
        self.assertEqual(result.seller_count, 3)
        self.assertEqual(result.cheapest_buy_price, 455_000)
        self.assertEqual(result.highest_accepted_buy_price, 468_000)
        self.assertEqual(result.total_cost, 32_480_000)
        self.assertEqual(result.total_revenue, 35_350_000)
        self.assertEqual(result.total_profit, 2_870_000)
        self.assertAlmostEqual(result.average_buy_price, 464_000.0)
        self.assertAlmostEqual(result.average_profit_per_item, 41_000.0)

    def test_threshold_is_applied_per_listing_unit(self):
        listings = [
            BazaarListing("Item X", 450_000, 10, "source", seller_name="A"),
            BazaarListing("Item X", 486_000, 10, "source", seller_name="B"),
        ]
        offer = BuyOffer("Item X", 505_000, "buyers", "Trader")

        result = evaluate_offer(listings, offer, min_profit_per_item=20_000)

        self.assertIsNotNone(result)
        self.assertEqual(result.quantity, 10)
        self.assertEqual(result.highest_accepted_buy_price, 450_000)

    def test_buyer_quantity_cap(self):
        listings = [
            BazaarListing("Item X", 450_000, 10, "source", seller_name="A"),
            BazaarListing("Item X", 455_000, 10, "source", seller_name="B"),
        ]
        offer = BuyOffer(
            "Item X",
            500_000,
            "buyers",
            "Trader",
            max_quantity=12,
        )

        result = evaluate_offer(listings, offer, min_profit_per_item=20_000)

        self.assertIsNotNone(result)
        self.assertEqual(result.quantity, 12)
        self.assertEqual(result.total_cost, 5_410_000)
        self.assertEqual(result.total_profit, 590_000)

    def test_scan_keeps_best_buyer_per_item(self):
        listings = [
            BazaarListing("Item X", 450_000, 10, "source", seller_name="A"),
        ]
        offers = [
            BuyOffer("Item X", 490_000, "weav3r", "Buyer A"),
            BuyOffer("Item X", 505_000, "torn_exchange", "Buyer B"),
        ]

        results = scan_arbitrage(
            listings,
            offers,
            min_profit_per_item=20_000,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].buyer_name, "Buyer B")
        self.assertEqual(results[0].total_profit, 550_000)

    def test_tracks_buy_source_quantities_and_costs(self):
        listings = [
            BazaarListing("Item X", 100, 3, "tornw3b_bazaar", seller_name="A"),
            BazaarListing("Item X", 110, 2, "torn_item_market", seller_name="Market"),
        ]
        offer = BuyOffer("Item X", 150, "buyers", "Trader")

        result = evaluate_offer(listings, offer, min_profit_per_item=20)

        self.assertIsNotNone(result)
        self.assertEqual(
            result.buy_source_quantities,
            {"torn_item_market": 2, "tornw3b_bazaar": 3},
        )
        self.assertEqual(
            result.buy_source_costs,
            {"torn_item_market": 220, "tornw3b_bazaar": 300},
        )

    def test_excluded_buyer_reselects_next_best(self):
        listings = [BazaarListing("Item X", 100, 5, "source", seller_name="A")]
        offers = [
            BuyOffer("Item X", 180, "buyers", "EVETINE"),
            BuyOffer("Item X", 170, "buyers", "Trader B"),
        ]

        results = scan_arbitrage(
            listings,
            offers,
            min_profit_per_item=20,
            excluded_buyers={"EVETINE"},
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].buyer_name, "Trader B")
        self.assertEqual(results[0].buyer_price, 170)

    def test_max_opportunities_per_buyer_reallocates_rows(self):
        listings = [
            BazaarListing("Item A", 100, 5, "source", item_id="1"),
            BazaarListing("Item B", 100, 5, "source", item_id="2"),
        ]
        offers = [
            BuyOffer("Item A", 200, "buyers", "EVETINE", item_id="1"),
            BuyOffer("Item A", 190, "buyers", "Trader A", item_id="1"),
            BuyOffer("Item B", 180, "buyers", "EVETINE", item_id="2"),
            BuyOffer("Item B", 170, "buyers", "Trader B", item_id="2"),
        ]

        results = scan_arbitrage(
            listings,
            offers,
            min_profit_per_item=20,
            max_opportunities_per_buyer=1,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(sum(r.buyer_name == "EVETINE" for r in results), 1)
        self.assertEqual({r.buyer_name for r in results}, {"EVETINE", "Trader B"})

    def test_diversified_mode_uses_near_best_alternate(self):
        listings = [
            BazaarListing("Item A", 100, 5, "source", item_id="1"),
            BazaarListing("Item B", 100, 5, "source", item_id="2"),
        ]
        offers = [
            BuyOffer("Item A", 200, "buyers", "EVETINE", item_id="1"),
            BuyOffer("Item A", 150, "buyers", "Trader A", item_id="1"),
            BuyOffer("Item B", 190, "buyers", "EVETINE", item_id="2"),
            BuyOffer("Item B", 185, "buyers", "Trader B", item_id="2"),
        ]

        results = scan_arbitrage(
            listings,
            offers,
            min_profit_per_item=20,
            diversified=True,
        )

        by_item = {r.item_name: r for r in results}
        self.assertEqual(by_item["Item A"].buyer_name, "EVETINE")
        self.assertEqual(by_item["Item B"].buyer_name, "Trader B")

    def test_capital_budget_limits_executable_quantity(self):
        listings = [
            BazaarListing("Item X", 100, 10, "source", seller_name="A"),
            BazaarListing("Item X", 120, 10, "source", seller_name="B"),
        ]
        offer = BuyOffer("Item X", 180, "buyers", "Trader")

        result = evaluate_offer(
            listings,
            offer,
            min_profit_per_item=20,
            max_capital=650,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.quantity, 6)
        self.assertEqual(result.total_cost, 600)
        self.assertEqual(result.total_profit, 480)

    def test_min_total_profit_filters_small_execution(self):
        listings = [BazaarListing("Item X", 100, 5, "source")]
        offers = [BuyOffer("Item X", 150, "buyers", "Trader")]

        self.assertEqual(
            scan_arbitrage(
                listings,
                offers,
                min_profit_per_item=20,
                min_total_profit=300,
            ),
            [],
        )
        self.assertEqual(
            len(
                scan_arbitrage(
                    listings,
                    offers,
                    min_profit_per_item=20,
                    min_total_profit=200,
                )
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
