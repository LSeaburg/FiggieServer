import numpy as np
import random
import requests
from dataclasses import dataclass
from typing import Optional, Literal

from agents.figgie_interface import FiggieInterface

SUITS = ["spades", "clubs", "hearts", "diamonds"]

@dataclass
class Market:
    """
    Represents current best bid and ask for a suit.
    """
    highest_bid: Optional[int] = None
    lowest_ask: Optional[int] = None

class NoiseTrader(FiggieInterface):
    """
    A noise trading agent based on the model in https://arxiv.org/pdf/2110.00879.
    """
    def __init__(
        self,
        server_url: str,
        name: str,
        polling_rate: float = 1.0,
        aggression: float = 0.5,
        default_val: int = 7,
        sigma: float = 1.0
    ) -> None:
        """
        Initialize the Noise Trader agent.

        Args:
            server_url: URL of the Figgie server.
            name: Unique name for this agent.
            polling_rate: Seconds between polling cycles.
            aggression: Probability [0,1] of acting on each tick.
            default_val: Parameter used as baseline if market data is empty.
            sigma: Parameter controlling level of noise.
        """
        super().__init__(server_url, name, polling_rate)
        self.aggression = aggression
        self.default_val = default_val
        self.sigma = sigma

        # Market quotes by suit
        self.market = {suit: Market() for suit in SUITS}

        self.on_tick(self._handle_tick)
        self.on_bid(self._handle_bid)
        self.on_offer(self._handle_offer)
        self.on_transaction(self._handle_trade)
        self.on_cancel(self._handle_cancel)

    # Uses a binomial dist. to approx. a normal dist. in discrete space
    def _add_noise(self, n: int, sigma: float) -> int:
        Z = np.random.normal(loc=0, scale=sigma)
        return max(round(n * np.exp(Z)), 1)

    def _get_exp_val(self, best_bid: Optional[int]) -> Optional[int]:
        if best_bid is None:
            return self.default_val
        return self._add_noise(best_bid, self.sigma)

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
        exp_val = self._get_exp_val(best_bid)
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
        self.market[suit].highest_bid = price

    def _handle_offer(self, _, price: int, suit: str) -> None:
        self.market[suit].lowest_ask = price

    def _handle_trade(self, _, __, ___, ____) -> None:
        self.market = {suit: Market() for suit in SUITS}

    def _handle_cancel(self, 
        order_type: Literal['bid', 'offer'], 
        _, __, ___, 
        new_price: int, 
        suit: str) -> None:
        """
        Handle repricing of an order.
        """
        if order_type == "bid":
            self.market[suit].highest_bid = new_price
        else: # order_type == "offer"
            self.market[suit].lowest_ask = new_price