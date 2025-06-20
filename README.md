# Local Figgie Server

This project implements a server for running rounds of the Figgie game. It provides a REST API for agents (or clients) to join a game, query game state, and place or cancel orders during the trading phase.

Official implementation: https://www.figgie.com

Built with Python 3.13

## Table of Contents

- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Game Flow](#game-flow)
- [API Endpoints](#api-endpoints)
  - [`POST /join`](#post-join)
  - [`GET /state`](#get-state)
  - [`POST /action`](#post-action)
- [Request & Response Formats](#request--response-formats)
- [Error Handling](#error-handling)
- [Creating Your Agent](#creating-your-agent)
- [Differences from Official Implementation](#differences-from-official-implementation)
- [Future Roadmap](#future-roadmap)

## Getting Started

1. Clone the repository:
  ```shell
  git clone git@github.com:LSeaburg/FiggieServer.git
  cd FiggieServer
  ```

2. Create virtualenv (optional)
  ```shell
  python -m venv my_venv
  source .my_venv/bin/activate
  ```

3. Install dependencies:
  ```shell
  pip install -r requirements.txt
  ```

4. Run the server:
  ```shell
  docker compose up --build -d
  ```

The server will start on `http://localhost:8000`.

  Alternatively, without Docker
   ```shell
   export PORT=5000          # optional, defaults to 5000
   export NUM_PLAYERS=4      # optional, 4 or 5 players
   export TRADING_DURATION=240  # optional, trading phase duration in seconds
   python figgie_server/api.py
   ```

The server will start on `http://0.0.0.0:$PORT`.

5. Run sample agents:
  ```shell 
  python agents/random_agents.py
  ```

### Code Coverage

You can run code coverage with:
```shell
coverage run -m pytest
coverage report -m
coverage html
```

## Environment Variables

- `PORT`: TCP port for the Flask server (default: 5000).
- `NUM_PLAYERS`: Number of players to wait for before starting a round (must be 4 or 5; default: 4).
- `TRADING_DURATION`: Duration of the trading phase in seconds (default: 240).

## Game Flow

1. **Waiting**: Server waits for `NUM_PLAYERS` to call `/join`.
2. **Trading**: Once enough players have joined, server deals cards and starts the trading phase. Clients may place or cancel orders.
3. **Completed**: After trading time elapses (or no more actions), server computes results and accepts no further trading requests. A new `/join` after completion resets the game.

## API Endpoints

### POST /join
Register a new player for the next round.

- Request body (JSON):
  ```json
  { "name": "PlayerName" }
  ```
- Response (200 OK):
  ```json
  { "player_id": "<unique-player-id>" }
  ```
- Errors (400 Bad Request):
  - Missing or empty `name`.
  - Game is already full or not in the `waiting` state.

### GET /state
Fetch the current game state from the perspective of a specific player.

- Query parameters:
  - `player_id`: Unique player identifier returned by `/join`.

- Response (200 OK):
  ```
  {
    "state": "waiting|trading|completed",
    "time_left": <int|null>,     // normalized 0–240 units during trading, null otherwise
    "pot": <int>,                // current pot size in dollars
    "hand": {                    // your current hand counts per suit
      "spades": <int>,
      "clubs": <int>,
      "hearts": <int>,
      "diamonds": <int>
    },
    "market": {                  // highest bid and lowest ask per suit
      "spades": { "highest_bid": {"player_id":"...","price":<int>}, "lowest_ask": {...} },
      ...
    },
    "balances": {"<pid>":<int>, ...},
    "trades": [                  // list of executed trades so far
      { "buyer":"<pid>", "seller":"<pid>", "suit":"hearts", "price":<int> },
      ...
    ],
    // only present when state == "completed":
    "results": {                // round results
      "goal_suit": "hearts",
      "counts": {"<pid>":<int>, ...},
      "bonuses": {"<pid>":<int>, ...},
      "winners": ["<pid>", ...],
      "share_each": <int>
    },
    "hands": {"<pid>": { ... }, ...} // all players' final hands when completed
    "initial_balances": {"<pid>": <int>, ...}   // all players' initial balance
  }
  ```
- Errors (400 Bad Request):
  - Missing or invalid `player_id`.

### POST /action
Place or cancel orders during the trading phase.

- Request body (JSON):
  ```
  {
    "player_id": "<your-player-id>",
    "action_type": "order" | "cancel",
    // for "order":
    "order_type": "buy" | "sell",
    "suit": "spades" | "clubs" | "hearts" | "diamonds",
    "price": <positive-integer>,

    // for "cancel":
    "order_type": "buy" | "sell" | "both",
    "suit": "spades" | "clubs" | "hearts" | "diamonds" | "all",
    "price": <positive-integer> | -1,
  }
  ```

- Success response (200 OK):
  - **Order**: returns either `{"order_id": "<id>"}` or a matched trade `{"trade": {...}}`.
  - **Cancel**: returns `{"canceled": ["<order_id>", ...]}`.

- Errors (400 Bad Request):
  - Invalid `player_id`.
  - Trading not active.
  - Invalid action type or missing fields.
  - Business logic errors (e.g., insufficient funds, duplicate order).

#### Bulk Cancel Details
- `suit`: specific suit or `"all"` to apply across all suits.
- `price`: integer threshold or `-1` to cancel all of your orders.
- Cancels buy orders with price ≥ threshold, sell orders with price ≤ threshold.

## Error Handling

All error responses use HTTP status 400 with JSON:
```json
{ "error": "<error message>" }
```

Clients should handle these gracefully and adjust behavior accordingly.

## Creating Your Agent

This section shows how to use the `FiggieInterface` to implement a custom trading agent. An agent joins the game, registers event handlers, and places orders programmatically based on game events.

### Example Agent

```python
from agents.figgie_interface import FiggieInterface
import time

# Initialize the interface with your server URL and agent name
def main():
    interface = FiggieInterface(
        server_url="http://localhost:5000",
        name="MyAgent"
    )

    # Called once when trading starts, providing your initial hand
    @interface.on_start
    def handle_start(hand):
        print("Game started. Your hand:", hand)

        # Example: place an initial bid of 10 on spades
        interface.bid(10, "spades")

    # Called on every tick (every polling interval) with seconds left
    @interface.on_tick
    def handle_tick(time_left):
        print(f"Time left: {time_left}s")
        # e.g., adjust strategy or cancel/modify orders

    # Called when any player places a new highest bid
    @interface.on_bid
    def handle_bid(player_id, price, suit):
        print(f"New highest bid by {player_id}: {price} on {suit}")

    # Called when any player places a new lowest ask
    @interface.on_offer
    def handle_offer(player_id, price, suit):
        print(f"New best offer by {player_id}: {price} on {suit}")

    # Called when an order is canceled or replaced
    @interface.on_cancel
    def handle_cancel(order_type, old_pid, old_price, new_pid, new_price, suit):
        print(
            f"Order canceled: {order_type} {old_pid}@{old_price} replaced by {new_pid}@{new_price} on {suit}"
        )

    # Called on completed trades
    @interface.on_transaction
    def handle_transaction(buyer, seller, price, suit):
        print(
            f"Trade executed: {buyer} bought from {seller} at {price} on {suit}"
        )

    # Keep running until interrupted
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping agent...")
        interface.stop()

if __name__ == "__main__":
    main()
```

### Agent Capabilities

- `interface.bid(price: int, suit: str)`: Place a buy order.
- `interface.offer(price: int, suit: str)`: Place a sell order.
- `interface.buy(suit: str)`: Instantly buy one unit at the current best ask.
- `interface.sell(suit: str)`: Instantly sell one unit at the current best bid.
- `interface.cancel_bids_and_offers(suit: str)`: Cancel all your orders for a given suit.

**Event hooks**:
- `on_start(fn: Dict[str, Any] → None)`: Fired once when trading begins, with your initial hand.
- `on_tick(fn: float → None)`: Fired every polling cycle with remaining time (seconds).
- `on_bid(fn: str, int, str → None)`: Fired on new highest bids by any player.
- `on_offer(fn: str, int, str → None)`: Fired on new lowest asks by any player.
- `on_cancel(fn: str, Optional[str], int, Optional[str], Optional[int], str → None)`: Fired when orders are canceled or outbid.
- `on_transaction(fn: str, str, int, str → None)`: Fired on each completed trade.

## Differences from Official Implementation

This project has several intentional differences when compared to the official implementation.

1. You are sucessfully able to place orders that are worse than or equal to the the current best order (bids that are lower than the current bid, asks higher than the current ask). Placing orders first gives priority, so this change will only make a material difference when orders are cancelled (these orders are not broadcast until the current order is cancelled).

2. In the official implementation, a person that places a bid and an ask on a suit that would result in a strike would effectively cancel all bids and asks on said suit. In this implementation, attempting to place an order that would result in a strike with oneself return a 400 error. 

3. Clients are given more control over order cancellation. Instead of having to cancel all orders of a specific type, clients can choose to only cancel orders of specific amounts. 

4. The server doesn't offer a way to buy or sell a card, effectively allowing a client to auto-accept the best bid or ask. Instead a client has to make an offer that will hit the strike price and execute a trade.

5. This implementation gives the ability to have variable round time. However, in order to keep similarity with the official implementation, remaining time as returned by a call to `state` is always given as an int in the range of (0, 240). If a round is 60 seconds long, every real second passed decrements the remaining time by 4 counts. In this example agents are able to experience the same simulated experience by increasing the polling rate by a factor of 4. 

While it wouldn't be difficult to bring the behavior of this server closer in line to that of the official Figgie implementation, I currently intend to keep these changes. They are minor enough as to not majorly impact any of the agent's behavior and are all features that would be expected to be seen in a real exchange.

For example, none of the official Jane Street bots cancel orders. The few times I have seen players on Figgie.com cancel orders were in matches against bots that were using order cancellation as a form of abuse.

## Future Roadmap

This project is under active development.

There are several improvements that could be made to the server. To name a few:

1. Communicating through web sockets instead of repeatedly polling `state`.

2. Allowing multiple rooms on a server.

3. Allowing player number and round duration to be configured on a per-room basis.

4. Allowing persisting rooms where the reamaining balances from one round carry to the next.

5. Securing calls to prevent other actors from getting info on an opponent's hand of cards with just a player id.

6. Adding a GUI.

While all of these features would undoubtedly make for a better Figgie server, none of these will be prioritized. This project's main goal is to allow for the creation and evaluation of agents, not to recreate the official implementation of the game. 

### Building Out Agents

Plans for this project are to implement different trading strategies and evaluate performance.

The largest priority at this time is to develop a better framework/pipeline for running agents and tracking evaluation metrics.

Some of the agents to be developed include:

1. A noise trader

2. A replication of the fundamentalist agent described in [this paper](https://arxiv.org/pdf/2110.00879)

3. A version of the fundamentalist strategy that includes infrences based on the behavior of other players

4. Other implementations of various agents described in prior implementations, such as in [this project](https://github.com/0xDub/figgie-auto)

5. A game-theory centered analysis and approach

After creating a few different agent strategies I plan on adding a way to implement reinforcement learning to improve agent performance.