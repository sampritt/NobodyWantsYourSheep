from app import app, games, socketio


def payload(client_id, **extra):
    return {"client_id": client_id, **extra}


def latest_state(client):
    states = [event["args"][0] for event in client.get_received() if event["name"] == "state"]
    return states[-1] if states else None


def test_three_clients_can_create_join_and_start_lobby():
    games.clear()
    clients = [socketio.test_client(app) for _ in range(3)]
    try:
        clients[0].emit("create_game", payload("a", username="Ada"))
        state = latest_state(clients[0])
        code = state["code"]

        clients[1].emit("join_game", payload("b", username="Ben", code=code))
        clients[2].emit("join_game", payload("c", username="Cy", code=code))
        latest_state(clients[0])
        clients[0].emit("start_game", payload("a", code=code))

        host_state = latest_state(clients[0])
        guest_state = latest_state(clients[1])
        assert host_state["status"] == "playing"
        assert guest_state["status"] == "playing"
        assert len(host_state["players"]) == 3
        assert host_state["board"] is not None
    finally:
        for client in clients:
            client.disconnect()

