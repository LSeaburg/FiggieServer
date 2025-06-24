import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import requests
import random

# ---- Data models ----
@dataclass
class State:
    """
    Represents the full game state returned by the Figgie server.
    """
    state: Optional[str]
    time_left: Optional[int]
    pot: Optional[int] = None
    hand: Optional[Dict[str, Any]] = None
    market: Dict[str, Any] = field(default_factory=dict)
    balances: Dict[str, Any] = field(default_factory=dict)
    trades: List['Trade'] = field(default_factory=list)
    results: Optional[Dict[str, Any]] = None
    hands: Optional[Dict[str, Any]] = None

@dataclass
class Order:
    """
    Represents a single order in the market or pending for this player.
    """
    order_id: str
    player_id: str
    type: str       # "buy" or "sell"
    suit: str
    price: int

@dataclass
class Trade:
    """
    Represents a completed trade event.
    """
    buyer: str
    seller: str
    price: int
    suit: str

# Type aliases for event handlers
HandlerBid = Callable[[str, int, str], None]
HandlerOffer = Callable[[str, int, str], None]
HandlerTransaction = Callable[[str, str, int, str], None]
HandlerCancel = Callable[[str, str, int, Optional[str], Optional[int], str], None]
HandlerStart = Callable[[Dict[str, Any], Set[str]], None]
HandlerTick = Callable[[int], None]

class FiggieInterface:
    def __init__(
        self,
        server_url: str,
        name: str,
        polling_rate: float = 1.0,
        jitter_factor: float = 0.1
    ) -> None:
        """
        Initialize the Figgie client interface.
        Args:
            server_url: Base URL of the Figgie Flask app.
            name: Player name.
            polling_rate: Seconds between polling cycles.
        """
        self.server_url: str = server_url.rstrip("/")
        self.name: str = name
        self.polling_rate: float = polling_rate
        self.jitter_factor: float = jitter_factor
        self.player_id: Optional[str] = None

        # Event handlers
        self._handlers: Dict[str, List[Callable[..., None]]] = {
            "bid": [],    # HandlerBid
            "offer": [],  # HandlerOffer
            "transaction": [],  # HandlerTransaction
            "cancel": [], # HandlerCancel
            "start": [],  # HandlerStart
            "tick": []    # HandlerTick
        }

        # Internal state
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Initialize last state to default for consistent behavior
        self._last_state: State = State(state=None, time_left=None)
        self._last_trade_index: int = 0

        # Join the game and start polling
        self._join()
        self._start_polling()

    def _join(self) -> None:
        """
        Register this client with the server to obtain a player ID.
        """
        try:
            response = requests.post(
                f"{self.server_url}/join",
                json={"name": self.name}
            )
            response.raise_for_status()
            data = response.json()
            self.player_id = data.get("player_id")
        except Exception:
            logging.exception("Error joining Figgie server")
            self.player_id = None

    def _start_polling(self) -> None:
        """Start the background polling thread."""
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True
        )
        self._thread.start()

    def _poll_loop(self) -> None:
        """Continuously poll the server for state changes and dispatch events."""
        while not self._stop_event.is_set():
            try:
                state = self._get_state()
                self._process_state(state)
            except Exception:
                logging.exception("Error polling Figgie state")
            # apply uniform jitter around polling_rate
            jitter = random.uniform(-self.jitter_factor, self.jitter_factor) * self.polling_rate
            sleep_time = max(self.polling_rate + jitter, 0.0)
            time.sleep(sleep_time)

    def _get_state(self) -> State:
        """Fetch and parse the latest game state for this player."""
        response = requests.get(
            f"{self.server_url}/state",
            params={"player_id": self.player_id}
        )
        response.raise_for_status()
        raw = response.json()
        # Parse trades into dataclasses
        trades_list = [Trade(**t) for t in (raw.get("trades", []) or [])]
        return State(
            state=raw.get("state"),
            time_left=raw.get("time_left"),
            pot=raw.get("pot"),
            hand=raw.get("hand"),
            market=raw.get("market", {}) or {},
            balances=raw.get("balances", {}),
            trades=trades_list,
            results=raw.get("results"),
            hands=raw.get("hands")
        )

    def _process_state(self, state: State) -> None:
        """
        Compare new state to the previous state and fire any relevant event handlers.
        Args:
            state: The latest parsed State object from the server.
        """
        # 1) on_tick events
        if state.time_left is not None:
            for fn in set(self._handlers["tick"]):
                try:
                    fn(state.time_left)  # type: ignore
                except Exception:
                    logging.exception("on_tick error")

        # 2) on_start: first transition to trading
        prev_phase = self._last_state.state if self._last_state else None
        if state.state == "trading" and prev_phase != "trading":
            if state.hand is not None:
                for fn in set(self._handlers["start"]):
                    try:
                        fn(state.hand, set(state.balances.keys()) - {self.player_id})  # type: ignore
                    except Exception:
                        logging.exception("on_start error")

        # 3) new trades -> on_transaction
        new_trades = state.trades[self._last_trade_index:]
        if new_trades:
            # Reset last state to prevent ghost cancellations
            self._last_state = None
            for trade in new_trades:
                buyer, seller, price, suit = trade.buyer, trade.seller, trade.price, trade.suit
                for fn in set(self._handlers["transaction"]):
                    try:
                        fn(buyer, seller, price, suit)
                    except Exception:
                        logging.exception("on_transaction error")
        self._last_trade_index = len(state.trades)

        # 4) market quote changes -> on_bid, on_offer, on_cancel
        prev_market = self._last_state.market if self._last_state else {}
        curr_market = state.market
        suits = set(prev_market.keys()) | set(curr_market.keys())
        for suit in suits:
            pm = prev_market.get(suit, {}) or {}
            cm = curr_market.get(suit, {}) or {}
            pb = pm.get("highest_bid") or {}
            cb = cm.get("highest_bid") or {}
            # New best bid
            if cb and (not pb or int(cb.get("price")) > int(pb.get("price"))) and cb.get("player_id") != self.player_id:
                for fn in set(self._handlers["bid"]):
                    try:
                        fn(cb["player_id"], int(cb["price"]), suit)  # type: ignore
                    except Exception:
                        logging.exception("on_bid error")
            # Bid canceled or changed
            elif pb and (not cb or cb.get("price") < pb.get("price") or (cb.get("price") == pb.get("price") and cb.get("player_id") != pb.get("player_id"))):
                old_pid = pb.get("player_id")
                old_price = int(pb.get("price", 0))
                new_pid = cb.get("player_id") if cb else None
                new_price = int(cb.get("price")) if cb and cb.get("price") is not None else None
                for fn in set(self._handlers["cancel"]):
                    try:
                        fn("bid", old_pid, old_price, new_pid, new_price, suit)  # type: ignore
                    except Exception:
                        logging.exception("on_cancel error")
                        
            po = pm.get("lowest_ask") or {}
            co = cm.get("lowest_ask") or {}
            # New best offer
            if co and (not po or int(co.get("price")) < int(po.get("price"))) and co.get("player_id") != self.player_id:
                for fn in set(self._handlers["offer"]):
                    try:
                        fn(co["player_id"], int(co["price"]), suit)  # type: ignore
                    except Exception:
                        logging.exception("on_offer error")
            # Offer canceled or changed
            elif po and (not co or co.get("price") > po.get("price") or (co.get("price") == po.get("price") and co.get("player_id") != po.get("player_id"))):
                old_pid = po.get("player_id")
                old_price = int(po.get("price", 0))
                new_pid = co.get("player_id") if co else None
                new_price = int(co.get("price")) if co and co.get("price") is not None else None
                for fn in set(self._handlers["cancel"]):
                    try:
                        fn("offer", old_pid, old_price, new_pid, new_price, suit)  # type: ignore
                    except Exception:
                        logging.exception("on_cancel error")

        # Stash state for next diff
        self._last_state = state

    def bid(self, value: int, suit: str) -> Any:
        """Place a buy order at the specified price for one unit."""
        return self._place("buy", suit, value)

    def offer(self, value: int, suit: str) -> Any:
        """Place a sell order at the specified price for one unit."""
        return self._place("sell", suit, value)

    def _place(self, otype: str, suit: str, price: int) -> Any:
        """Internal helper for placing orders (buy or sell)."""
        payload: Dict[str, Any] = {
            "action_type": "order",
            "player_id": self.player_id,
            "order_type": otype,
            "suit": suit,
            "price": price
        }
        response = requests.post(
            f"{self.server_url}/action",
            json=payload
        )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            # Handle cases where no JSON is returned
            logging.error("Server returned non-JSON response for order.")
            return {}

    def buy(self, suit: str) -> Any:
        """Buy one unit of the given suit at the best offer price."""
        if not self._last_state:
            raise RuntimeError("No state yet")
        ask = self._last_state.market.get(suit, {}).get("lowest_ask") or {}
        if not ask or ask.get("price") is None:
            raise RuntimeError("No offers")
        return self.bid(int(ask["price"]), suit)

    def sell(self, suit: str) -> Any:
        """Sell one unit of the given suit at the best bid price."""
        if not self._last_state:
            raise RuntimeError("No state yet")
        bid = self._last_state.market.get(suit, {}).get("highest_bid") or {}
        if not bid or bid.get("price") is None:
            raise RuntimeError("No bids")
        return self.offer(int(bid["price"]), suit)

    def cancel_bids_and_offers(self, suit: str) -> List[str]:
        """Cancel all your outstanding orders for a given suit and return their IDs."""
        if not self._last_state:
            return []
        # Use bulk cancel API to cancel both buy and sell orders for this suit
        payload: Dict[str, Any] = {
            "action_type": "cancel",
            "player_id": self.player_id,
            "order_type": "both",
            "suit": suit,
            "price": -1
        }
        response = requests.post(
            f"{self.server_url}/action",
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        # Return list of canceled order IDs
        return data.get("canceled", [])

    def cancel_all_bids_and_offers(self) -> List[str]:
        return self.cancel_bids_and_offers("all")

    # Event registration methods
    def on_bid(self, fn: HandlerBid) -> HandlerBid:
        self._handlers["bid"].append(fn)
        return fn

    def on_offer(self, fn: HandlerOffer) -> HandlerOffer:
        self._handlers["offer"].append(fn)
        return fn

    def on_transaction(self, fn: HandlerTransaction) -> HandlerTransaction:
        self._handlers["transaction"].append(fn)
        return fn

    def on_cancel(self, fn: HandlerCancel) -> HandlerCancel:
        self._handlers["cancel"].append(fn)
        return fn

    def on_start(self, fn: HandlerStart) -> HandlerStart:
        self._handlers["start"].append(fn)
        return fn

    def on_tick(self, fn: HandlerTick) -> HandlerTick:
        self._handlers["tick"].append(fn)
        return fn

    def stop(self) -> None:
        """Stop the polling thread and clean up."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join()
