# Local Figgie Server

This module implements a local server for running rounds of the card game **Figgie**. It provides a REST API for clients (typically agents) to:

- Join a game
- Query the current game state
- Place or cancel orders during the trading phase

Official implementation: https://www.figgie.com

---

## Environment Variables

- `PORT`: TCP port for the Flask server (default: 5000)
- `NUM_PLAYERS`: Players required to start a round (4 or 5; default: 4)
- `TRADING_DURATION`: Duration of trading phase in seconds (default: 240)

These can be set in your shell or in `docker-compose.yml` under the `environment` block.

---

## Game Flow

1. **Waiting**: Server waits for `NUM_PLAYERS` clients to call `/join`.
2. **Trading**: Once enough players have joined, the server deals cards and enters the trading phase. Clients may place or cancel orders via `/action`.
3. **Completed**: After trading time elapses or no further actions occur, the server computes results. The next `/join` resets the game.

---

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
  - Missing or empty `name`
  - Game is full or not in the `waiting` state

### GET /state
Fetch the current game state for a specific player.

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
    }
  }
  ```
- Errors (400 Bad Request):
  - Missing or invalid `player_id`

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
    "price": <positive-integer>

    // for "cancel":
    "order_type": "buy" | "sell" | "both",
    "suit": "spades" | "clubs" | "hearts" | "diamonds" | "all",
    "price": <positive-integer> | -1
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

## Differences from Official Implementation

This project has several intentional differences when compared to the official implementation.

1. You can successfully place orders that are worse than or equal to the current best order (bids that are lower than the current bid, asks higher than the current ask). Placing orders first gives priority, so this change will only make a material difference when orders are cancelled (these orders are not broadcast until the current order is cancelled).

2. In the official implementation, a person that places a bid and an ask on a suit that would result in a strike would effectively cancel all bids and asks on said suit. In this implementation, attempting to place an order that would result in a strike with oneself returns a 400 error.

3. Clients are given more control over order cancellation. Instead of having to cancel all orders of a specific type, clients can choose to only cancel orders of specific amounts. 

4. The server doesn't offer a way to buy or sell a card, effectively allowing a client to auto-accept the best bid or ask. Instead a client has to make an offer that will hit the strike price and execute a trade.

5. This implementation gives the ability to have variable round time. However, in order to keep similarity with the official implementation, remaining time as returned by a call to `state` is always given as an int in the range of (0, 240). If a round is 60 seconds long, every real second passed decrements the remaining time by 4 counts. In this example agents are able to experience the same simulated experience by increasing the polling rate by a factor of 4. 

While it wouldn't be difficult to bring the behavior of this server closer in line to that of the official Figgie implementation, I currently intend to keep these changes. They are minor enough as to not majorly impact any of the agent's behavior and are all features that would be expected to be seen in a real exchange.

For example, none of the official Jane Street bots cancel orders. The few times I have seen players on Figgie.com cancel orders were in matches against bots that were using order cancellation as a form of abuse.