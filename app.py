from __future__ import annotations

import os
import secrets
import threading
from typing import Any, Callable

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

from catan import CatanGame, GameError

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

games: dict[str, CatanGame] = {}
client_games: dict[str, str] = {}
sid_clients: dict[str, str] = {}
lock = threading.RLock()


def normalize_code(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())[:6]


def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(5))
        if code not in games:
            return code


def broadcast_game(game: CatanGame) -> None:
    for player in game.players:
        socketio.emit("state", game.serialize(player.id), to=f"client:{player.id}")


def current_context(payload: dict[str, Any] | None = None) -> tuple[CatanGame, str]:
    payload = payload or {}
    client_id = str(payload.get("client_id") or sid_clients.get(request.sid) or "")
    code = normalize_code(str(payload.get("code") or client_games.get(client_id) or ""))
    if not client_id or code not in games:
        raise GameError("Join a game first.")
    game = games[code]
    game._player(client_id)
    return game, client_id


def game_event(handler: Callable[[CatanGame, str, dict[str, Any]], Any]) -> Callable:
    def wrapped(payload: dict[str, Any] | None = None) -> None:
        try:
            with lock:
                data = payload or {}
                game, client_id = current_context(data)
                result = handler(game, client_id, data)
                broadcast_game(game)
                if result is not None:
                    emit("action_result", result)
        except (GameError, ValueError, TypeError) as exc:
            emit("error_message", {"message": str(exc)})

    wrapped.__name__ = handler.__name__
    return wrapped


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"ok": True, "games": len(games)})


@socketio.on("connect")
def connected():
    emit("connected", {"ok": True})


@socketio.on("identify")
def identify(payload: dict[str, Any]):
    client_id = str(payload.get("client_id", "")).strip()[:80]
    if not client_id:
        emit("error_message", {"message": "Missing player identity."})
        return
    sid_clients[request.sid] = client_id
    join_room(f"client:{client_id}")
    code = client_games.get(client_id)
    if code and code in games:
        with lock:
            game = games[code]
            try:
                player = game._player(client_id)
            except GameError:
                return
            player.connected = True
            join_room(code)
            emit("state", game.serialize(client_id))
            broadcast_game(game)


@socketio.on("create_game")
def create_game(payload: dict[str, Any]):
    try:
        with lock:
            client_id = str(payload.get("client_id", "")).strip()[:80]
            username = str(payload.get("username", ""))
            if not client_id:
                raise GameError("Missing player identity.")
            if client_id in client_games and client_games[client_id] in games:
                old_game = games[client_games[client_id]]
                if old_game.status != "finished":
                    raise GameError("You are already seated in an active game.")
            code = new_code()
            game = CatanGame(code, client_id, username)
            games[code] = game
            client_games[client_id] = code
            sid_clients[request.sid] = client_id
            join_room(code)
            join_room(f"client:{client_id}")
            emit("state", game.serialize(client_id))
    except (GameError, ValueError) as exc:
        emit("error_message", {"message": str(exc)})


@socketio.on("join_game")
def join_game_event(payload: dict[str, Any]):
    try:
        with lock:
            client_id = str(payload.get("client_id", "")).strip()[:80]
            username = str(payload.get("username", ""))
            code = normalize_code(str(payload.get("code", "")))
            if not client_id:
                raise GameError("Missing player identity.")
            if client_id in client_games and client_games[client_id] in games:
                existing_game = games[client_games[client_id]]
                if existing_game.code != code and existing_game.status != "finished":
                    raise GameError("You are already seated in an active game.")
            if code not in games:
                raise GameError("No island was found with that code.")
            game = games[code]
            game.add_player(client_id, username)
            client_games[client_id] = code
            sid_clients[request.sid] = client_id
            join_room(code)
            join_room(f"client:{client_id}")
            broadcast_game(game)
            if len(game.players) == 4 and game.status == "lobby":
                game.start(game.host_id)
                broadcast_game(game)
    except (GameError, ValueError) as exc:
        emit("error_message", {"message": str(exc)})


@socketio.on("leave_game")
def leave_game_event(payload: dict[str, Any] | None = None):
    try:
        with lock:
            game, client_id = current_context(payload)
            if game.status != "lobby":
                raise GameError("Started games keep your seat so you can reconnect.")
            player = game._player(client_id)
            game.players.remove(player)
            client_games.pop(client_id, None)
            leave_room(game.code)
            if not game.players:
                games.pop(game.code, None)
            else:
                if game.host_id == client_id:
                    game.host_id = game.players[0].id
                broadcast_game(game)
            emit("left_game", {"ok": True})
    except GameError as exc:
        emit("error_message", {"message": str(exc)})


@socketio.on("disconnect")
def disconnected():
    client_id = sid_clients.pop(request.sid, None)
    if not client_id:
        return
    code = client_games.get(client_id)
    if code in games:
        with lock:
            game = games[code]
            try:
                game._player(client_id).connected = False
                broadcast_game(game)
            except GameError:
                pass


@socketio.on("start_game")
@game_event
def start_game(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.start(client_id)


@socketio.on("setup_settlement")
@game_event
def setup_settlement(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.place_setup_settlement(client_id, str(payload["vertex_id"]))


@socketio.on("setup_road")
@game_event
def setup_road(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.place_setup_road(client_id, str(payload["edge_id"]))


@socketio.on("roll_dice")
@game_event
def roll_dice(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.roll_dice(client_id)


@socketio.on("discard")
@game_event
def discard(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.discard(client_id, payload.get("cards", {}))


@socketio.on("move_robber")
@game_event
def move_robber(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.move_robber(client_id, str(payload["hex_id"]))


@socketio.on("steal")
@game_event
def steal(game: CatanGame, client_id: str, payload: dict[str, Any]):
    resource = game.steal(client_id, str(payload["victim_id"]))
    return {"type": "stolen_resource", "resource": resource}


@socketio.on("build")
@game_event
def build(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.build(client_id, str(payload["kind"]), str(payload["location_id"]))


@socketio.on("buy_development")
@game_event
def buy_development(game: CatanGame, client_id: str, payload: dict[str, Any]):
    card = game.buy_development_card(client_id)
    return {"type": "development_card", "card": card}


@socketio.on("play_development")
@game_event
def play_development(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.play_development_card(client_id, str(payload["card_type"]), payload.get("choice"))


@socketio.on("finish_road_building")
@game_event
def finish_road_building(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.finish_road_building(client_id)


@socketio.on("maritime_trade")
@game_event
def maritime_trade(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.maritime_trade(client_id, str(payload["give"]), str(payload["receive"]))


@socketio.on("offer_trade")
@game_event
def offer_trade(game: CatanGame, client_id: str, payload: dict[str, Any]):
    raw_target = payload.get("target_id")
    game.offer_trade(
        client_id,
        str(raw_target) if raw_target else None,
        payload.get("give", {}),
        payload.get("receive", {}),
    )


@socketio.on("cancel_trade")
@game_event
def cancel_trade(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.cancel_trade(client_id, str(payload["offer_id"]))


@socketio.on("respond_trade")
@game_event
def respond_trade(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.respond_trade(client_id, str(payload["offer_id"]), bool(payload.get("accept")))


@socketio.on("end_turn")
@game_event
def end_turn(game: CatanGame, client_id: str, payload: dict[str, Any]):
    game.end_turn(client_id)


if __name__ == "__main__":
    socketio.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
        allow_unsafe_werkzeug=True,
    )
