import numpy as np
import random
import requests
from dataclasses import dataclass, field
from typing import Dict, List, Set, TypeVar, FrozenSet, Optional, Literal

from figgie_interface import FiggieInterface

SUITS = ["spades", "clubs", "hearts", "diamonds"]

@dataclass
class Market:
    """
    Represents current best bid and ask for a suit.
    """
    highest_bid: Optional[int] = None
    lowest_ask: Optional[int] = None

@dataclass
class History:
    """
    Represents history of a players bids and offers.
    """
    bids: Dict[str, List[int]] = field(default_factory=lambda: {s: [] for s in SUITS})
    offers: Dict[str, List[int]] = field(default_factory=lambda: {s: [] for s in SUITS})

T = TypeVar('T')
def get_random_non_empty_subset(input_set: Set[T]) -> FrozenSet[T]:
    """
    Returns a random non-empty subset of the input_set, where each
    non-empty subset is equally likely.

    Args:
        input_set: The original set.

    Returns:
        A frozenset representing a random non-empty subset.
    """
    if not input_set:
        raise ValueError("Cannot get a non-empty subset from an empty set.")

    random_subset = set()
    while not random_subset:  # Keep trying until a non-empty subset is found
        for element in input_set:
            if random.choice([True, False]):  # 50% chance to include the element
                random_subset.add(element)
    return frozenset(random_subset)

class BottomFeeder(FiggieInterface):
    """
    A bottom feeder agent based on the model in https://arxiv.org/pdf/2110.00879.
    """
    def __init__(
        self,
        server_url: str,
        name: str,
        polling_rate: float = 1.0,
        aggression: float = 0.5,
        look_depth: int = 4
    ) -> None:
        """
        Initialize the Fundamentalist agent.

        Args:
            server_url: URL of the Figgie server.
            name: Unique name for this agent.
            polling_rate: Seconds between polling cycles.
            aggression: Probability [0,1] of acting on each tick.
            look_depth: How far to look back in order history.
        """
        super().__init__(server_url, name, polling_rate)
        self.aggression = aggression
        self.look_depth = look_depth

        # Market quotes by suit
        self.market: Dict[str, Market] = {suit: Market() for suit in SUITS}
        # Opponents to calculate order price on
        self.prey: Set[str] = set()
        # History of opponent bids and offers
        self.history: Dict[str, History] = dict()

        # Register event handlers
        # The tick handler will be registered once trading starts
        # self.on_tick(self._handle_tick)
        self.on_start(self._handle_start)
        self.on_bid(self._handle_bid)
        self.on_offer(self._handle_offer)
        self.on_transaction(self._handle_trade)
        self.on_cancel(self._handle_cancel)

    def _get_mean_history(self, player: str, suit: str) -> Optional[float]:
        if not self.history[player].bids[suit] or not self.history[player].offers[suit]:
            return None

        recent_bids = self.history[player].bids[suit][-self.look_depth:]
        recent_offers = self.history[player].offers[suit][-self.look_depth:]

        bid_avg = sum(recent_bids) / len(recent_bids)
        offer_avg = sum(recent_offers) / len(recent_offers)

        return (bid_avg + offer_avg) / 2

    def _get_exp_val(self, suit: str) -> Optional[int]:
        res = 0.0
        count = 0
        for p in self.prey:
            mean =  self._get_mean_history(p, suit)
            if not mean is None:
                res += mean
                count += 1

        if count == 0:
            return None
        return round(res / count)
            

    def _handle_start(self, _, opponents: Set[str]) -> None:
        """
        Initialize internal state at the start of trading.
        """
        self.prey = get_random_non_empty_subset(opponents)
        
        all_players = opponents | {self.player_id}
        self.history = {p: History() for p in all_players}

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
        best_ask = self.market[suit].lowest_ask
        best_bid = self.market[suit].highest_bid

        exp_val = self._get_exp_val(suit)
        if exp_val is None:
            return

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

    def _handle_bid(self, player: str, price: int, suit: str) -> None:
        self.market[suit].highest_bid = price

        self.history[player].bids[suit].append(price)

    def _handle_offer(self, player: str, price: int, suit: str) -> None:
        self.market[suit].lowest_ask = price

        self.history[player].offers[suit].append(price)

    def _handle_trade(self, buyer: str, seller: str, price: int, suit: str) -> None:
        self.market = {suit: Market() for suit in SUITS}

        if self.history[buyer].bids[suit] and self.history[buyer].bids[suit][-1] != price:
            self.history[buyer].bids[suit].append(price)
        if self.history[seller].offers[suit] and self.history[seller].offers[suit][-1] != price:
            self.history[seller].offers[suit].append(price)

    def _handle_cancel(self, 
        order_type: Literal['bid', 'offer'], 
        old_player: str, _, 
        __, new_price: int, 
        suit: str) -> None:
        """
        Handle repricing of an order.
        """
        if order_type == "bid":
            self.market[suit].highest_bid = new_price
            self.history[old_player].bids[suit].pop()
        else: # order_type == "offer"
            self.market[suit].lowest_ask = new_price
            self.history[old_player].offers[suit].pop()