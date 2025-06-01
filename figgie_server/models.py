from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

@dataclass
class Order:
    order_id: str
    player_id: str
    type: str       # "buy" or "sell"
    suit: str
    price: int

@dataclass
class Trade:
    buyer: str
    seller: str
    price: int
    suit: str

@dataclass
class Player:
    player_id: str
    name: str
    money: int = 350
    # before a round, hand is an empty dict; during/after round, hand maps suits to counts
    hand: Dict[str, int] = field(default_factory=dict)

@dataclass
class Market:
    bids: List[Order] = field(default_factory=list)
    offers: List[Order] = field(default_factory=list)
