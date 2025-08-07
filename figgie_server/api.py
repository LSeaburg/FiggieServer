import threading
from flask import Flask, request, jsonify, current_app

from figgie_server.game import NUM_PLAYERS

app = Flask(__name__)
lock = threading.Lock()

@app.route("/join", methods=["POST"])
def join():
    data = request.get_json(force=True)
    name = data.get("name")
    if not name:
        return jsonify(error="Name is required"), 400
    with lock:
        if current_app.game.state == "completed":
            current_app.game.reset()
        if current_app.game.state != "waiting":
            return jsonify(error="Cannot join right now"), 400
        if len(current_app.game.players) >= NUM_PLAYERS:
            return jsonify(error="Game is full"), 400
        pid = current_app.game.add_player(name)
        if current_app.game.can_start():
            current_app.game.start_round()
    return jsonify(player_id=pid), 200

@app.route("/state", methods=["GET"])
def state():
    pid = request.args.get("player_id")
    if not pid or pid not in current_app.game.players:
        return jsonify(error="Invalid or missing player_id"), 400
    with lock:
        resp = current_app.game.get_state(req_pid=pid)
    return jsonify(resp), 200

@app.route("/action", methods=["POST"])
def action():
    data = request.get_json(force=True)
    pid = data.get("player_id")
    if not pid or pid not in current_app.game.players:
        return jsonify(error="Invalid player_id"), 400
    if current_app.game.state != "trading":
        return jsonify(error="Trading not active"), 400
    with lock:
        atype = data.get("action_type")
        if atype == "order":
            result, err = current_app.game.place_order(pid,
                                          data.get("order_type"),
                                          data.get("suit"),
                                          data.get("price"))
            if err:
                return jsonify(error=err), 400
            return jsonify(success=True, **result), 200
        if atype == "cancel":
            result, err = current_app.game.cancel_order(pid,
                                          data.get("order_type"),
                                          data.get("suit"),
                                          data.get("price"))
            if err:
                return jsonify(error=err), 400
            return jsonify(success=True, **result), 200
        return jsonify(error="Invalid action type"), 400

@app.route("/status", methods=["GET"])
def status():
    return jsonify(status=current_app.game.get_game_status()), 200