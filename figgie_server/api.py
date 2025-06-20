import os
import threading
from flask import Flask, request, jsonify

from figgie_server.game import Game, NUM_PLAYERS

app = Flask(__name__)
lock = threading.Lock()

game = Game()

@app.route("/join", methods=["POST"])
def join():
    data = request.get_json(force=True)
    name = data.get("name")
    if not name:
        return jsonify(error="Name is required"), 400
    with lock:
        if game.state == "completed":
            game.reset()
        if game.state != "waiting":
            return jsonify(error="Cannot join right now"), 400
        if len(game.players) >= NUM_PLAYERS:
            return jsonify(error="Game is full"), 400
        pid = game.add_player(name)
        if game.can_start():
            game.start_round()
    return jsonify(player_id=pid), 200

@app.route("/state", methods=["GET"])
def state():
    pid = request.args.get("player_id")
    if not pid or pid not in game.players:
        return jsonify(error="Invalid or missing player_id"), 400
    with lock:
        resp = game.get_state(req_pid=pid)
    return jsonify(resp), 200

@app.route("/action", methods=["POST"])
def action():
    data = request.get_json(force=True)
    pid = data.get("player_id")
    if not pid or pid not in game.players:
        return jsonify(error="Invalid player_id"), 400
    if game.state != "trading":
        return jsonify(error="Trading not active"), 400
    with lock:
        atype = data.get("action_type")
        if atype == "order":
            result, err = game.place_order(pid,
                                          data.get("order_type"),
                                          data.get("suit"),
                                          data.get("price"))
            if err:
                return jsonify(error=err), 400
            return jsonify(success=True, **result), 200
        if atype == "cancel":
            result, err = game.cancel_order(pid,
                                          data.get("order_type"),
                                          data.get("suit"),
                                          data.get("price"))
            if err:
                return jsonify(error=err), 400
            return jsonify(success=True, **result), 200
        return jsonify(error="Invalid action type"), 400

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", debug=True, port=port)
