from __future__ import annotations

import random
import secrets
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from .board import RESOURCE_BY_TERRAIN, TOPOLOGY, generate_board

RESOURCES = ("brick", "lumber", "wool", "grain", "ore")
PLAYER_COLORS = ("#e65b45", "#2b79d1", "#f2b134", "#f4f0df")
BUILD_COSTS = {
    "road": {"brick": 1, "lumber": 1},
    "settlement": {"brick": 1, "lumber": 1, "wool": 1, "grain": 1},
    "city": {"ore": 3, "grain": 2},
    "development": {"ore": 1, "wool": 1, "grain": 1},
}
DEVELOPMENT_DECK = (
    ["knight"] * 14
    + ["road_building"] * 2
    + ["year_of_plenty"] * 2
    + ["monopoly"] * 2
    + ["victory_point"] * 5
)


class GameError(ValueError):
    pass


@dataclass
class Player:
    id: str
    username: str
    color: str
    connected: bool = True
    resources: Counter[str] = field(default_factory=Counter)
    development_cards: list[dict[str, Any]] = field(default_factory=list)
    roads: set[str] = field(default_factory=set)
    settlements: set[str] = field(default_factory=set)
    cities: set[str] = field(default_factory=set)
    played_knights: int = 0

    def resource_total(self) -> int:
        return sum(self.resources.values())

    def hidden_victory_points(self) -> int:
        return sum(card["type"] == "victory_point" for card in self.development_cards)


class CatanGame:
    def __init__(self, code: str, host_id: str, host_username: str, seed: int | None = None):
        self.code = code
        self.host_id = host_id
        self.rng = random.Random(seed if seed is not None else secrets.randbits(64))
        self.players: list[Player] = []
        self.status = "lobby"
        self.board: dict[str, Any] | None = None
        self.bank = Counter({resource: 19 for resource in RESOURCES})
        self.development_deck: list[str] = []
        self.turn_order: list[str] = []
        self.active_player_id: str | None = None
        self.turn_number = 0
        self.phase = "lobby"
        self.setup_sequence: list[str] = []
        self.setup_step = 0
        self.setup_pending_vertex: str | None = None
        self.discard_required: dict[str, int] = {}
        self.pending_robber_reason: str | None = None
        self.pending_development_return_phase: str | None = None
        self.pending_free_roads = 0
        self.played_development_this_turn = False
        self.longest_road_holder: str | None = None
        self.largest_army_holder: str | None = None
        self.trade_offers: dict[str, dict[str, Any]] = {}
        self._trade_lock = threading.RLock()
        self.log: list[str] = []
        self.winner_id: str | None = None
        self.last_roll: tuple[int, int] | None = None
        self.add_player(host_id, host_username)

    def _player(self, player_id: str) -> Player:
        player = next((item for item in self.players if item.id == player_id), None)
        if not player:
            raise GameError("Player not found.")
        return player

    def add_player(self, player_id: str, username: str) -> Player:
        if self.status != "lobby":
            raise GameError("This game has already started.")
        existing = next((player for player in self.players if player.id == player_id), None)
        if existing:
            existing.connected = True
            return existing
        if len(self.players) >= 4:
            raise GameError("This island already has four settlers.")
        normalized = " ".join(username.strip().split())[:24]
        if not normalized:
            raise GameError("Enter a gamer tag.")
        if any(player.username.casefold() == normalized.casefold() for player in self.players):
            raise GameError("That gamer tag is already seated.")
        player = Player(player_id, normalized, PLAYER_COLORS[len(self.players)])
        self.players.append(player)
        self.log.append(f"{normalized} joined the expedition.")
        return player

    def start(self, player_id: str) -> None:
        if player_id != self.host_id:
            raise GameError("Only the host can launch the game.")
        if self.status != "lobby":
            raise GameError("The game has already started.")
        if len(self.players) < 3:
            raise GameError("Catan needs at least three players.")
        self.status = "playing"
        self.board = generate_board(self.rng)
        self.development_deck = list(DEVELOPMENT_DECK)
        self.rng.shuffle(self.development_deck)
        self.turn_order = [player.id for player in self.players]
        self.rng.shuffle(self.turn_order)
        self.setup_sequence = self.turn_order + list(reversed(self.turn_order))
        self.setup_step = 0
        self.active_player_id = self.setup_sequence[0]
        self.phase = "setup_settlement"
        self.log.append(
            f"The island is revealed. {self._player(self.active_player_id).username} places first."
        )

    def _require_active(self, player_id: str) -> Player:
        if self.status != "playing":
            raise GameError("The game is not active.")
        if player_id != self.active_player_id:
            raise GameError("Wait for your turn.")
        return self._player(player_id)

    def _require_phase(self, *phases: str) -> None:
        if self.phase not in phases:
            raise GameError("That action is not available right now.")

    def _building_at(self, vertex_id: str) -> tuple[str, str] | None:
        for player in self.players:
            if vertex_id in player.settlements:
                return player.id, "settlement"
            if vertex_id in player.cities:
                return player.id, "city"
        return None

    def _road_owner(self, edge_id: str) -> str | None:
        for player in self.players:
            if edge_id in player.roads:
                return player.id
        return None

    def _pay(self, player: Player, cost: dict[str, int]) -> None:
        if any(player.resources[resource] < amount for resource, amount in cost.items()):
            raise GameError("You do not have the resources for that.")
        for resource, amount in cost.items():
            player.resources[resource] -= amount
            self.bank[resource] += amount

    def _can_afford(self, player: Player, item: str) -> bool:
        return all(
            player.resources[resource] >= amount
            for resource, amount in BUILD_COSTS[item].items()
        )

    def _distance_rule_allows(self, vertex_id: str) -> bool:
        if self._building_at(vertex_id):
            return False
        return not any(
            self._building_at(neighbor)
            for neighbor in TOPOLOGY["vertex_neighbors"].get(vertex_id, [])
        )

    def legal_settlements(self, player_id: str, setup: bool = False) -> list[str]:
        player = self._player(player_id)
        legal = []
        for vertex_id in TOPOLOGY["vertex_positions"]:
            if not self._distance_rule_allows(vertex_id):
                continue
            if setup:
                legal.append(vertex_id)
            elif any(edge_id in player.roads for edge_id in TOPOLOGY["vertex_edges"][vertex_id]):
                legal.append(vertex_id)
        return legal

    def legal_roads(self, player_id: str, setup_vertex: str | None = None) -> list[str]:
        player = self._player(player_id)
        legal = []
        for edge_id, vertices in TOPOLOGY["edge_vertices"].items():
            if self._road_owner(edge_id):
                continue
            if setup_vertex:
                if setup_vertex in vertices:
                    legal.append(edge_id)
                continue
            for vertex_id in vertices:
                building = self._building_at(vertex_id)
                if building and building[0] == player_id:
                    legal.append(edge_id)
                    break
                if building and building[0] != player_id:
                    continue
                if any(
                    adjacent in player.roads
                    for adjacent in TOPOLOGY["vertex_edges"][vertex_id]
                    if adjacent != edge_id
                ):
                    legal.append(edge_id)
                    break
        return legal

    def place_setup_settlement(self, player_id: str, vertex_id: str) -> None:
        player = self._require_active(player_id)
        self._require_phase("setup_settlement")
        if vertex_id not in self.legal_settlements(player_id, setup=True):
            raise GameError("That intersection violates the distance rule.")
        player.settlements.add(vertex_id)
        self.setup_pending_vertex = vertex_id
        self.phase = "setup_road"
        self.log.append(f"{player.username} founded a settlement.")

    def place_setup_road(self, player_id: str, edge_id: str) -> None:
        player = self._require_active(player_id)
        self._require_phase("setup_road")
        if edge_id not in self.legal_roads(player_id, self.setup_pending_vertex):
            raise GameError("Your road must touch the settlement you just placed.")
        player.roads.add(edge_id)
        if self.setup_step >= len(self.players):
            self._grant_starting_resources(player, self.setup_pending_vertex)
        self.setup_pending_vertex = None
        self.setup_step += 1
        if self.setup_step == len(self.setup_sequence):
            self.active_player_id = self.turn_order[0]
            self.phase = "roll"
            self.turn_number = 1
            self.log.append(
                f"Setup is complete. {self._player(self.active_player_id).username} begins."
            )
        else:
            self.active_player_id = self.setup_sequence[self.setup_step]
            self.phase = "setup_settlement"
        self._update_longest_road()

    def _grant_starting_resources(self, player: Player, vertex_id: str | None) -> None:
        if not vertex_id or not self.board:
            return
        by_id = {item["id"]: item for item in self.board["hexes"]}
        for hex_id in TOPOLOGY["vertex_hexes"][vertex_id]:
            resource = by_id[hex_id]["resource"]
            if resource and self.bank[resource]:
                self.bank[resource] -= 1
                player.resources[resource] += 1

    def roll_dice(self, player_id: str, dice: tuple[int, int] | None = None) -> tuple[int, int]:
        self._require_active(player_id)
        self._require_phase("roll")
        rolled = dice or (self.rng.randint(1, 6), self.rng.randint(1, 6))
        if any(value < 1 or value > 6 for value in rolled):
            raise GameError("Invalid dice.")
        self.last_roll = rolled
        total = sum(rolled)
        self.log.append(f"{self._player(player_id).username} rolled {total}.")
        if total == 7:
            self.discard_required = {
                player.id: player.resource_total() // 2
                for player in self.players
                if player.resource_total() > 7
            }
            self.pending_robber_reason = "roll"
            self.phase = "discard" if self.discard_required else "move_robber"
        else:
            self._produce(total)
            self.phase = "action"
            self._check_win()
        return rolled

    def _produce(self, number: int) -> None:
        if not self.board:
            return
        demands: dict[str, Counter[str]] = {player.id: Counter() for player in self.players}
        for hex_item in self.board["hexes"]:
            if hex_item["number"] != number or hex_item["id"] == self.board["robber_hex"]:
                continue
            resource = hex_item["resource"]
            for vertex_id in hex_item["vertices"]:
                building = self._building_at(vertex_id)
                if not building:
                    continue
                owner_id, kind = building
                demands[owner_id][resource] += 2 if kind == "city" else 1

        for resource in RESOURCES:
            claimants = [
                (self._player(player_id), demand[resource])
                for player_id, demand in demands.items()
                if demand[resource]
            ]
            total = sum(amount for _, amount in claimants)
            if total <= self.bank[resource]:
                for player, amount in claimants:
                    player.resources[resource] += amount
                    self.bank[resource] -= amount
            elif len(claimants) == 1:
                player, _ = claimants[0]
                amount = self.bank[resource]
                player.resources[resource] += amount
                self.bank[resource] = 0

    def discard(self, player_id: str, cards: dict[str, int]) -> None:
        self._require_phase("discard")
        required = self.discard_required.get(player_id)
        if required is None:
            raise GameError("You do not need to discard.")
        normalized = Counter({resource: int(cards.get(resource, 0)) for resource in RESOURCES})
        if any(amount < 0 for amount in normalized.values()) or sum(normalized.values()) != required:
            raise GameError(f"Choose exactly {required} resource cards.")
        player = self._player(player_id)
        if any(player.resources[resource] < amount for resource, amount in normalized.items()):
            raise GameError("You cannot discard cards you do not hold.")
        for resource, amount in normalized.items():
            player.resources[resource] -= amount
            self.bank[resource] += amount
        del self.discard_required[player_id]
        self.log.append(f"{player.username} returned {required} cards to the bank.")
        if not self.discard_required:
            self.phase = "move_robber"

    def legal_robber_hexes(self) -> list[str]:
        if not self.board:
            return []
        return [item["id"] for item in self.board["hexes"] if item["id"] != self.board["robber_hex"]]

    def move_robber(self, player_id: str, hex_id: str) -> list[str]:
        self._require_active(player_id)
        self._require_phase("move_robber")
        if hex_id not in self.legal_robber_hexes():
            raise GameError("The robber must move to a different terrain hex.")
        assert self.board is not None
        self.board["robber_hex"] = hex_id
        hex_item = next(item for item in self.board["hexes"] if item["id"] == hex_id)
        victims = []
        for vertex_id in hex_item["vertices"]:
            building = self._building_at(vertex_id)
            if building and building[0] != player_id:
                victim = self._player(building[0])
                if victim.resource_total() and victim.id not in victims:
                    victims.append(victim.id)
        self.log.append(f"{self._player(player_id).username} moved the robber.")
        if victims:
            self.phase = "steal"
        else:
            self._finish_robber()
        return victims

    def legal_victims(self, player_id: str) -> list[str]:
        if self.phase != "steal" or not self.board:
            return []
        hex_item = next(item for item in self.board["hexes"] if item["id"] == self.board["robber_hex"])
        victims = []
        for vertex_id in hex_item["vertices"]:
            building = self._building_at(vertex_id)
            if building and building[0] != player_id:
                victim = self._player(building[0])
                if victim.resource_total() and victim.id not in victims:
                    victims.append(victim.id)
        return victims

    def steal(self, player_id: str, victim_id: str) -> str:
        thief = self._require_active(player_id)
        self._require_phase("steal")
        if victim_id not in self.legal_victims(player_id):
            raise GameError("That player cannot be robbed.")
        victim = self._player(victim_id)
        cards = [resource for resource in RESOURCES for _ in range(victim.resources[resource])]
        resource = self.rng.choice(cards)
        victim.resources[resource] -= 1
        thief.resources[resource] += 1
        self.log.append(f"{thief.username} stole a card from {victim.username}.")
        self._finish_robber()
        return resource

    def _finish_robber(self) -> None:
        if self.pending_robber_reason == "knight":
            self.phase = self.pending_development_return_phase or "action"
            self.pending_development_return_phase = None
        else:
            self.phase = "action"
        self.pending_robber_reason = None
        self._check_win()

    def build(self, player_id: str, kind: str, location_id: str) -> None:
        player = self._require_active(player_id)
        self._require_phase("action", "road_building")
        if kind not in ("road", "settlement", "city"):
            raise GameError("Unknown building type.")

        free_road = self.phase == "road_building" and kind == "road" and self.pending_free_roads > 0
        if self.phase == "road_building" and kind != "road":
            raise GameError("Finish placing the Road Building roads first.")

        if kind == "road":
            if len(player.roads) >= 15:
                raise GameError("You have no road pieces remaining.")
            if location_id not in self.legal_roads(player_id):
                raise GameError("That road is not connected to your network.")
            if not free_road:
                self._pay(player, BUILD_COSTS["road"])
            player.roads.add(location_id)
            if free_road:
                self.pending_free_roads -= 1
                if self.pending_free_roads == 0 or len(player.roads) >= 15:
                    self.phase = self.pending_development_return_phase or "action"
                    self.pending_development_return_phase = None
            self.log.append(f"{player.username} built a road.")
        elif kind == "settlement":
            if len(player.settlements) >= 5:
                raise GameError("You have no settlement pieces remaining.")
            if location_id not in self.legal_settlements(player_id):
                raise GameError("That settlement is not connected or violates the distance rule.")
            self._pay(player, BUILD_COSTS["settlement"])
            player.settlements.add(location_id)
            self.log.append(f"{player.username} founded a settlement.")
        else:
            if len(player.cities) >= 4:
                raise GameError("You have no city pieces remaining.")
            if location_id not in player.settlements:
                raise GameError("A city must replace one of your settlements.")
            self._pay(player, BUILD_COSTS["city"])
            player.settlements.remove(location_id)
            player.cities.add(location_id)
            self.log.append(f"{player.username} upgraded a city.")
        self._update_longest_road()
        self._check_win()

    def buy_development_card(self, player_id: str) -> str:
        player = self._require_active(player_id)
        self._require_phase("action")
        if not self.development_deck:
            raise GameError("The development deck is empty.")
        self._pay(player, BUILD_COSTS["development"])
        card_type = self.development_deck.pop()
        player.development_cards.append({"type": card_type, "bought_turn": self.turn_number})
        self.log.append(f"{player.username} bought a development card.")
        self._check_win()
        return card_type

    def playable_development_cards(self, player_id: str) -> list[str]:
        player = self._player(player_id)
        if self.played_development_this_turn or player_id != self.active_player_id:
            return []
        if self.phase not in ("roll", "action"):
            return []
        return sorted(
            {
                card["type"]
                for card in player.development_cards
                if card["type"] != "victory_point" and card["bought_turn"] < self.turn_number
            }
        )

    def play_development_card(
        self, player_id: str, card_type: str, choice: Any | None = None
    ) -> None:
        player = self._require_active(player_id)
        if card_type not in self.playable_development_cards(player_id):
            raise GameError("That development card cannot be played now.")
        choices: list[str] = []
        if card_type == "year_of_plenty":
            choices = list(choice or [])
            if len(choices) != 2 or any(resource not in RESOURCES for resource in choices):
                raise GameError("Year of Plenty requires two resource choices.")
            needed = Counter(choices)
            if any(self.bank[resource] < amount for resource, amount in needed.items()):
                raise GameError("The bank does not have those resources.")
        elif card_type == "monopoly" and choice not in RESOURCES:
            raise GameError("Choose a resource for Monopoly.")

        return_phase = self.phase
        index = next(
            index
            for index, card in enumerate(player.development_cards)
            if card["type"] == card_type and card["bought_turn"] < self.turn_number
        )
        player.development_cards.pop(index)
        self.played_development_this_turn = True

        if card_type == "knight":
            player.played_knights += 1
            self.pending_robber_reason = "knight"
            self.pending_development_return_phase = return_phase
            self.phase = "move_robber"
            self._update_largest_army()
            self.log.append(f"{player.username} played a Knight.")
        elif card_type == "road_building":
            self.pending_free_roads = min(2, 15 - len(player.roads))
            if self.pending_free_roads:
                self.pending_development_return_phase = return_phase
                self.phase = "road_building"
            self.log.append(f"{player.username} played Road Building.")
        elif card_type == "year_of_plenty":
            for resource in choices:
                self.bank[resource] -= 1
                player.resources[resource] += 1
            self.log.append(f"{player.username} played Year of Plenty.")
        elif card_type == "monopoly":
            total = 0
            for other in self.players:
                if other.id == player_id:
                    continue
                amount = other.resources[choice]
                other.resources[choice] = 0
                player.resources[choice] += amount
                total += amount
            self.log.append(f"{player.username} monopolized {choice} and collected {total} cards.")
        self._check_win()

    def finish_road_building(self, player_id: str) -> None:
        self._require_active(player_id)
        self._require_phase("road_building")
        self.pending_free_roads = 0
        self.phase = self.pending_development_return_phase or "action"
        self.pending_development_return_phase = None

    def harbor_rates(self, player_id: str) -> dict[str, int]:
        player = self._player(player_id)
        rates = {resource: 4 for resource in RESOURCES}
        if not self.board:
            return rates
        occupied = player.settlements | player.cities
        for harbor in self.board["harbors"]:
            if not occupied.intersection(harbor["vertices"]):
                continue
            if harbor["type"] == "generic":
                rates = {resource: min(rate, 3) for resource, rate in rates.items()}
            else:
                rates[harbor["type"]] = 2
        return rates

    def maritime_trade(self, player_id: str, give: str, receive: str) -> None:
        player = self._require_active(player_id)
        self._require_phase("action")
        if give not in RESOURCES or receive not in RESOURCES or give == receive:
            raise GameError("Choose two different resource types.")
        rate = self.harbor_rates(player_id)[give]
        if player.resources[give] < rate:
            raise GameError(f"You need {rate} {give} for that trade.")
        if self.bank[receive] < 1:
            raise GameError(f"The bank is out of {receive}.")
        player.resources[give] -= rate
        self.bank[give] += rate
        self.bank[receive] -= 1
        player.resources[receive] += 1
        self.log.append(f"{player.username} traded {rate} {give} for 1 {receive}.")

    @staticmethod
    def _clean_bundle(bundle: dict[str, Any]) -> Counter[str]:
        cleaned = Counter()
        for resource in RESOURCES:
            amount = int(bundle.get(resource, 0))
            if amount < 0:
                raise GameError("Trade amounts cannot be negative.")
            if amount:
                cleaned[resource] = amount
        return cleaned

    def _eligible_trade_recipients(
        self, player_id: str, target_id: str | None
    ) -> tuple[list[str], bool]:
        normalized_target = target_id.strip() if target_id else ""
        if normalized_target.lower() in {"all", "broadcast", "table"}:
            normalized_target = ""

        if normalized_target:
            if player_id == normalized_target:
                raise GameError("Choose another player.")
            self._player(normalized_target)
            if self.active_player_id not in (player_id, normalized_target):
                raise GameError("Trades must include the active player.")
            return [normalized_target], False

        if player_id == self.active_player_id:
            recipients = [player.id for player in self.players if player.id != player_id]
        elif self.active_player_id:
            recipients = [self.active_player_id]
        else:
            recipients = []

        if not recipients:
            raise GameError("No players can receive this trade.")
        return recipients, len(recipients) > 1

    def offer_trade(
        self,
        player_id: str,
        target_id: str | None,
        give: dict[str, Any],
        receive: dict[str, Any],
    ) -> str:
        self._require_phase("action")
        with self._trade_lock:
            proposer = self._player(player_id)
            recipients, broadcast = self._eligible_trade_recipients(player_id, target_id)
            offered = self._clean_bundle(give)
            requested = self._clean_bundle(receive)
            if not offered or not requested:
                raise GameError("A trade must exchange resources in both directions.")
            if set(offered).intersection(requested):
                raise GameError("The same resource cannot be on both sides of a trade.")
            if any(
                proposer.resources[resource] < amount
                for resource, amount in offered.items()
            ):
                raise GameError("You do not hold the resources offered.")

            offer_id = secrets.token_hex(4)
            self.trade_offers[offer_id] = {
                "id": offer_id,
                "from": player_id,
                "to": None if broadcast else recipients[0],
                "eligible_to": recipients,
                "declined_by": [],
                "give": dict(offered),
                "receive": dict(requested),
            }
            if broadcast:
                self.log.append(f"{proposer.username} offered a trade to the table.")
            else:
                target = self._player(recipients[0])
                self.log.append(f"{proposer.username} offered a trade to {target.username}.")
            return offer_id

    def cancel_trade(self, player_id: str, offer_id: str) -> None:
        self._require_phase("action")
        with self._trade_lock:
            offer = self.trade_offers.get(offer_id)
            if not offer:
                raise GameError("That trade offer is no longer available.")
            if player_id != offer["from"]:
                raise GameError("Only the proposer can cancel this offer.")
            proposer = self._player(player_id)
            del self.trade_offers[offer_id]
            self.log.append(f"{proposer.username} cancelled a trade offer.")

    def respond_trade(self, player_id: str, offer_id: str, accept: bool) -> None:
        self._require_phase("action")
        with self._trade_lock:
            offer = self.trade_offers.get(offer_id)
            if not offer:
                raise GameError("That trade offer is no longer available.")
            eligible_to = list(
                offer.get("eligible_to")
                or ([offer["to"]] if offer.get("to") else [])
            )
            if player_id not in eligible_to:
                raise GameError("Only an eligible recipient can answer this offer.")

            proposer = self._player(offer["from"])
            recipient = self._player(player_id)
            declined_by = set(offer.get("declined_by", []))
            if player_id in declined_by:
                raise GameError("You already passed on this offer.")

            if accept:
                if any(
                    proposer.resources[resource] < amount
                    for resource, amount in offer["give"].items()
                ):
                    del self.trade_offers[offer_id]
                    self.log.append(f"{proposer.username}'s trade offer expired.")
                    raise GameError("The proposer no longer has the offered resources.")
                if any(
                    recipient.resources[resource] < amount
                    for resource, amount in offer["receive"].items()
                ):
                    raise GameError("You do not hold the requested resources.")
                for resource, amount in offer["give"].items():
                    proposer.resources[resource] -= amount
                    recipient.resources[resource] += amount
                for resource, amount in offer["receive"].items():
                    recipient.resources[resource] -= amount
                    proposer.resources[resource] += amount
                del self.trade_offers[offer_id]
                self.log.append(f"{recipient.username} accepted {proposer.username}'s trade.")
                return

            self.log.append(f"{recipient.username} declined {proposer.username}'s trade.")
            if offer.get("to"):
                del self.trade_offers[offer_id]
                return

            declined_by.add(player_id)
            offer["declined_by"] = [
                recipient_id for recipient_id in eligible_to if recipient_id in declined_by
            ]
            if declined_by.issuperset(eligible_to):
                del self.trade_offers[offer_id]
                self.log.append(f"No one accepted {proposer.username}'s trade.")

    def end_turn(self, player_id: str) -> None:
        self._require_active(player_id)
        self._require_phase("action")
        self._check_win()
        if self.status == "finished":
            return
        current_index = self.turn_order.index(player_id)
        self.active_player_id = self.turn_order[(current_index + 1) % len(self.turn_order)]
        self.turn_number += 1
        self.phase = "roll"
        self.last_roll = None
        self.played_development_this_turn = False
        with self._trade_lock:
            self.trade_offers.clear()
        self.log.append(f"It is now {self._player(self.active_player_id).username}'s turn.")
        self._check_win()

    def _road_length(self, player_id: str) -> int:
        player = self._player(player_id)
        if not player.roads:
            return 0

        def walk(vertex_id: str, used: frozenset[str], started: bool) -> int:
            building = self._building_at(vertex_id)
            if started and building and building[0] != player_id:
                return 0
            best = 0
            for edge_id in TOPOLOGY["vertex_edges"][vertex_id]:
                if edge_id not in player.roads or edge_id in used:
                    continue
                start, end = TOPOLOGY["edge_vertices"][edge_id]
                next_vertex = end if start == vertex_id else start
                best = max(best, 1 + walk(next_vertex, used | {edge_id}, True))
            return best

        return max(walk(vertex_id, frozenset(), False) for vertex_id in TOPOLOGY["vertex_positions"])

    def _update_longest_road(self) -> None:
        lengths = {player.id: self._road_length(player.id) for player in self.players}
        eligible = {player_id: length for player_id, length in lengths.items() if length >= 5}
        if self.longest_road_holder in eligible:
            holder_length = eligible[self.longest_road_holder]
            challengers = [
                player_id
                for player_id, length in eligible.items()
                if player_id != self.longest_road_holder and length > holder_length
            ]
            if challengers:
                best = max(eligible[player_id] for player_id in challengers)
                winners = [player_id for player_id in challengers if eligible[player_id] == best]
                if len(winners) == 1:
                    self.longest_road_holder = winners[0]
            return
        if not eligible:
            self.longest_road_holder = None
            return
        best = max(eligible.values())
        winners = [player_id for player_id, length in eligible.items() if length == best]
        self.longest_road_holder = winners[0] if len(winners) == 1 else None

    def _update_largest_army(self) -> None:
        armies = {player.id: player.played_knights for player in self.players}
        eligible = {player_id: count for player_id, count in armies.items() if count >= 3}
        if self.largest_army_holder in eligible:
            holder_count = eligible[self.largest_army_holder]
            challengers = [
                player_id
                for player_id, count in eligible.items()
                if player_id != self.largest_army_holder and count > holder_count
            ]
            if challengers:
                best = max(eligible[player_id] for player_id in challengers)
                winners = [player_id for player_id in challengers if eligible[player_id] == best]
                if len(winners) == 1:
                    self.largest_army_holder = winners[0]
            return
        if eligible:
            best = max(eligible.values())
            winners = [player_id for player_id, count in eligible.items() if count == best]
            self.largest_army_holder = winners[0] if len(winners) == 1 else None

    def score(self, player_id: str, include_hidden: bool = True) -> int:
        player = self._player(player_id)
        score = len(player.settlements) + 2 * len(player.cities)
        score += 2 if self.longest_road_holder == player_id else 0
        score += 2 if self.largest_army_holder == player_id else 0
        if include_hidden:
            score += player.hidden_victory_points()
        return score

    def _check_win(self) -> None:
        if (
            self.active_player_id
            and self.status == "playing"
            and self.score(self.active_player_id, include_hidden=True) >= 10
        ):
            self.winner_id = self.active_player_id
            self.status = "finished"
            self.phase = "finished"
            self.log.append(f"{self._player(self.winner_id).username} won Catan!")

    def _legal_actions(self, viewer_id: str) -> dict[str, Any]:
        player = self._player(viewer_id)
        is_active = viewer_id == self.active_player_id
        actions: dict[str, Any] = {
            "can_start": self.status == "lobby"
            and viewer_id == self.host_id
            and len(self.players) >= 3,
            "can_roll": is_active and self.phase == "roll",
            "can_end_turn": is_active and self.phase == "action",
            "can_buy_development": is_active
            and self.phase == "action"
            and bool(self.development_deck)
            and self._can_afford(player, "development"),
            "playable_development": self.playable_development_cards(viewer_id),
            "must_discard": self.discard_required.get(viewer_id, 0),
            "can_move_robber": is_active and self.phase == "move_robber",
            "robber_hexes": self.legal_robber_hexes()
            if is_active and self.phase == "move_robber"
            else [],
            "victims": self.legal_victims(viewer_id) if is_active else [],
            "legal_roads": [],
            "legal_settlements": [],
            "legal_cities": [],
            "buildable": {},
            "harbor_rates": self.harbor_rates(viewer_id),
            "can_offer_trade": self.phase == "action",
        }
        if is_active and self.phase == "setup_settlement":
            actions["legal_settlements"] = self.legal_settlements(viewer_id, setup=True)
        elif is_active and self.phase == "setup_road":
            actions["legal_roads"] = self.legal_roads(viewer_id, self.setup_pending_vertex)
        elif is_active and self.phase in ("action", "road_building"):
            free = self.phase == "road_building"
            if free or self._can_afford(player, "road"):
                actions["legal_roads"] = self.legal_roads(viewer_id)
            if self.phase == "action" and self._can_afford(player, "settlement"):
                actions["legal_settlements"] = self.legal_settlements(viewer_id)
            if self.phase == "action" and self._can_afford(player, "city"):
                actions["legal_cities"] = sorted(player.settlements)
            actions["buildable"] = {
                "road": free or self._can_afford(player, "road"),
                "settlement": self._can_afford(player, "settlement"),
                "city": self._can_afford(player, "city"),
            }
        return actions

    def serialize(self, viewer_id: str) -> dict[str, Any]:
        viewer = self._player(viewer_id)
        reveal_all = self.status == "finished"
        players = []
        for player in self.players:
            is_viewer = player.id == viewer_id
            public_score = self.score(player.id, include_hidden=reveal_all or is_viewer)
            players.append(
                {
                    "id": player.id,
                    "username": player.username,
                    "color": player.color,
                    "connected": player.connected,
                    "resource_count": player.resource_total(),
                    "development_count": len(player.development_cards),
                    "played_knights": player.played_knights,
                    "roads_remaining": 15 - len(player.roads),
                    "settlements_remaining": 5 - len(player.settlements),
                    "cities_remaining": 4 - len(player.cities),
                    "score": public_score,
                    "longest_road_length": self._road_length(player.id) if self.board else 0,
                    "is_host": player.id == self.host_id,
                    "is_active": player.id == self.active_player_id,
                }
            )

        buildings = {}
        roads = {}
        for player in self.players:
            for vertex_id in player.settlements:
                buildings[vertex_id] = {"player_id": player.id, "type": "settlement"}
            for vertex_id in player.cities:
                buildings[vertex_id] = {"player_id": player.id, "type": "city"}
            for edge_id in player.roads:
                roads[edge_id] = {"player_id": player.id}

        return {
            "code": self.code,
            "status": self.status,
            "phase": self.phase,
            "host_id": self.host_id,
            "active_player_id": self.active_player_id,
            "turn_number": self.turn_number,
            "players": players,
            "board": self.board,
            "buildings": buildings,
            "roads": roads,
            "bank": dict(self.bank),
            "development_deck_count": len(self.development_deck),
            "last_roll": list(self.last_roll) if self.last_roll else None,
            "longest_road_holder": self.longest_road_holder,
            "largest_army_holder": self.largest_army_holder,
            "winner_id": self.winner_id,
            "log": self.log[-40:],
            "trade_offers": list(self.trade_offers.values()),
            "you": {
                "id": viewer.id,
                "username": viewer.username,
                "resources": dict(viewer.resources),
                "development_cards": [card["type"] for card in viewer.development_cards],
                "score": self.score(viewer.id, include_hidden=True),
            },
            "legal": self._legal_actions(viewer_id),
        }
