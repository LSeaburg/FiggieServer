import math
import random
import requests
from dataclasses import dataclass
from typing import Dict, Optional, Set, Any, Literal

from figgie_interface import FiggieInterface

SUITS = ["spades", "clubs", "hearts", "diamonds"]
SUIT_COLORS: Dict[str, str] = {
    "spades": "black",
    "clubs": "black",
    "hearts": "red",
    "diamonds": "red"
}

def dict_to_key(d):
    return tuple(sorted(d.items()))

@dataclass
class Market:
    """
    Represents current best bid and ask for a suit.
    """
    highest_bid: Optional[int] = None
    lowest_ask: Optional[int] = None

class Fundamentalist(FiggieInterface):
    """
    A fundamentalist trading agent based on the model in https://arxiv.org/pdf/2110.00879.
    """
    def __init__(
        self,
        server_url: str,
        name: str,
        polling_rate: float = 1.0,
        aggression: float = 0.5,
        buy_ratio: float = 1.7
    ) -> None:
        """
        Initialize the Fundamentalist agent.

        Args:
            server_url: URL of the Figgie server.
            name: Unique name for this agent.
            polling_rate: Seconds between polling cycles.
            aggression: Probability [0,1] of acting on each tick.
            buy_ratio: Parameter controlling bidding aggressiveness.  Should be greater than 1.
        """
        super().__init__(server_url, name, polling_rate)
        self.aggression: float = aggression
        self.buy_ratio: float = buy_ratio

        # Market quotes by suit
        self.market: Dict[str, Market] = {suit: Market() for suit in SUITS}
        # Current player hand counts by suit
        self.hand: Dict[str, int] = {}
        # Initial hand counts for all players
        self.initial_hand: Dict[str, Dict[str, int]] = {}
        # Flags for whether we've peeked an opponent's offer
        self.peek_offers: Dict[str, Dict[str, bool]] = {}
        # Tracks how many cards each opponent has bought
        self.bought_cards: Dict[str, Dict[str, int]] = {}
        # Caches multinomials for faster compute
        self.multinomials: Dict[tuple, float] = {}

        # Register event handlers
        # The tick handler will be registered once trading starts
        # self.on_tick(self._handle_tick)
        self.on_start(self._handle_start)
        self.on_bid(self._handle_bid)
        self.on_offer(self._handle_offer)
        self.on_transaction(self._handle_trade)
        self.on_cancel(self._handle_cancel)

    def _total_known_cards(self) -> Dict[str, int]:  # type: ignore
        """
        Calculate total observed cards for each suit.

        Combines your initial hand and opponents known initial hands
        that were traded plus any peeks of opponent offers.

        Returns:
            Mapping of suit to count of seen cards.
        """
        total: Dict[str, int] = {suit: 0 for suit in SUITS}
        # Count initial hand for all players
        for hand in self.initial_hand.values():
            for suit, cnt in hand.items():
                total[suit] += cnt
        # Count peeks of opponent offers
        for state in self.peek_offers.values():
            for suit, seen in state.items():
                if seen:
                    total[suit] += 1
        return total

    def _update_multinomials(self) -> None:
        """
        Compute normalized multinomial probability weight.
        """
        self.multinomials.clear()
        seen_cards = self._total_known_cards()

        m_values = dict()

        for twelve in SUITS:
            for eight in set(SUITS) - {twelve}:
                deck = {s: 10 for s in SUITS}
                deck[twelve] = 12
                deck[eight] = 8

                m = 1
                for suit in SUITS:
                    k = seen_cards[suit]
                    n = deck[suit]
                    if k > n:
                        m = 0
                        break
                    m *= math.comb(n, k)

                m_values[dict_to_key(deck)] = m

        total = sum(m_values.values())

        for deck, m in m_values.items():
            self.multinomials[deck] = m / total

    def _get_exp_val(
        self,
        suit: str,
        order: Literal['buy', 'sell']
    ) -> int:
        """
        Compute expected value for placing an order.
        """
        if order == "sell":
            self.hand[suit] -= 1
            res = self._get_exp_val(suit, "buy")
            self.hand[suit] += 1
            return res

        color = SUIT_COLORS[suit]
        twelve = next(s for s in SUITS if s != suit and SUIT_COLORS[s] == color)
        possible_eights = set(SUITS) - {twelve}

        res = 0.0
        for eight in possible_eights:
            deck = {s: 10 for s in SUITS}
            deck[twelve] = 12
            deck[eight] = 8

            m = self.multinomials[dict_to_key(deck)]
            x = 5 if eight == suit else 6
            if self.hand[suit] >= x:
                v = 0
            else:
                p = 120 if eight == suit else 100
                a = (p*(1 - self.buy_ratio)) / (1-(self.buy_ratio**x))
                v = self.buy_ratio**self.hand[suit] * a
            res += m * (10 + v) 

        return max(round(res), 1)
    
    def _handle_start(self, hand: Dict[str, Any], opponents: Set[str]) -> None:
        """
        Initialize internal state at the start of trading.
        """
        # Setup structures for each player
        self.initial_hand = {pid: {s: 0 for s in SUITS} for pid in opponents}
        self.bought_cards = {pid: {s: 0 for s in SUITS} for pid in opponents}
        self.peek_offers = {pid: {s: False for s in SUITS} for pid in opponents}

        self.initial_hand[self.player_id] = hand.copy()
        self.hand = hand.copy()

        self._update_multinomials()
        
        # Begin tick events
        self.on_tick(self._handle_tick)

    def _handle_tick(self, _) -> None:
        """
        Called every polling cycle of the market.

        May issue a buy or sell order based on aggression.
        """
        if random.random() >= self.aggression:
            return
        action = random.choice(['buy', 'sell'])
        suit = random.choice(SUITS)
        # Cannot sell what you don't have
        if action == 'sell' and self.hand.get(suit, 0) == 0:
            return
        best_ask = self.market[suit].lowest_ask
        best_bid = self.market[suit].highest_bid
        exp_val = self._get_exp_val(suit, action)
        if action == 'buy':
            bid_price = random.randint(1, exp_val)
            price = min(bid_price, best_ask) if best_ask is not None else bid_price
            self.market[suit].highest_bid = price
            op = self.bid
        else:
            ask_price = random.randint(exp_val, 2 * exp_val)
            price = max(ask_price, best_bid) if best_bid is not None else ask_price
            self.market[suit].lowest_ask = price
            op = self.offer
            
        print(f"{self.player_id}: Send {action} order for {suit} at {price}")
        try:
            op(price, suit)
        except requests.HTTPError as e:
            # Log failure to execute order
            print(f"Order failed ({action} {suit} at {price}): {e.response.text}")

    def _handle_bid(self, _, price: int, suit: str) -> None:
        """
        Update highest bid when an opponent bids.
        """
        self.market[suit].highest_bid = price

    def _handle_offer(self, player: str, price: int, suit: str) -> None:
        """
        Update lowest ask when an opponent offers.
        Register new cards as seen and update multinomials when necessary.
        """
        self.market[suit].lowest_ask = price
        new_peek = not self.peek_offers[player][suit]

        # Mark peek if they haven't bought that suit before
        if self.bought_cards.get(player, {}).get(suit, 0) == 0:
            self.peek_offers[player][suit] = True
            if new_peek:
                self._update_multinomials()

    def _handle_trade(self, buyer: str, seller: str, _, suit: str) -> None:
        """
        Process a completed trade event and adjust holdings.
        """
        # Clear market quotes
        self.market = {s: Market() for s in SUITS}
        # Adjust seller and buyer states
        if seller == self.player_id:
            self.hand[suit] -= 1
        else:
            if self.bought_cards[seller][suit] > 0:
                self.bought_cards[seller][suit] -= 1
            else:
                self.peek_offers[seller][suit] = False
                self.initial_hand[seller][suit] += 1
        if buyer == self.player_id:
            self.hand[suit] += 1
        else:
            self.bought_cards[buyer][suit] += 1

    def _handle_cancel(
        self,
        order_type: Literal['bid', 'offer'],
        _, __, ___,
        new_price: Optional[int],
        suit: str
    ) -> None:
        """
        Handle repricing of an order.
        """
        if order_type == 'bid':
            self.market[suit].highest_bid = new_price
        else:
            self.market[suit].lowest_ask = new_price
