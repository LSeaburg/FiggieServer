from itertools import permutations
from dataclasses import dataclass, fields, replace
import numbers
from typing import Generic, TypeVar

T = TypeVar("T")

SUITS = ["hearts", "spades", "clubs", "diamonds"]

SUIT_COLORS: dict[str, str] = {
    "spades": "black",
    "clubs": "black",
    "hearts": "red",
    "diamonds": "red"
}

@dataclass
class Cards(Generic[T]):
    hearts: T = 0
    spades: T = 0
    clubs: T = 0
    diamonds: T = 0

    SUIT_SYMBOLS = {
        "hearts": "♥",
        "spades": "♠",
        "clubs": "♣",
        "diamonds": "♦",
    }

    def copy(self) -> "Cards":
        return replace(self)  # makes a shallow copy

    def __getitem__(self, key: str):
        if not hasattr(self, key):
            raise KeyError(f"Invalid key: {key}")
        return getattr(self, key)

    def __setitem__(self, key: str, value):
        if not hasattr(self, key):
            raise KeyError(f"Invalid key: {key}")
        setattr(self, key, value)

    def as_dict(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def keys(self):
        return [f.name for f in fields(self)]

    def values(self):
        return [getattr(self, f.name) for f in fields(self)]

    def items(self):
        return [(f.name, getattr(self, f.name)) for f in fields(self)]

    def __iter__(self):
        """Iterate over (suit, value) pairs."""
        for f in fields(self):
            yield (f.name, getattr(self, f.name))

    def __repr__(self) -> str:
        parts = []
        for f in fields(self):
            val = getattr(self, f.name)
            symbol = self.SUIT_SYMBOLS[f.name]
            parts.append(f"{symbol}={val}")
        return f"Cards({', '.join(parts)})"
    
    def __str__(self) -> str:
        """Compact, user-friendly representation."""
        parts = []
        for f in fields(self):
            val = getattr(self, f.name)
            symbol = self.SUIT_SYMBOLS[f.name]
            parts.append(f"{symbol}{val}")
        return " ".join(parts)

    # --- Arithmetic support ---
    def __add__(self, other: "Cards") -> "Cards":
        if not isinstance(other, Cards):
            return NotImplemented
        return Cards(
            **{
                f.name: (
                    getattr(self, f.name) + getattr(other, f.name)
                    if isinstance(getattr(self, f.name), numbers.Number)
                    and isinstance(getattr(other, f.name), numbers.Number)
                    else getattr(self, f.name)
                )
                for f in fields(self)
            }
        )

    def __sub__(self, other: "Cards") -> "Cards":
        if not isinstance(other, Cards):
            return NotImplemented
        return Cards(
            **{
                f.name: (
                    getattr(self, f.name) - getattr(other, f.name)
                    if isinstance(getattr(self, f.name), numbers.Number)
                    and isinstance(getattr(other, f.name), numbers.Number)
                    else getattr(self, f.name)
                )
                for f in fields(self)
            }
        )

    def __iadd__(self, other: "Cards") -> "Cards":
        if not isinstance(other, Cards):
            return NotImplemented
        for f in fields(self):
            a, b = getattr(self, f.name), getattr(other, f.name)
            if isinstance(a, numbers.Number) and isinstance(b, numbers.Number):
                setattr(self, f.name, a + b)
        return self

    def __isub__(self, other: "Cards") -> "Cards":
        if not isinstance(other, Cards):
            return NotImplemented
        for f in fields(self):
            a, b = getattr(self, f.name), getattr(other, f.name)
            if isinstance(a, numbers.Number) and isinstance(b, numbers.Number):
                setattr(self, f.name, a - b)
        return self

    # --- Multiplication support ---
    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Cards(
                **{
                    f.name: (
                        getattr(self, f.name) * other
                        if isinstance(getattr(self, f.name), (int, float, bool))
                        else getattr(self, f.name)
                    )
                    for f in fields(self)
                }
            )
        return NotImplemented

    def __rmul__(self, other):
        # support float * Cards as well as Cards * float
        return self.__mul__(other)

VALUES = [12, 10, 10, 8]
DECKS = [Cards(**dict(zip(SUITS, perm))) 
         for perm in set(permutations(VALUES))]

@dataclass
class Market:
    """
    Represents current best bid and ask for a suit.
    """
    bid: object | None = None
    offer: object | None = None

    def __getitem__(self, key: str):
        if not hasattr(self, key):
            raise KeyError(f"Invalid key: {key}")
        return getattr(self, key)

    def __setitem__(self, key: str, value):
        if not hasattr(self, key):
            raise KeyError(f"Invalid key: {key}")
        setattr(self, key, value)

    def as_dict(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def keys(self):
        return [f.name for f in fields(self)]

    def values(self):
        return [getattr(self, f.name) for f in fields(self)]

    def items(self):
        return [(f.name, getattr(self, f.name)) for f in fields(self)]

    def __iter__(self):
        # iterate over (key, value) pairs
        for f in fields(self):
            yield (f.name, getattr(self, f.name))