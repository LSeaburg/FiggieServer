import numpy as np
import random
import requests
from figgie_interface import FiggieInterface
from dataclasses import dataclass
from typing import Optional

SUITS = ["spades", "clubs", "hearts", "diamonds"]

@dataclass
class Market:
    highest_bid: Optional[int] = None
    lowest_ask: Optional[int] = None

class NoiseTrader(FiggieInterface):

    def __init__(self, server_url, name, polling_rate=1.0, aggression=0.5, default_val=7, sigma=1):
        super().__init__(server_url, name, polling_rate)
        self.aggression = aggression
        self.market = {suit: Market() for suit in SUITS}
        self.default_val = default_val
        self.sigma = sigma

        self.on_tick(self._handle_tick)
        self.on_bid(self._handle_bid)
        self.on_offer(self._handle_offer)
        self.on_transaction(self._handle_trade)

    # Uses a binomial dist. to approx. a normal dist. in discrete space
    def _add_noise(self, n, sigma) -> int:
        Z = np.random.normal(loc=0, scale=sigma)
        return round(n * np.exp(Z))

    def _handle_tick(self, _):
        if random.random() < self.aggression:
            order = random.choice(["buy", "sell"])
            suit = random.choice(SUITS)

            low_ask = self.market[suit].lowest_ask
            high_bid = self.market[suit].highest_bid

            exp_val = self.default_val if high_bid is None else self._add_noise(high_bid, self.sigma)

            if order == "buy":
                p = random.randint(0, exp_val)
                price = p if low_ask is None else min(p, low_ask)
                operation = self.bid
                print(f"{self.player_id}: Making bid with price {price} and suit {suit}")
            else: # order == "sell"
                p = random.randint(exp_val, 2 * exp_val)
                price = p if high_bid is None else max(p, high_bid)
                operation = self.offer
            
            print(f"{self.player_id}: Send {order} order with price {price} and suit {suit}")
            try:
                operation(price, suit)
            except requests.HTTPError as e:
                print(f"Failed: {e.response.status_code} {e.response.text}")

    def _handle_bid(self, _, price, suit):
        self.market[suit].highest_bid = price

    def _handle_offer(self, _, price, suit):
        self.market[suit].lowest_ask = price

    def _handle_trade(self, _, __, ___, ____):
        self.market = {suit: Market() for suit in SUITS}