import unittest
from unittest.mock import patch, MagicMock

import agents.traders.fundamentalist as fund
from agents.traders.fundamentalist import Fundamentalist, Market


class TestFundamentalist(unittest.TestCase):
    def setUp(self):
        self.server_url = "http://testserver"
        self.agent_name = "Fundy"
        self.player_id = "test_player_id"
        # a reasonable, deterministic starting hand
        self.start_hand = {s: 3 for s in fund.SUITS}
        self.start_hand[fund.SUITS[0]] = 1
        self.start_hand[fund.SUITS[2]] = 2
        self.opponents = {"p2", "p3", "p4"}

    def _make_join_response(self) -> MagicMock:
        join_resp = MagicMock()
        join_resp.raise_for_status.return_value = None
        join_resp.json.return_value = {"player_id": self.player_id}
        return join_resp

    @patch("agents.figgie_interface.requests.post")
    @patch("agents.figgie_interface.FiggieInterface._start_polling")
    def test_start_initializes_state_and_probabilities(self, mock_start, mock_post):
        mock_post.return_value = self._make_join_response()
        agent = Fundamentalist(self.server_url, self.agent_name, polling_rate=0.1)

        agent._handle_start(self.start_hand, self.opponents)

        # self and opponents are tracked
        self.assertIn(agent.player_id, agent.initial_hand)
        for pid in self.opponents:
            self.assertIn(pid, agent.initial_hand)
            self.assertIn(pid, agent.bought_cards)
            self.assertIn(pid, agent.peek_offers)

        # hand copied
        self.assertEqual(agent.hand, self.start_hand)

        # market initialized per suit
        self.assertEqual(set(agent.market.keys()), set(fund.SUITS))
        self.assertTrue(all(isinstance(m, Market) for m in agent.market.values()))

        # deck probabilities exist and sum to ~1
        self.assertEqual(len(agent.deck_probabilities), len(fund.POSSIBLE_DECKS))
        self.assertAlmostEqual(sum(agent.deck_probabilities.values()), 1.0, places=7)

    @patch("agents.figgie_interface.requests.post")
    @patch("agents.figgie_interface.FiggieInterface._start_polling")
    def test_get_exp_val_monotonic_with_hand(self, mock_start, mock_post):
        mock_post.return_value = self._make_join_response()
        agent = Fundamentalist(self.server_url, self.agent_name, polling_rate=0.1, buy_ratio=1.7)
        agent._handle_start(self.start_hand, self.opponents)

        # make probabilities uniform to avoid dependence on combinatorics of seen cards
        uniform = 1.0 / len(fund.POSSIBLE_DECKS)
        agent.deck_probabilities = {fund.dict_to_key(d): uniform for d in fund.POSSIBLE_DECKS}

        suit = fund.SUITS[0]

        agent.hand[suit] = 0
        v0 = agent._get_exp_val(suit, "buy")
        agent.hand[suit] = 1
        v1 = agent._get_exp_val(suit, "buy")
        # with more of the suit already, expected marginal value should not increase
        self.assertLessEqual(v1, v0)

        # sell path should delegate to buy and return an int >= 1
        agent.hand[suit] = 2
        vs = agent._get_exp_val(suit, "sell")
        self.assertIsInstance(vs, int)
        self.assertGreaterEqual(vs, 1)

    @patch("agents.figgie_interface.requests.post")
    @patch("agents.figgie_interface.FiggieInterface._start_polling")
    def test_offer_updates_peek_and_probabilities(self, mock_start, mock_post):
        mock_post.return_value = self._make_join_response()
        agent = Fundamentalist(self.server_url, self.agent_name, polling_rate=0.1)
        agent._handle_start(self.start_hand, self.opponents)

        opponent = next(iter(self.opponents))
        suit = fund.SUITS[1]

        # Initially no peeks and no purchases
        self.assertFalse(agent.peek_offers[opponent][suit])
        self.assertEqual(agent.bought_cards[opponent][suit], 0)

        # Spy on probability update
        agent._update_deck_probabilities = MagicMock(side_effect=agent._update_deck_probabilities)

        # First offer from opponent should set peek and trigger probability recompute
        agent._handle_offer(opponent, price=10, suit=suit)
        self.assertTrue(agent.peek_offers[opponent][suit])
        self.assertGreater(agent._update_deck_probabilities.call_count, 0)

        # Subsequent offer should not trigger another recompute if already peeked
        call_count_before = agent._update_deck_probabilities.call_count
        agent._handle_offer(opponent, price=11, suit=suit)
        self.assertEqual(agent._update_deck_probabilities.call_count, call_count_before)

        # If opponent has bought that suit, peeks should not be set when false
        other = list(self.opponents - {opponent})[0]
        agent.peek_offers[other][suit] = False
        agent.bought_cards[other][suit] = 1
        agent._handle_offer(other, price=12, suit=suit)
        self.assertFalse(agent.peek_offers[other][suit])

    @patch("agents.figgie_interface.requests.post")
    @patch("agents.figgie_interface.FiggieInterface._start_polling")
    def test_trade_and_cancel_handlers(self, mock_start, mock_post):
        mock_post.return_value = self._make_join_response()
        agent = Fundamentalist(self.server_url, self.agent_name, polling_rate=0.1)
        agent._handle_start(self.start_hand, self.opponents)

        suit = fund.SUITS[2]
        opponent = next(iter(self.opponents))

        # trade where self is buyer
        before = agent.hand[suit]
        agent._handle_trade(buyer=agent.player_id, seller=opponent, _=15, suit=suit)
        self.assertEqual(agent.hand[suit], before + 1)
        # market should be reset
        self.assertTrue(all(isinstance(m, Market) for m in agent.market.values()))

        # trade where self is seller
        agent.hand[suit] = 2
        agent._handle_trade(buyer=opponent, seller=agent.player_id, _=18, suit=suit)
        self.assertEqual(agent.hand[suit], 1)

        # trade where seller is opponent without prior buys -> peek reset and initial hand incremented
        agent.peek_offers[opponent][suit] = True
        agent.bought_cards[opponent][suit] = 0
        prev_initial = agent.initial_hand[opponent][suit]
        agent._handle_trade(buyer=agent.player_id, seller=opponent, _=20, suit=suit)
        self.assertFalse(agent.peek_offers[opponent][suit])
        self.assertEqual(agent.initial_hand[opponent][suit], prev_initial + 1)

        # cancel updates quotes correctly
        agent.market[suit].highest_bid = 10
        agent.market[suit].lowest_ask = 30
        agent._handle_cancel("bid", "old", 10, None, 8, suit)
        self.assertEqual(agent.market[suit].highest_bid, 8)
        agent._handle_cancel("offer", "old", 30, None, 35, suit)
        self.assertEqual(agent.market[suit].lowest_ask, 35)

    @patch("agents.figgie_interface.requests.post")
    @patch("agents.figgie_interface.FiggieInterface._start_polling")
    def test_tick_behavior_buy_and_sell(self, mock_start, mock_post):
        mock_post.return_value = self._make_join_response()
        agent = Fundamentalist(self.server_url, self.agent_name, polling_rate=0.1)
        agent._handle_start(self.start_hand, self.opponents)

        suit = fund.SUITS[0]

        # Skip path when aggression is 0.0
        agent.aggression = 0.0
        agent.bid = MagicMock()
        agent.offer = MagicMock()
        with patch("agents.traders.fundamentalist.random.random", return_value=0.5):
            agent._handle_tick(None)
        agent.bid.assert_not_called()
        agent.offer.assert_not_called()

        # Buy path
        agent.aggression = 1.0
        agent.market[suit].lowest_ask = 7
        agent._get_exp_val = MagicMock(return_value=10)
        agent.bid = MagicMock()
        with patch("agents.traders.fundamentalist.random.random", return_value=0.0), \
             patch("agents.traders.fundamentalist.random.choice", side_effect=["buy", suit]), \
             patch("agents.traders.fundamentalist.random.randint", return_value=5):
            agent._handle_tick(None)
        agent.bid.assert_called_once_with(5, suit)

        # Sell path (ensure we have at least 1 card to sell)
        agent.hand[suit] = 1
        agent.market[suit].highest_bid = 12
        agent._get_exp_val = MagicMock(return_value=7)
        agent.offer = MagicMock()
        with patch("agents.traders.fundamentalist.random.random", return_value=0.0), \
             patch("agents.traders.fundamentalist.random.choice", side_effect=["sell", suit]), \
             patch("agents.traders.fundamentalist.random.randint", return_value=10):
            agent._handle_tick(None)
        agent.offer.assert_called_once_with(12, suit)

    @patch("agents.figgie_interface.requests.post")
    @patch("agents.figgie_interface.FiggieInterface._start_polling")
    def test_peek_and_initial_hand(self, mock_start, mock_post):
        mock_post.return_value = self._make_join_response()
        agent = Fundamentalist(self.server_url, self.agent_name, polling_rate=0.1)
        agent._handle_start(self.start_hand, self.opponents)

        opponent1 = next(iter(self.opponents))
        opponent2 = next(iter(self.opponents - {opponent1}))
        opponent3 = next(iter(self.opponents - {opponent1, opponent2}))
        suit = fund.SUITS[1]

        # Initially no peeks and no purchases
        self.assertFalse(agent.peek_offers[opponent1][suit])
        self.assertEqual(agent.initial_hand[opponent1][suit], 0)

        self.assertFalse(agent.peek_offers[opponent2][suit])
        self.assertEqual(agent.initial_hand[opponent2][suit], 0)

        # First offer from opponent should set peek and trigger probability recompute
        agent._handle_offer(opponent1, price=10, suit=suit)
        self.assertTrue(agent.peek_offers[opponent1][suit])
        self.assertEqual(agent.initial_hand[opponent1][suit], 0)

        agent._handle_trade(buyer=opponent2, seller=opponent1, _=12, suit=suit)
        self.assertFalse(agent.peek_offers[opponent1][suit])
        self.assertFalse(agent.peek_offers[opponent2][suit])
        self.assertEqual(agent.initial_hand[opponent1][suit], 1)
        self.assertEqual(agent.initial_hand[opponent2][suit], 0)

        # If opponent has bought that suit, peeks should not be set
        agent._handle_offer(opponent2, price=11, suit=suit)
        self.assertFalse(agent.peek_offers[opponent2][suit])
        self.assertEqual(agent.initial_hand[opponent2][suit], 0)

        agent._handle_offer(opponent1, price=10, suit=suit)
        self.assertTrue(agent.peek_offers[opponent1][suit])
        self.assertEqual(agent.initial_hand[opponent1][suit], 1)

        agent._handle_offer(opponent3, price=9, suit=suit)
        self.assertTrue(agent.peek_offers[opponent3][suit])
        self.assertEqual(agent.initial_hand[opponent3][suit], 0)

        agent._handle_trade(buyer=opponent2, seller=opponent1, _=8, suit=suit)
        agent._handle_trade(buyer=opponent1, seller=agent.player_id, _=10, suit=suit)
        agent._handle_trade(buyer=opponent3, seller=opponent1, _=10, suit=suit)

        self.assertEqual(agent.initial_hand[opponent1][suit], 2)
        self.assertEqual(agent.initial_hand[opponent2][suit], 0)
        self.assertEqual(agent.initial_hand[opponent3][suit], 0)
        self.assertFalse(agent.peek_offers[opponent1][suit])
        self.assertFalse(agent.peek_offers[opponent2][suit])
        self.assertTrue(agent.peek_offers[opponent3][suit])


if __name__ == "__main__":
    unittest.main()


