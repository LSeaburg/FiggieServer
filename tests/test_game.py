import unittest
import time

from figgie_server.game import Game, SUITS, TRADING_DURATION
from figgie_server.models import Order, Player

class TestGame(unittest.TestCase):
    def setUp(self):
        self.game = Game()
        self.pid1 = 'p1'
        self.pid2 = 'p2'
        # initialize players with Player objects
        self.game.players = {
            self.pid1: Player(player_id=self.pid1, name='A'),
            self.pid2: Player(player_id=self.pid2, name='B')
        }

    def test_game_initialization(self):
        # reset game state to initial configuration
        self.game.reset()
        self.assertEqual(self.game.state, "waiting")
        self.assertEqual(self.game.players, {})
        self.assertEqual(self.game.orders, {})
        self.assertEqual(self.game.trades, [])
        self.assertEqual(self.game.pot, 0)
        self.assertIsNone(self.game.start_time)
        self.assertIsNone(self.game.suit_counts)
        self.assertIsNone(self.game.goal_suit)
        self.assertIsNone(self.game.results)

    def test_match_order_no_orders(self):
        ok, err, match = self.game.match_order(self.pid1, 'buy', SUITS[0], 10)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertIsNone(match)

    def test_match_order_buy_matches_ask(self):
        suit = SUITS[0]
        ask = Order(order_id='o1', player_id=self.pid2, type='sell', suit=suit, price=50)
        self.game.markets[suit].offers = [ask]
        ok, err, match = self.game.match_order(self.pid1, 'buy', suit, 60)
        self.assertTrue(ok)
        self.assertEqual(err, 'o1')
        self.assertEqual(match, ask)

    def test_match_order_self_reject(self):
        suit = SUITS[1]
        ask = Order(order_id='o2', player_id=self.pid1, type='sell', suit=suit, price=30)
        self.game.markets[suit].offers = [ask]
        ok, err, match = self.game.match_order(self.pid1, 'buy', suit, 40)
        self.assertFalse(ok)
        self.assertEqual(err, 'Reject Order')
        self.assertIsNone(match)

    def test_match_order_self_reject_sell(self):
        # test that a sell order is rejected when matching against own bid
        suit = SUITS[2]
        bid = Order(order_id='b3', player_id=self.pid1, type='buy', suit=suit, price=25)
        self.game.markets[suit].bids = [bid]
        ok, err, match = self.game.match_order(self.pid1, 'sell', suit, 25)
        self.assertFalse(ok)
        self.assertEqual(err, 'Reject Order')
        self.assertIsNone(match)

    def test_place_order_invalid(self):
        res, err = self.game.place_order(self.pid1, 'hold', SUITS[0], 10)
        self.assertIsNone(res)
        self.assertIn('Invalid order_type', err)
        res, err = self.game.place_order(self.pid1, 'buy', 'invalid', 10)
        self.assertIsNone(res)
        self.assertIn('Invalid suit', err)
        res, err = self.game.place_order(self.pid1, 'buy', SUITS[0], -5)
        self.assertIsNone(res)
        self.assertIn('Price must be a positive integer', err)

    def test_place_order_insufficient(self):
        res, err = self.game.place_order(self.pid1, 'buy', SUITS[0], 1000)
        self.assertIsNone(res)
        self.assertIn('Insufficient funds', err)
        res, err = self.game.place_order(self.pid1, 'sell', SUITS[0], 10)
        self.assertIsNone(res)
        self.assertIn('Not enough cards', err)

    def test_place_order_duplicate(self):
        # first order
        res, err = self.game.place_order(self.pid1, 'buy', SUITS[0], 10)
        self.assertIsNotNone(res)
        self.assertIn('order_id', res)
        res, err = self.game.place_order(self.pid1, 'buy', SUITS[0], 10)
        self.assertIsNone(res)
        self.assertIn('Duplicate order', err)

    def test_place_order_trade_execution(self):
        # reset and setup buyer seller
        self.game = Game()
        # give seller one card of suit
        suit = SUITS[0]
        self.game.players = {
            self.pid1: Player(player_id=self.pid1, name='A', money=100),
            self.pid2: Player(player_id=self.pid2, name='B', money=100)
        }
        self.game.players[self.pid2].hand = {s:0 for s in SUITS}
        self.game.players[self.pid2].hand[suit] = 1
        # buyer places buy
        res_bid, err_bid = self.game.place_order(self.pid1, 'buy', suit, 20)
        self.assertIn('order_id', res_bid)
        # seller places matching sell
        res_sell, err_sell = self.game.place_order(self.pid2, 'sell', suit, 20)
        self.assertIn('trade', res_sell)
        trade = res_sell['trade']
        self.assertEqual(trade['buyer'], self.pid1)
        self.assertEqual(trade['seller'], self.pid2)
        self.assertFalse(self.game.orders)
        self.assertFalse(self.game.markets[suit].bids)
        self.assertFalse(self.game.markets[suit].offers)

    def test_cancel_order(self):
        # add buy and sell orders
        suit = SUITS[1]
        o1 = Order(order_id='c1', player_id=self.pid1, type='buy', suit=suit, price=10)
        o2 = Order(order_id='c2', player_id=self.pid1, type='sell', suit=suit, price=5)
        self.game.orders = {'c1': o1, 'c2': o2}
        self.game.markets[suit].bids.append(o1)
        self.game.markets[suit].offers.append(o2)
        res, err = self.game.cancel_order(self.pid1, 'both', 'all', -1)
        self.assertEqual(set(res['canceled']), {'c1', 'c2'})
        self.assertFalse(self.game.orders)
        self.assertFalse(self.game.markets[suit].bids)
        self.assertFalse(self.game.markets[suit].offers)

    def test_get_state_various(self):
        # waiting
        st = self.game.get_state(self.pid1)
        self.assertEqual(st['state'], 'waiting')
        self.assertIsNone(st['time_left'])
        # trading half time
        self.game.state = 'trading'
        self.game.start_time = time.time() - (TRADING_DURATION / 2)
        self.game.pot = 100
        suit = SUITS[0]
        bid = Order(order_id='b1', player_id=self.pid1, type='buy', suit=suit, price=30)
        ask = Order(order_id='a1', player_id=self.pid1, type='sell', suit=suit, price=50)
        self.game.markets[suit].bids = [bid]
        self.game.markets[suit].offers = [ask]
        st2 = self.game.get_state(self.pid1)
        self.assertEqual(st2['state'], 'trading')
        self.assertTrue(0 < st2['time_left'] < 240)
        self.assertEqual(st2['market'][suit]['highest_bid']['price'], 30)
        self.assertEqual(st2['market'][suit]['lowest_ask']['price'], 50)
        # expired yields completed
        self.game.start_time = time.time() - (TRADING_DURATION + 1)
        st3 = self.game.get_state(self.pid1)
        self.assertEqual(st3['state'], 'completed')
        self.assertIn('results', st3)
        self.assertIn('hands', st3)

    def test_place_order_sell_insertion(self):
        # Test ascending insertion of sell orders (covers lines 190-196 in game.py)
        suit = SUITS[0]
        # ensure player has enough cards to sell
        # initialize hand with 0 for all suits then 3 cards for test suit
        self.game.players[self.pid1].hand = {s: 0 for s in SUITS}
        self.game.players[self.pid1].hand[suit] = 3
        # place multiple sell orders with varying prices
        prices = [50, 20, 30]
        order_ids = []
        for price in prices:
            res, err = self.game.place_order(self.pid1, 'sell', suit, price)
            self.assertIsNotNone(res, f"Failed to place sell order at price {price}: {err}")
            order_ids.append(res['order_id'])
        # verify market.offers sorted in ascending order by price
        offers = self.game.markets[suit].offers
        self.assertEqual([o.price for o in offers], sorted(prices))
        # verify orders dict contains all placed orders
        self.assertEqual(set(order_ids), set(self.game.orders.keys()))

    def test_same_price_bid_priority(self):
        # two buyers place bids at the same price; the one who bid first should win
        game = Game()
        pid1 = 'b1'
        pid2 = 'b2'
        seller = 's1'

        # initialize players
        for pid in (pid1, pid2, seller):
            game.players[pid] = Player(player_id=pid, name=pid, money=100)
            game.players[pid].hand = {s: 0 for s in SUITS}
        # give the seller one card to sell
        suit = SUITS[0]
        game.players[seller].hand[suit] = 1

        # both buyers place a bid at price 30
        res1, err1 = game.place_order(pid1, 'buy', suit, 30)
        self.assertIsNotNone(res1)
        self.assertIsNone(err1)

        res2, err2 = game.place_order(pid2, 'buy', suit, 30)
        self.assertIsNotNone(res2)
        self.assertIsNone(err2)

        # now the seller places a matching sell
        res_sell, err_sell = game.place_order(seller, 'sell', suit, 30)
        self.assertIsNone(err_sell)
        trade = res_sell.get('trade')
        # confirm that pid1 (the first bidder) is the buyer in the trade
        self.assertEqual(trade['buyer'], pid1)
        self.assertEqual(trade['seller'], seller)

    def test_same_price_offer_priority(self):
        # two sellers place asks at the same price; the one who asked first should get matched first
        game = Game()
        # setup two sellers and one buyer
        s1, s2, buyer = 's1', 's2', 'b1'
        for pid in (s1, s2, buyer):
            game.players[pid] = Player(player_id=pid, name=pid, money=100)
            game.players[pid].hand = {s: 0 for s in SUITS}
        # give each seller one card of the suit
        suit = SUITS[0]
        game.players[s1].hand[suit] = 1
        game.players[s2].hand[suit] = 1
        price = 40
        # both sellers place sell orders at the same price
        res1, err1 = game.place_order(s1, 'sell', suit, price)
        self.assertIsNotNone(res1)
        self.assertIsNone(err1)
        res2, err2 = game.place_order(s2, 'sell', suit, price)
        self.assertIsNotNone(res2)
        self.assertIsNone(err2)
        # buyer places matching buy order
        res_buy, err_buy = game.place_order(buyer, 'buy', suit, price)
        self.assertIsNone(err_buy)
        trade = res_buy.get('trade')
        # the seller with the earlier ask (s1) should be the one who sold
        self.assertEqual(trade['seller'], s1)
        self.assertEqual(trade['buyer'], buyer)


