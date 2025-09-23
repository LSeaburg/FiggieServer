import math
import random
import requests
from dataclasses import dataclass
from typing import Literal

from agents.figgie_interface import FiggieInterface
from agents.suits import SUITS, SUIT_COLORS, DECKS, Cards, Market


class HandTracker:
    """
    Tracks the hand of a player.
    Returns the total net difference in cards over the course of the game
    and what can be decuded regarding the initial hands of the players.

    *Bought cards cannot go negative, unlike net difference.  This is because
    if a player sells 2 cards and then buys 1, the net difference is -1.  
    However, if the player then offers a card, the card they offered is
    the one they bought.
    """
    def __init__(self):
        self.known_initials: Cards[int] = Cards()
        self.net_difference: Cards[int] = Cards()

        self.bought_cards: Cards[int] = Cards()
        self.seen_offer: Cards[bool] = Cards(False, False, False, False)

    # Returns True if new information regarding starting hand is available
    def offered(self, suit: str) -> bool:
        was_seen = self.seen_offer[suit]
        
        # Bought cards cannot go negative
        if self.bought_cards[suit] == 0:
            self.seen_offer[suit] = True

        return not was_seen and self.seen_offer[suit]

    def bought(self, suit: str) -> None:
        self.net_difference[suit] += 1
        self.bought_cards[suit] += 1
    
    # Returns True if new information regarding starting hand is available
    def sold(self, suit: str) -> bool:
        self.net_difference[suit] -= 1

        if self.bought_cards[suit] > 0:
            self.bought_cards[suit] -= 1
            return False

        was_seen = self.seen_offer[suit]
        self.seen_offer[suit] = False
        self.known_initials[suit] += 1
        return not was_seen

    def get_initial_cards(self) -> Cards[int]:
        return self.known_initials + self.seen_offer

    def get_net_difference(self) -> Cards[int]:
        return self.net_difference


STARTING_HAND_INDEX: list[Cards[int]] = []

@dataclass
class StartingHandFilter:
    order: Literal['bid', 'offer']
    suit: str
    price: int
    observed: Cards[int]
    hand_delta: Cards[int]

class StartingHand:
    def __init__(self, evidence_sensitivity: float, buy_ratio: float, hand_index: list[Cards[int]]):
        # Grid is indexed against hand_index
        self.hand_index = hand_index
        self.evidence_sensitivity: float = evidence_sensitivity
        self.buy_ratio: float = buy_ratio
        self.base_grid: list[int] = []
        self.filter_info: Cards[Market[StartingHandFilter]] = Cards(Market(), Market(), Market(), Market())
        self.computed_filters: Cards[Market[list[float]]] = Cards(Market(), Market(), Market(), Market())
        self.computed_grid: list[float] = []

    # Initial is the number of cards we know the player has initially
    # All known is the total number of cards we are able to place
    # between our own starting hand and the cards that we've observed
    # from other players.
    def set_base(self, initial: Cards[int], all_known: Cards[int]) -> None:
        self.base_grid = []
        deck_probs = self._multinomial_deck_probability(all_known)
        for hand in self.hand_index:
            count = 0
            for deck, deck_prob in zip(DECKS, deck_probs):
                count += deck_prob * self._hand_is_valid(hand, initial, all_known, deck)
            self.base_grid.append(count)

        self.compute_grid()

    def add_filter(self, order: Literal['bid', 'offer'], suit: str, price: int, observed: Cards[int], hand_delta: Cards[int]) -> None:
        prob_filter = StartingHandFilter(order, suit, price, observed, hand_delta)
        self.filter_info[suit][order] = prob_filter

        self.compute_filter(order, suit)
        self.compute_grid()

    def remove_filter(self, order: Literal['bid', 'offer'], suit: str) -> None:
        self.filter_info[suit][order] = None

        self.compute_filter(order, suit)
        self.compute_grid()

    def compute_filter(self, order: Literal['bid', 'offer'], suit: str) -> None:
        prob_filter = self.filter_info[suit][order]
        if prob_filter is None:
            self.computed_filters[suit][order] = None
            return

        self.computed_filters[suit][order] = [
            0 if grid_val == 0
            else math.exp(-math.sqrt(self._price_difference(hand, prob_filter)) * self.evidence_sensitivity)
            for hand, grid_val in zip(self.hand_index, self.base_grid)
        ]

    # Multiply all computed filters by the base grid
    def compute_grid(self) -> None:
        filter_composite = [1] * len(self.base_grid)
        for filter_suit in self.computed_filters.values():
            for prob_filter in filter_suit.values():
                if prob_filter is not None:
                    filter_composite = [a * b for a, b in zip(filter_composite, prob_filter)]
        self.computed_grid = [a * b for a, b in zip(self.base_grid, filter_composite)]

        total = sum(self.computed_grid)
        self.computed_grid = [x / total for x in self.computed_grid]

    def expected_value(self) -> Cards[int]:
        return sum((hand * prob for hand, prob in zip(self.hand_index, self.computed_grid)), Cards())

    def _hand_is_valid(self, hand: Cards[int], initial: Cards[int], known: Cards[int], deck: Cards[int]):
        if any(initial[suit] > hand[suit] for suit in SUITS):
            return 0
        
        outside = known - initial
        total = hand + outside
        if any(total[suit] > deck[suit] for suit in SUITS):
            return 0
        
        return 1

    def _multinomial_deck_probability(self, known_cards: Cards[int]) -> list[float]:
        """
        Compute normalized multinomial probability weight.
        Probability a given deck is the current deck in play given the known cards.
        """
        m_values = []
        # Generate all possible decks
        for deck in DECKS:
                m = 1
                for suit in SUITS:
                    k = known_cards[suit]
                    n = deck[suit]
                    if k > n:
                        m = 0
                        break
                    m *= math.comb(n, k)
                m_values.append(m)

        total = sum(m_values)
        # All decks are impossible
        if total == 0:
            return [0 * len(m_values)]
        return [m / total for m in m_values]

    def _price_difference(self, starting_hand: Cards[int], prob_filter: StartingHandFilter) -> float:
        known_cards = starting_hand + prob_filter.observed
        hand = starting_hand + prob_filter.hand_delta
        deck_probs = self._multinomial_deck_probability(known_cards)
        exp_val = FundamentalistExpectedValue(prob_filter.suit, prob_filter.order, hand, deck_probs, self.buy_ratio)
        return max(0, prob_filter.price - exp_val)


def FundamentalistExpectedValue(suit: str, 
                                order: Literal['bid', 'offer'], 
                                hand: Cards[int], 
                                deck_probabilities: list[float], 
                                buy_ratio: float
                                ) -> int:
    """
    Compute expected value for placing an order.
    """
    if order == 'offer':
        hand[suit] -= 1
        res = FundamentalistExpectedValue(suit, 'bid', hand, deck_probabilities, buy_ratio)
        hand[suit] += 1
        return res

    # Assume suit is the goal suit, so card of the same color must be the 12 card suit 
    color = SUIT_COLORS[suit]
    twelve_suit = next(s for s in SUITS if s != suit and SUIT_COLORS[s] == color)

    res = 0.0
    for deck, deck_prob in zip(DECKS, deck_probabilities):
        # If 'suit' is not the goal suit of this deck it will not add to the expected value 
        if deck[twelve_suit] != 12:
            continue
        # See page 6 in paper for math equation
        m = deck_prob
        x = deck[suit] // 2 + 1  # outright majority of goal suit
        if hand[suit] >= x:
            v = 0
        else:
            p = 200 - (10 * deck[suit])  # payout bonus for goal suit
            a = (p*(1 - buy_ratio)) / (1-(buy_ratio**x))
            v = buy_ratio**hand[suit] * a
        res += m * (10 + v) 

    return max(round(res), 1)


class HandReading(FiggieInterface):
    """
    A hand reading trading agent.
    This agent is an extension of the Fundamentalist agent.
    It uses the same model to calculate expected value, but uses
    a hand reading strategy to determine the probabilities for
    the deck in play.  It assumes opponents are using a 
    fundamentalist strategy.
    """
    def __init__(
        self,
        server_url: str,
        name: str,
        polling_rate: float,
        aggression: float = 0.5,
        buy_ratio: float = 1.7,
        alpha: float = 0.3,
        evidence_sensitivity: float = 0.5,
        test_mode: bool = False
    ) -> None:
        """
        Initialize the HandReading agent.

        Args:
            server_url: URL of the Figgie server.
            name: Unique name for this agent.
            polling_rate: Seconds between polling cycles.
            aggression: Probability [0,1] of acting on each tick.
            buy_ratio: Parameter controlling bidding aggressiveness.  Should be greater than 1.
            alpha: Parameter controlling the weight of the squared error loss when updating the deck probabilities.
            evidence_sensitivity: Parameter controlling the evidence sensitivity when updating the starting hand distribution.
        """
        super().__init__(server_url, name, polling_rate, test_mode=test_mode)
        self.aggression: float = aggression
        self.buy_ratio: float = buy_ratio
        self.alpha: float = alpha
        self.evidence_sensitivity: float = evidence_sensitivity

        # Market quotes by suit
        self.market: Cards[Market[int]] = Cards(Market(), Market(), Market(), Market())
        self.starting_hand: Cards[int] = Cards()

        self.hand_trackers: dict[str, HandTracker] = dict()
        self.oppo_starting_hands: dict[str, StartingHand] = dict()

        # Indexed against DECKS
        self.deck_probabilities: list[float] = []

        # Register event handlers
        self.on_tick(self._handle_tick)
        self.on_start(self._handle_start)
        self.on_bid(self._handle_bid)
        self.on_offer(self._handle_offer)
        self.on_transaction(self._handle_trade)
        self.on_cancel(self._handle_cancel)


    def observed_cards(self, player: str) -> Cards[int]:
        """
        Calculate total observed cards for each suit from the perspective of the passed player.
        """
        total = Cards()
        for pid, hand_tracker in self.hand_trackers.items():
            if pid != player:
                total += hand_tracker.get_initial_cards()
        return total


    def update_deck_probability(self) -> None:
        """
        Update the probabilities that each deck is the one in play.
        Uses the expected values of cards that you think each player has in their hand.
        """
        deck_ev = self.starting_hand.copy()
        # known_cards = 10 + sum(val for val in self.observed_cards(self.player_id).values())

        # alph = 0.025 * known_cards

        # Accumulate expected counts
        for starting_hand_dist in self.oppo_starting_hands.values():
            deck_ev += starting_hand_dist.expected_value()

        # Compute squared error loss for each possible deck
        total_loss = [
            sum((deck_ev[suit] - deck[suit])**2 for suit in SUITS) / len(SUITS)
            for deck in DECKS
        ]
        weights = [ math.exp(-self.alpha * loss) for loss in total_loss ]
        
        # Normalize weights and return dictionary mapping between deck and weight
        total = sum(weights)
        self.deck_probabilities = [weight/total for weight in weights]


    def exp_val(self, suit: str, order: Literal['bid', 'offer']) -> int:
        return FundamentalistExpectedValue(suit, order, self.starting_hand + self.hand_trackers[self.player_id].get_net_difference(), self.deck_probabilities, self.buy_ratio)


    def _handle_start(self, hand: dict[str, int], opponents: set[str]) -> None:
        """
        Initialize internal state at the start of trading.
        Possible starting hands are all permutations of the number of cards in each hand,
        which depends on the number of players.  These are initialized here and stored in 
        an index that can be looped over and used to lookup hands by id (index).
        """
        num_players = len(opponents) + 1
        starting_hand_size = 40 // num_players

        STARTING_HAND_INDEX.clear()
        # Create the starting hand index structure
        for i in range(starting_hand_size+1):
            for j in range(starting_hand_size-i+1):
                for k in range(starting_hand_size-i-j+1):
                    l = starting_hand_size-i-j-k
                    STARTING_HAND_INDEX.append(Cards(i, j, k, l))

        # Setup structures for each player
        self.hand_trackers = {pid: HandTracker() for pid in (opponents | {self.player_id})}
        self.oppo_starting_hands = {pid: StartingHand(self.evidence_sensitivity, self.buy_ratio, STARTING_HAND_INDEX) for pid in opponents}

        self.starting_hand = Cards(**hand)

        for pid in self.oppo_starting_hands:
            self.oppo_starting_hands[pid].set_base(self.hand_trackers[pid].get_initial_cards(), 
                                                   self.starting_hand + self.observed_cards(self.player_id))


    def _handle_tick(self, _) -> None:
        """
        Called every polling cycle of the market.
        May issue a buy or sell order based on aggression.
        """
        self.update_deck_probability()
        # Make a random decision
        if random.random() >= self.aggression:
            return
        action = random.choice(['buy', 'sell'])
        suit = random.choice(SUITS)

        # Cannot sell what you don't have
        hand = self.starting_hand + self.hand_trackers[self.player_id].get_net_difference()
        if action == 'sell' and hand[suit] == 0:
            return
        best_ask = self.market[suit]['offer']
        best_bid = self.market[suit]['bid']
        exp_val = self.exp_val(suit, 'bid' if action == 'buy' else 'offer')

        if action == 'buy':
            bid_price = random.randint(1, exp_val)
            price = min(bid_price, best_ask) if best_ask is not None else bid_price
            op = self.bid
        else: # action == 'sell'
            ask_price = random.randint(exp_val, 2 * exp_val)
            price = max(ask_price, best_bid) if best_bid is not None else ask_price
            op = self.offer

        print(f"{self.player_id}: Send {action} order for {suit} at {price}")
        try:
            op(price, suit)
        except requests.HTTPError as e:
            # Log failure to execute order
            print(f"Order failed ({action} {suit} at {price}): {e.response.text}")


    def _handle_bid(self, player: str, price: int, suit: str) -> None:
        self.market[suit]['bid'] = price

        # We don't learn anything from our own bids
        if player != self.player_id:
            self.oppo_starting_hands[player].add_filter('bid', suit, price, self.observed_cards(player), self.hand_trackers[player].get_net_difference())


    def _handle_offer(self, player: str, price: int, suit: str) -> None:
        self.market[suit]['offer'] = price

        new_info = self.hand_trackers[player].offered(suit)

        if player != self.player_id:
            self.oppo_starting_hands[player].add_filter('offer', suit, price, self.observed_cards(player), self.hand_trackers[player].get_net_difference())

        if new_info:
            for pid in self.oppo_starting_hands:
                self.oppo_starting_hands[pid].set_base(self.hand_trackers[pid].get_initial_cards(), 
                                                  self.starting_hand + self.observed_cards(self.player_id))


    def _handle_trade(self, buyer: str, seller: str, price: int, suit: str) -> None:
        # Did buyer meet seller's ask, or did seller meet buyer's bid?
        if self.market[suit]['bid'] is not None and price <= self.market[suit]['bid']:  # seller met buyer's bid
            if seller != self.player_id:
                self.oppo_starting_hands[seller].add_filter('offer', suit, price, self.observed_cards(seller), self.hand_trackers[seller].get_net_difference())
        else: # buyer met seller's ask
            if buyer != self.player_id:
                self.oppo_starting_hands[buyer].add_filter('bid', suit, price, self.observed_cards(buyer), self.hand_trackers[buyer].get_net_difference())

        self.market = Cards(Market(), Market(), Market(), Market())

        new_info = self.hand_trackers[seller].sold(suit)
        self.hand_trackers[buyer].bought(suit)

        if new_info:
            for pid in self.oppo_starting_hands:
                self.oppo_starting_hands[pid].set_base(self.hand_trackers[pid].get_initial_cards(), 
                                                  self.starting_hand + self.observed_cards(self.player_id))


    def _handle_cancel(
        self,
        order_type: Literal['bid', 'offer'],
        old_player: str,
        old_price: int, 
        new_player: str | None,
        new_price: int | None,
        suit: str
    ) -> None:
        """
        Handle repricing of an order.
        """
        self.market[suit][order_type] = new_price
        self.oppo_starting_hands[old_player].remove_filter(order_type, suit)
