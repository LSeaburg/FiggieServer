import unittest
from unittest.mock import patch, MagicMock

from agents.figgie_interface import FiggieInterface, State, Order, Trade

class TestFiggieInterface(unittest.TestCase):
    def setUp(self):
        self.server_url = "http://testserver"
        self.agent_name = "TestAgent"
        self.player_id = "test_player_id"
        # minimal initial payload
        self.initial_state = {
            "state": "waiting",
            "trades": [],
            "market": {},
            "time_left": None,
        }

    def _make_join_response(self) -> MagicMock:
        join_resp = MagicMock()
        join_resp.raise_for_status.return_value=None
        join_resp.json.return_value={'player_id': self.player_id}
        return join_resp

    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.FiggieInterface._start_polling')
    def test_init_joins_game_and_starts_polling(self, mock_start, mock_post):
        # join returns player_id
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"player_id": self.player_id}
        mock_post.return_value = mock_resp

        iface = FiggieInterface(self.server_url, self.agent_name)
        mock_post.assert_called_once_with(
            f"{self.server_url}/join", json={"name": self.agent_name}
        )
        self.assertEqual(iface.player_id, self.player_id)
        mock_start.assert_called_once()

    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.requests.get')
    def test_get_state_parses_dataclass(self, mock_get, mock_post):
        # mock join
        join_resp = self._make_join_response()
        mock_post.return_value = join_resp
        # mock get
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = self.initial_state
        mock_get.return_value = mock_resp

        with patch('agents.figgie_interface.FiggieInterface._start_polling'):
            iface = FiggieInterface(self.server_url, self.agent_name)
        state = iface._get_state()
        mock_get.assert_called_once_with(
            f"{self.server_url}/state", params={"player_id": self.player_id}
        )
        self.assertIsInstance(state, State)
        self.assertEqual(state.state, "waiting")
        self.assertEqual(state.time_left, None)
        self.assertListEqual(state.trades, [])
        self.assertEqual(state.market, {})

    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.requests.get')
    @patch('agents.figgie_interface.FiggieInterface._start_polling')
    def test_process_state_triggers_events(self, mock_start, mock_get, mock_post):
        # mock join
        join_resp = self._make_join_response()
        mock_post.return_value = join_resp
        with patch('agents.figgie_interface.FiggieInterface._start_polling'):
            iface = FiggieInterface(self.server_url, self.agent_name)
        # tick
        tick_fn = MagicMock()
        iface.on_tick(tick_fn)
        s1 = State(state='trading', time_left=5, hand=None, market={}, trades=[])
        iface._process_state(s1)
        tick_fn.assert_called_once_with(5)
        # start
        start_fn = MagicMock()
        iface.on_start(start_fn)
        s2_prev = State(state='waiting', time_left=None, hand=None, market={}, trades=[])
        s2 = State(state='trading', time_left=None, hand={'a':1}, market={}, trades=[])
        iface._last_state = s2_prev
        iface._process_state(s2)
        start_fn.assert_called_once_with({'a':1})
        # bid & offer
        bid_fn = MagicMock()
        offer_fn = MagicMock()
        iface.on_bid(bid_fn)
        iface.on_offer(offer_fn)
        m_prev = State(state='trading', time_left=None, hand=None, market={'x':{}}, trades=[])
        m_curr = State(state='trading', time_left=None, hand=None,
                       market={'x':{'highest_bid':{'player_id':'B','price':7}, 'lowest_ask':None}}, trades=[])
        iface._last_state = m_prev
        iface._process_state(m_curr)
        bid_fn.assert_called_once_with('B',7,'x')
        # transaction
        transaction_fn = MagicMock()
        iface.on_transaction(transaction_fn)
        trades = [Trade(buyer='A',seller='C',price=10,suit='h')]
        t_state = State(state='trading', time_left=None, hand=None, market={}, trades=trades)
        iface._last_state = State(state=None, time_left=None, hand=None, market={}, trades=[])
        iface._last_trade_index=0
        iface._process_state(t_state)
        transaction_fn.assert_called_once_with('A','C',10,'h')


    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.FiggieInterface._start_polling')
    def test_bid_and_offer_methods(self, mock_start, mock_post):
        # join and action responses
        join_resp = self._make_join_response()
        action_resp = MagicMock()
        action_resp.raise_for_status.return_value=None
        action_resp.json.return_value={'result': 'ok'}
        mock_post.side_effect = [join_resp, action_resp]

        iface = FiggieInterface(self.server_url, self.agent_name)
        # test bid
        result_bid = iface.bid(15, 's')
        self.assertEqual(result_bid, {'result': 'ok'})
        # second post should be action
        mock_post.assert_called_with(
            f"{self.server_url}/action",
            json={'type': 'order', 'player_id': self.player_id, 'order_type': 'buy', 'suit': 's', 'price': 15}
        )
        # test offer
        mock_post.reset_mock()
        mock_post.side_effect = [join_resp, action_resp]
        iface2 = FiggieInterface(self.server_url, self.agent_name)
        result_offer = iface2.offer(20, 'h')
        self.assertEqual(result_offer, {'result': 'ok'})
        mock_post.assert_called_with(
            f"{self.server_url}/action",
            json={'type': 'order', 'player_id': self.player_id, 'order_type': 'sell', 'suit': 'h', 'price': 20}
        )

    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.FiggieInterface._start_polling')
    def test_buy_and_sell_methods_and_errors(self, mock_start, mock_post):
        # patch join
        join_resp = self._make_join_response()
        mock_post.return_value = join_resp
        iface = FiggieInterface(self.server_url, self.agent_name)
        # no state yet
        iface._last_state = None
        with self.assertRaisesRegex(RuntimeError, 'No state yet'):
            iface.buy('x')
        with self.assertRaisesRegex(RuntimeError, 'No state yet'):
            iface.sell('x')
        # state with no offers/bids
        iface._last_state = State(state=None, time_left=None, hand=None, market={}, trades=[])
        with self.assertRaisesRegex(RuntimeError, 'No offers'):
            iface.buy('x')
        with self.assertRaisesRegex(RuntimeError, 'No bids'):
            iface.sell('x')
        # happy paths by patching bid/offer
        iface._last_state = State(state=None, time_left=None, hand=None,
                                   market={'y': {'lowest_ask': {'player_id':'Z','price':30}, 'highest_bid': {'player_id':'Y','price':25}}}, trades=[])
        iface.bid = MagicMock(return_value='bid_ok')
        iface.offer = MagicMock(return_value='offer_ok')
        res_buy = iface.buy('y')
        self.assertEqual(res_buy, 'bid_ok')
        iface.bid.assert_called_with(30, 'y')
        res_sell = iface.sell('y')
        self.assertEqual(res_sell, 'offer_ok')
        iface.offer.assert_called_with(25, 'y')

    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.FiggieInterface._start_polling')
    def test_cancel_methods(self, mock_start, mock_post):
        join_resp = self._make_join_response()
        cancel_resp = MagicMock()
        cancel_resp.raise_for_status.return_value=None
        cancel_resp.json.return_value={'canceled': ['id1', 'id2']}
        mock_post.side_effect = [join_resp, cancel_resp]
        iface = FiggieInterface(self.server_url, self.agent_name)
        res = iface.cancel_bids_and_offers('t')
        self.assertEqual(res, ['id1', 'id2'])
        mock_post.assert_called_with(
            f"{self.server_url}/action",
            json={'type': 'cancel', 'player_id': self.player_id, 'order_type': 'both', 'suit': 't', 'price': -1}
        )
        # test cancel_all
        mock_post.reset_mock()
        mock_post.side_effect = [join_resp, cancel_resp]
        iface2 = FiggieInterface(self.server_url, self.agent_name)
        res2 = iface2.cancel_all_bids_and_offers()
        self.assertEqual(res2, ['id1', 'id2'])
        mock_post.assert_called_with(
            f"{self.server_url}/action",
            json={'type': 'cancel', 'player_id': self.player_id, 'order_type': 'both', 'suit': 'all', 'price': -1}
        )

    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.FiggieInterface._start_polling')
    def test_dataclasses_and_defaults(self, mock_start, mock_post):
        # Test Order and Trade dataclasses
        order = Order(order_id='o1', player_id='p1', type='buy', suit='s', price=50)
        self.assertEqual(order.order_id, 'o1')
        self.assertEqual(order.player_id, 'p1')
        self.assertEqual(order.type, 'buy')
        self.assertEqual(order.suit, 's')
        self.assertEqual(order.price, 50)
        trade = Trade(buyer='b1', seller='s1', price=100, suit='h')
        self.assertEqual(trade.buyer, 'b1')
        self.assertEqual(trade.seller, 's1')
        self.assertEqual(trade.price, 100)
        self.assertEqual(trade.suit, 'h')
        # Test State defaults
        state = State(state='done', time_left=0.0)
        self.assertIsNone(state.pot)
        self.assertIsNone(state.hand)
        self.assertEqual(state.market, {})
        self.assertEqual(state.balances, {})
        self.assertEqual(state.trades, [])
        self.assertIsNone(state.results)
        self.assertIsNone(state.hands)

    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.FiggieInterface._start_polling')
    def test_transaction_indexing_prevents_duplicates(self, mock_start, mock_post):
        join_resp = self._make_join_response()
        mock_post.return_value = join_resp
        iface = FiggieInterface(self.server_url, self.agent_name)
        transaction_fn = MagicMock()
        iface.on_transaction(transaction_fn)
        t1 = Trade(buyer='A', seller='B', price=10, suit='d')
        t2 = Trade(buyer='C', seller='D', price=20, suit='h')
        state1 = State(state=None, time_left=None, hand=None, market={}, trades=[t1, t2])
        iface._last_state = State(state=None, time_left=None, hand=None, market={}, trades=[])
        iface._last_trade_index = 0
        iface._process_state(state1)
        self.assertEqual(transaction_fn.call_count, 2)
        transaction_fn.reset_mock()
        iface._last_trade_index = 2
        iface._process_state(state1)
        transaction_fn.assert_not_called()

    @patch('agents.figgie_interface.requests.post')
    @patch('agents.figgie_interface.FiggieInterface._start_polling')
    def test_cancel_returns_empty_if_no_state(self, mock_start, mock_post):
        join_resp = self._make_join_response()
        mock_post.return_value = join_resp
        iface = FiggieInterface(self.server_url, self.agent_name)
        iface._last_state = None
        res = iface.cancel_bids_and_offers('any')
        self.assertEqual(res, [])
