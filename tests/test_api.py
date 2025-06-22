import unittest
import time

import figgie_server.game as game_mod
import figgie_server.api as api_mod

# --- Endpoint integration tests ---
class TestAppEndpoints(unittest.TestCase):
    def setUp(self):
        self.app_module = api_mod
        self.app = api_mod.app
        self.game = game_mod.Game()
        api_mod.game = self.game
        self.app.game = self.game
        self.client = self.app.test_client()
        self.game.reset()
    
    def _join_all_players(self):
        for i in range(self.app_module.NUM_PLAYERS):
            rv = self.client.post('/join', json={'name': str(i)})
            self.assertEqual(rv.status_code, 200)

    def test_join_without_name(self):
        rv = self.client.post('/join', json={})
        self.assertEqual(rv.status_code, 400)
        data = rv.get_json()
        self.assertIn('Name is required', data.get('error', ''))

    def test_join_full_and_wrong_state(self):
        self._join_all_players()
        # Now state == 'trading'
        rv = self.client.post('/join', json={'name': 'extra'})
        self.assertEqual(rv.status_code, 400)
        self.assertIn('Cannot join right now', rv.get_json().get('error', ''))

    def test_state_errors(self):
        rv = self.client.get('/state')
        self.assertEqual(rv.status_code, 400)
        rv2 = self.client.get('/state', query_string={'player_id': 'bogus'})
        self.assertEqual(rv2.status_code, 400)

    def test_action_invalid_pid_and_state(self):
        rv = self.client.post('/action', json={'player_id': 'bogus'})
        self.assertEqual(rv.status_code, 400)
        self.assertIn('Invalid player_id', rv.get_json().get('error', ''))
        # Prepare trading state
        self._join_all_players()
        pid = next(iter(self.game.players))
        rv2 = self.client.post('/action', json={'player_id': pid})
        self.assertEqual(rv2.status_code, 400)
        rv3 = self.client.post('/action', json={'player_id': pid, 'action_type': 'foobar'})
        self.assertEqual(rv3.status_code, 400)

    def test_action_order_errors(self):
        self._join_all_players()
        pid = next(iter(self.game.players))
        base = {'player_id': pid, 'action_type': 'order'}
        r1 = self.client.post('/action', json={**base, 'order_type': 'foo', 'suit': 'spades'})
        self.assertEqual(r1.status_code, 400)
        r2 = self.client.post('/action', json={**base, 'order_type': 'buy', 'suit': 'invalid'})
        self.assertEqual(r2.status_code, 400)
        r3 = self.client.post('/action', json={**base, 'order_type': 'buy', 'suit': 'spades', 'price': 0})
        self.assertEqual(r3.status_code, 400)
        r4 = self.client.post('/action', json={**base, 'order_type': 'buy', 'suit': 'spades', 'price': 9999})
        self.assertEqual(r4.status_code, 400)
        r5 = self.client.post('/action', json={'player_id': pid, 'action_type': 'order', 'order_type': 'sell', 'suit': 'spades'})
        self.assertEqual(r5.status_code, 400)

    def test_order_and_cancel_happy_path(self):
        self._join_all_players()
        pids = list(self.game.players)
        buyer, seller = pids[0], pids[1]
        # setup
        self.game.players[seller].hand = {s: 0 for s in game_mod.SUITS}
        self.game.players[seller].hand['spades'] = 1
        self.game.players[buyer].money = 1000
        # buy
        resp1 = self.client.post('/action', json={'player_id': buyer, 'action_type': 'order', 'order_type': 'buy', 'suit': 'spades','price':50})
        self.assertEqual(resp1.status_code, 200)
        bid_oid = resp1.get_json().get('order_id')
        # sell
        resp2 = self.client.post('/action', json={'player_id': seller, 'action_type':'order','order_type':'sell','suit':'spades','price':50})
        self.assertEqual(resp2.status_code, 200)
        self.assertIn('trade', resp2.get_json())
        # cancel
        resp3 = self.client.post('/action', json={'player_id': buyer,'action_type':'order','order_type':'buy','suit':'clubs','price':20})
        oid2 = resp3.get_json().get('order_id')
        resp4 = self.client.post('/action', json={'player_id': buyer, 'action_type':'cancel', 'order_type':'buy', 'suit':'clubs', 'price': 20})
        self.assertEqual(resp4.status_code, 200)
        self.assertTrue(resp4.get_json().get('success'))

    def test_trading_timeout(self):
        self._join_all_players()
        pid = next(iter(self.game.players))
        self.game.start_time = time.time() - (game_mod.TRADING_DURATION + 1)
        rv = self.client.get('/state', query_string={'player_id': pid})
        self.assertEqual(rv.status_code, 200)
        data = rv.get_json()
        self.assertEqual(data.get('state'), 'completed')
        self.assertIn('results', data)

