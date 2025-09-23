import unittest
from unittest.mock import patch, MagicMock

import agents.traders.hand_reading as hr
from agents.traders.hand_reading import HandReading


class TestHandReading(unittest.TestCase):
    def setUp(self):
        self.server_url = "http://testserver"
        self.agent_name = "HandReader"
        self.player_id = "test_player_id"
        # deterministic starting hand
        self.start_hand = {s: 3 for s in hr.SUITS}
        self.start_hand[hr.SUITS[0]] = 1
        self.start_hand[hr.SUITS[2]] = 2
        self.opponents = {"p2", "p3", "p4"}

    def _make_join_response(self) -> MagicMock:
        join_resp = MagicMock()
        join_resp.raise_for_status.return_value = None
        join_resp.json.return_value = {"player_id": self.player_id}
        return join_resp

    @patch("agents.figgie_interface.requests.post")
    @patch("agents.figgie_interface.FiggieInterface._start_polling")
    def test_peek_and_initial_hand(self, mock_start, mock_post):
        mock_post.return_value = self._make_join_response()
        agent = HandReading(self.server_url, self.agent_name, polling_rate=0.1)
        agent._handle_start(self.start_hand, self.opponents)

        opponent1 = next(iter(self.opponents))
        opponent2 = next(iter(self.opponents - {opponent1}))
        opponent3 = next(iter(self.opponents - {opponent1, opponent2}))
        suit = hr.SUITS[1]

        # Initially no peeks and no known initials
        self.assertFalse(agent.peek_offers[opponent1][suit])
        self.assertEqual(agent.known_initials[opponent1][suit], 0)

        self.assertFalse(agent.peek_offers[opponent2][suit])
        self.assertEqual(agent.known_initials[opponent2][suit], 0)

        # First offer from opponent should set peek
        agent._handle_offer(opponent1, price=10, suit=suit)
        self.assertTrue(agent.peek_offers[opponent1][suit])
        self.assertEqual(agent.known_initials[opponent1][suit], 0)

        # Trade: opponent2 buys from opponent1 => seller's card was from starting hand
        agent._handle_trade(buyer=opponent2, seller=opponent1, price=12, suit=suit)
        self.assertFalse(agent.peek_offers[opponent1][suit])
        self.assertFalse(agent.peek_offers[opponent2][suit])
        self.assertEqual(agent.known_initials[opponent1][suit], 1)
        self.assertEqual(agent.known_initials[opponent2][suit], 0)

        # If opponent has bought that suit, peeks should not be set
        agent._handle_offer(opponent2, price=11, suit=suit)
        self.assertFalse(agent.peek_offers[opponent2][suit])
        self.assertEqual(agent.known_initials[opponent2][suit], 0)

        # Offers from others set peek but do not change known initials
        agent._handle_offer(opponent1, price=10, suit=suit)
        self.assertTrue(agent.peek_offers[opponent1][suit])
        self.assertEqual(agent.known_initials[opponent1][suit], 1)

        agent._handle_offer(opponent3, price=9, suit=suit)
        self.assertTrue(agent.peek_offers[opponent3][suit])
        self.assertEqual(agent.known_initials[opponent3][suit], 0)

        # More trades: seller opponent1 twice, and opponent1 buys once in between
        agent._handle_trade(buyer=opponent2, seller=opponent1, price=8, suit=suit)
        agent._handle_trade(buyer=opponent1, seller=agent.player_id, price=10, suit=suit)
        agent._handle_trade(buyer=opponent3, seller=opponent1, price=10, suit=suit)

        # After alignment with Fundamentalist logic, the buy in between
        # consumes one sale attribution. Expect total 2.
        self.assertEqual(agent.known_initials[opponent1][suit], 2)
        self.assertEqual(agent.known_initials[opponent2][suit], 0)
        self.assertEqual(agent.known_initials[opponent3][suit], 0)
        self.assertFalse(agent.peek_offers[opponent1][suit])
        self.assertFalse(agent.peek_offers[opponent2][suit])
        self.assertTrue(agent.peek_offers[opponent3][suit])


if __name__ == "__main__":
    unittest.main()


