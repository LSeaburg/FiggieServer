# agent.py

import os
import time
import random
import requests
from figgie_interface import FiggieInterface

SUITS = ["spades", "clubs", "hearts", "diamonds"]

# This file launches 4 agents that perform random actions, including bids, offers,
# and cancellations.  This should be mainly used as a reference for how to program 
# actions.
# For more control over agent behavior and for an easier deployment framework see
# the system layed out in dispatcher.py.

def make_client(name, server_url="http://localhost:8000", polling_rate=0.1):
    fig = FiggieInterface(server_url, name=name, polling_rate=polling_rate)

    @fig.on_start
    def on_start(hand, other_players):
        print(f"[{name}] → Round started, my hand: {hand}")

    @fig.on_tick
    def on_tick(time_left):
        print(f"[{name}] → Time left: {time_left}s")
        # 2.5% chance each tick to cancel all bids and offers
        if random.random() < 0.025:
            try:
                res = fig.cancel_all_bids_and_offers()
                print(f"[{name}] → CANCEL ALL BIDS AND OFFERS => {res}")
            except requests.HTTPError as e:
                print(f"[{name}] → CANCEL ALL failed: {e.response.status_code} {e.response.text}")
            except Exception as e:
                print(f"[{name}] → Tick handler error (cancel): {e}")
        # 10% chance each tick to place a random bid or offer
        if random.random() < 0.2:
            suit = random.choice(SUITS)
            price = random.randint(1, 20)
            # Determine action type for logging
            if random.random() < 0.5:
                action = "BID"
                operation = fig.bid
            else:
                action = "OFFER"
                operation = fig.offer
            try:
                res = operation(price, suit)
                print(f"[{name}] → {action} {price}@{suit} => {res}")
            except requests.HTTPError as e:
                print(f"[{name}] → {action} {price}@{suit} failed: {e.response.status_code} {e.response.text}")
            except Exception as e:
                print(f"[{name}] → Tick handler error: {e}")

    @fig.on_bid
    def on_bid(player, value, suit):
        print(f"[{name}]    [EVENT] {player} bids {value}@{suit}")

    @fig.on_offer
    def on_offer(player, value, suit):
        print(f"[{name}]    [EVENT] {player} offers {value}@{suit}")

    @fig.on_transaction
    def on_bought(buyer, seller, price, suit):
        print(f"[{name}]    [TRADE] {buyer} bought {suit}@{price} from {seller}")

    @fig.on_cancel
    def on_cancel(otype, old_p, old_v, new_p, new_v, suit):
        print(
            f"[{name}]    [CANCEL] best {otype} for {suit} changed "
            f"{old_p}@{old_v} → {new_p}@{new_v}"
        )

    return fig


def main():
    num = int(os.getenv("NUM_PLAYERS", "4"))
    print(f"Spawning {num} agents…")
    clients = [
        make_client(f"Agent{i}", polling_rate=0.25)
        for i in range(1, num + 1)
    ]

    # wait until at least one client sees the round completed
    try:
        while True:
            time.sleep(1)
            # Check for round completion
            completed_client = next(
                (c for c in clients if c._last_state and c._last_state.state == "completed"),
                None
            )
            if not completed_client:
                continue

            # Round completed, output final results
            print("\n→ Detected round completion.")
            print("--- Final Results ---")

            final_state = completed_client._last_state
            # Optional players info (list of player dicts) on the State object
            players = getattr(final_state, 'players', None)
            if players:
                print("\nPlayer Stats:")
                for player_info in players:

                    # Hand is now a dictionary of suit counts
                    print(f"  Hand: {player_info.get('hand', {})}")
                    print(f"  Money: ${player_info.get('money', 0)}")

            # Optional results info on the State object
            results = getattr(final_state, 'results', None)
            if results:
                print("\nRound Outcome:")
                print(f"  Goal Suit: {results.get('goal_suit', 'N/A')}")
                print(f"  Suit Counts: {results.get('counts', {})}")
                print(f"  Bonuses: {results.get('bonuses', {})}")
                print(f"  Winners: {results.get('winners', [])}")
                print(f"  Share each: ${results.get('share_each', 0)}")
                # Print all players' hands
                hands = getattr(final_state, 'hands', None)
                if hands:
                    print("\nFinal Hands:")
                    for pid, hand in hands.items():
                        print(f"  {pid}: {hand}")

            print("\n→ Shutting down agents.")
            break
    except KeyboardInterrupt:
        pass
    finally:
        for c in clients:
            c.stop()


if __name__ == "__main__":
    main()
