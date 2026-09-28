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
        self.assertEqual(result.total_cost, 32_240_000)
        self.assertEqual(result.total_revenue, 35_350_000)
        self.assertEqual(result.total_profit, 3_110_000)
        self.assertAlmostEqual(result.average_buy_price, 460_571.4285714286)
        self.assertAlmostEqual(result.average_profit_per_item, 44_428.57142857143)

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


if __name__ == "__main__":
    unittest.main()
