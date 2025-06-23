import os
import uuid
import random
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from figgie_server.models import Order, Trade, Player, Market
from figgie_server import db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)

NUM_PLAYERS = int(os.getenv("NUM_PLAYERS", "4"))
if NUM_PLAYERS not in (4, 5):
    raise RuntimeError("NUM_PLAYERS must be 4 or 5")
TRADING_DURATION = int(os.getenv("TRADING_DURATION", str(4 * 60)))  # seconds

SUITS = ["spades", "clubs", "hearts", "diamonds"]
SUIT_COLORS = {
    "spades": "black",
    "clubs": "black",
    "hearts": "red",
    "diamonds": "red"
}

class Game:
    def __init__(self) -> None:
        self.round_id = None
        self.reset()
        logger.info("Initialized new Game instance.")

    def _compute_or_finalize_time(self) -> int:
        """
        Compute and normalize the remaining trading time to a 0-240 scale.
        Ends the round if time has expired.
        """
        now = datetime.now().timestamp()
        elapsed = now - (self.start_time or now)
        raw_time_left = max(0.0, TRADING_DURATION - elapsed)
        if raw_time_left <= 0.0:
            self.end_round()
            raw_time_left = 0.0
        return int(raw_time_left / TRADING_DURATION * 240)

    def reset(self) -> None:
        self.state = "waiting"          # waiting, trading, completed
        self.players: Dict[str, Player] = {}               # pid -> Player
        self.orders: Dict[str, Order] = {}                 # oid -> Order
        self.initial_balances: Dict[str, int] = {}         # pid -> balance
        self.initial_hands: Dict[str, Dict] = {}           # pid -> hand
        # Markets per suit
        self.markets: Dict[str, Market] = {s: Market() for s in SUITS}
        self.trades: List[Trade] = []                      # executed trades
        self.pot = 0
        self.start_time: Optional[float] = None
        self.suit_counts: Optional[Dict[str,int]] = None   # counts per suit
        self.goal_suit: Optional[str] = None
        self.results: Optional[dict] = None
        # generate a new round ID
        self.round_id = uuid.uuid4().hex
        logger.info("Game state has been reset.")

    def add_player(self, name: str) -> str:
        pid = uuid.uuid4().hex
        self.players[pid] = Player(player_id=pid, name=name)
        logger.info(f"Player added: {name} (ID: {pid})")
        # log player join
        db.log_player(pid, name)
        return pid

    def can_start(self) -> bool:
        return len(self.players) == NUM_PLAYERS

    def start_round(self) -> None:
        logger.info("Starting new round.")
        counts = random.sample([8, 10, 10, 12], 4)
        self.suit_counts = dict(zip(SUITS, counts))
        twelve = next(s for s, c in self.suit_counts.items() if c == 12)
        eight  = next(s for s, c in self.suit_counts.items() if c == 8)
        col12 = SUIT_COLORS[twelve]
        self.goal_suit = next(s for s in SUITS if s != twelve and SUIT_COLORS[s] == col12)
        logger.info(f"Suit counts: {self.suit_counts}, goal: {self.goal_suit}")

        # record initial money balances of players at start of round
        self.initial_balances = {pid: p.money for pid, p in self.players.items()}

        # collect ante
        ante = 200 // NUM_PLAYERS
        self.pot = ante * NUM_PLAYERS
        for p in self.players.values():
            p.money -= ante
            p.hand = {s: 0 for s in SUITS}
        logger.info(f"Pot initialized to ${self.pot}")

        # shuffle the deck
        deck: List[str] = []
        for suit, cnt in self.suit_counts.items():
            deck.extend([suit] * cnt)
        random.shuffle(deck)

        # deal the cards
        per = len(deck) // NUM_PLAYERS
        for _ in range(per):
            for pid in self.players:
                dealt = deck.pop()
                self.players[pid].hand[dealt] += 1

        # record initial hands after dealing cards
        self.initial_hands = {pid: p.hand.copy() for pid, p in self.players.items()}

        self.state = "trading"
        self.start_time = datetime.now().timestamp()
        logger.info("Round state changed to 'trading'.")
        
        db.log_round_start(self.round_id, NUM_PLAYERS, TRADING_DURATION, self.goal_suit, eight)

    def end_round(self) -> None:
        logger.info(f"Ending round. Goal suit: {self.goal_suit}")
        goal = self.goal_suit
        counts = {pid: p.hand.get(goal, 0) for pid, p in self.players.items()}
        total_bonus = 0
        bonuses = {}
        for pid, cnt in counts.items():
            b = 10 * cnt
            self.players[pid].money += b
            bonuses[pid] = b
            total_bonus += b
        rem = self.pot - total_bonus
        max_cnt = max(counts.values(), default=0)
        winners = [pid for pid, cnt in counts.items() if cnt == max_cnt]
        share = rem // len(winners) if winners else 0
        for pid in winners:
            self.players[pid].money += share
        self.results = {"goal_suit": goal, "counts": counts, "bonuses": bonuses,
                        "winners": winners, "share_each": share}
        logger.info(f"Results computed: {self.results}")
        # log round end with snapshots
        db.log_round_end(
            self.round_id,
            self.results,
            self.initial_balances,
            {pid: p.money for pid, p in self.players.items()},
            self.initial_hands,
            {pid: p.hand.copy() for pid, p in self.players.items()}
        )
        self.pot = 0
        self.state = "completed"
        logger.info("Round state changed to 'completed'.")

    def match_order(self, pid: str, otype: str, suit: str, price: int) -> Tuple[bool, Optional[str], Optional[Order]]:
        market = self.markets[suit]
        if otype == "buy":
            if market.offers:
                lowest_ask = market.offers[0]
                # reject trade with oneself
                if lowest_ask.player_id == pid and price >= lowest_ask.price:
                    return False, "Reject Order", None
                # match if buyer's price meets or exceeds ask price
                if price >= lowest_ask.price:
                    return True, lowest_ask.order_id, lowest_ask
        else:
            if market.bids:
                highest_bid = market.bids[0]
                if highest_bid.player_id == pid and price <= highest_bid.price:
                    return False, "Reject Order", None
                # match if seller's price is <= bid price
                if price <= highest_bid.price:
                    return True, highest_bid.order_id, highest_bid
        return True, None, None

    def place_order(self, pid: str, otype: str, suit: str, price: int) -> Tuple[dict, Optional[str]]:
        # validation
        if (time_remaining := self._compute_or_finalize_time()) == 0:
            return None, "Round has ended"
        if otype not in ("buy", "sell"): 
            return None, "Invalid order_type"
        if suit not in SUITS: 
            return None, "Invalid suit"
        if not isinstance(price, int) or price <= 0: 
            return None, "Price must be a positive integer"
        p = self.players[pid]
        if otype == "sell" and p.hand.get(suit, 0) < 1: 
            return None, "Not enough cards"
        if otype == "buy" and p.money < price: 
            return None, "Insufficient funds"

        market = self.markets[suit]
        # cancel duplicate orders by same player for same suit and price
        side_list = market.bids if otype == "buy" else market.offers
        if any(o.player_id == pid and o.price == price for o in side_list):
            return None, "Duplicate order"

        valid_order, mid, match = self.match_order(pid, otype, suit, price)
        if not valid_order:
            return None, "Cannot execute trade with oneself"
        if match:
            # execute trade
            buyer = pid if otype == "buy" else match.player_id
            seller = match.player_id if otype == "buy" else pid
            self.players[seller].hand[suit] -= 1
            self.players[buyer].hand[suit] = self.players[buyer].hand.get(suit, 0) + 1
            self.players[buyer].money -= match.price
            self.players[seller].money += match.price
            tr = Trade(buyer=buyer, seller=seller, price=match.price, suit=suit)
            self.trades.append(tr)
            # log trade in DB
            db.log_trade(self.round_id, tr, time_remaining)
            # clear all orders in all markets
            self.orders.clear()
            for m in self.markets.values():
                m.bids.clear()
                m.offers.clear()
            return {"trade": tr.__dict__}, None

        # no match: add to market
        oid = uuid.uuid4().hex
        new_o = Order(order_id=oid, player_id=pid, type=otype, suit=suit, price=price)
        self.orders[oid] = new_o
        # log order in DB
        db.log_order(self.round_id, new_o, time_remaining)
        # insert order in sorted position (stable for same price)
        if otype == "buy":
            # descending order
            idx = 0
            for idx, existing in enumerate(market.bids):
                if existing.price < price:
                    break
            else:
                idx = len(market.bids)
            market.bids.insert(idx, new_o)
        else:
            # ascending order
            idx = 0
            for idx, existing in enumerate(market.offers):
                if existing.price > price:
                    break
            else:
                idx = len(market.offers)
            market.offers.insert(idx, new_o)
        return {"order_id": oid}, None

    def cancel_order(self, pid: str, otype: str, suit: str, price: int) -> Tuple[dict, Optional[str]]:
        """
        Bulk cancel orders based on order type, suit, and price threshold.
        Cancels buy orders with price greater than given price, and sell orders with price less than given price.
        If passed price is -1, all orders will be canceled.
        If otype is 'both', applies to both buy and sell. If suit is 'all', applies to all suits.
        Only cancels orders owned by pid.
        Returns a dict with canceled order IDs, or an error message.
        """
        # validation
        if (time_remaining := self._compute_or_finalize_time()) == 0:
            return None, "Round has ended"
        if otype not in ("buy", "sell", "both"): 
            return None, "Invalid order_type"
        if suit not in ("all", *SUITS): 
            return None, "Invalid suit"
        if not isinstance(price, int) or price < -1: 
            return None, "Price must be a non-negative integer or -1"

        canceled = []
        for oid, o in list(self.orders.items()):
            if o.player_id != pid:
                continue
            if otype != 'both' and o.type != otype:
                continue
            if suit != 'all' and o.suit != suit:
                continue
            # cancel logic: all orders if price == -1, else buy with price >= threshold, sell with price <= threshold
            if price == -1 or (o.type == 'buy' and o.price >= price) or (o.type == 'sell' and o.price <= price):
                market = self.markets[o.suit]
                if o.type == 'buy' and o in market.bids:
                    market.bids.remove(o)
                if o.type == 'sell' and o in market.offers:
                    market.offers.remove(o)
                canceled.append(oid)
                # log cancellation in DB
                db.log_cancellation(self.round_id, o, time_remaining)
                del self.orders[oid]
        return {'canceled': canceled}, None

    def get_state(self, req_pid: str) -> dict:
        time_left = None
        if self.state == "trading":
            time_left = self._compute_or_finalize_time()

        # Requester's current hand
        requester_hand = self.players[req_pid].hand.copy()

        # All trades so far
        trades_list = [t.__dict__ for t in self.trades]

        # Market info: highest bid and lowest ask per suit
        market = {}
        for suit, mkt in self.markets.items():
            highest_bid = None
            if mkt.bids:
                bid = mkt.bids[0]
                highest_bid = {"player_id": bid.player_id, "price": bid.price}
            lowest_ask = None
            if mkt.offers:
                ask = mkt.offers[0]
                lowest_ask = {"player_id": ask.player_id, "price": ask.price}
            market[suit] = {"highest_bid": highest_bid, "lowest_ask": lowest_ask}

        # Balances for every player
        balances = {pid: p.money for pid, p in self.players.items()}

        resp = {
            "state": self.state,
            "time_left": time_left,
            "pot": self.pot,
            "hand": requester_hand,
            "market": market,
            "balances": balances,
            "trades": trades_list
        }
        if self.state == "completed":
            resp["results"] = self.results
        return resp