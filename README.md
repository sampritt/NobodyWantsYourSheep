# Settlers' Table

A server-authoritative, real-time implementation of the 3-4 player Catan base game.

## Included rules

- Random 19-hex board, balanced number tokens, nine randomized harbors
- Official reverse-order initial placement and second-settlement resources
- Resource production, bank shortages, robber discards, movement, and random theft
- Domestic offers and counteroffers plus 4:1, 3:1, and 2:1 maritime trade
- Roads, settlements, cities, distance rule, piece limits, and interrupted road networks
- Full development deck: Knight, Road Building, Year of Plenty, Monopoly, and hidden VP cards
- Largest Army, exact longest-road trail scoring, hidden scores, and turn-scoped victory
- Reconnectable seats and private player state over Socket.IO

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

For a production-style launch:

```bash
gunicorn --worker-class gthread --threads 100 --bind 0.0.0.0:5000 app:app
```

The in-memory room store intentionally uses one Gunicorn worker. For horizontal deployment, move
game snapshots to Redis or a database and configure Flask-SocketIO with a Redis message queue.

