from collections import Counter

import pytest

from catan.board import TOPOLOGY
from catan.game import CatanGame, GameError, RESOURCES


def started_game(seed=2):
    game = CatanGame("TABLE", "p1", "Ada", seed=seed)
    game.add_player("p2", "Ben")
    game.add_player("p3", "Cy")
    game.start("p1")
    return game


def finish_setup(game):
    placements = []
    while game.phase.startswith("setup_"):
        player_id = game.active_player_id
        if game.phase == "setup_settlement":
            vertex = game.legal_settlements(player_id, setup=True)[0]
            game.place_setup_settlement(player_id, vertex)
            placements.append((player_id, vertex))
        else:
            edge = game.legal_roads(player_id, game.setup_pending_vertex)[0]
            game.place_setup_road(player_id, edge)
    return placements


def set_action_turn(game, player_id="p1"):
    game.active_player_id = player_id
    game.phase = "action"
    game.turn_number = max(game.turn_number, 10)


def simple_edge_path(length):
    def walk(vertex, used, vertices):
        if len(used) == length:
            return list(used), vertices
        for edge in TOPOLOGY["vertex_edges"][vertex]:
            if edge in used:
                continue
            start, end = TOPOLOGY["edge_vertices"][edge]
            neighbor = end if start == vertex else start
            if neighbor in vertices:
                continue
            found = walk(neighbor, used + [edge], vertices + [neighbor])
            if found:
                return found
        return None

    for vertex in TOPOLOGY["vertex_positions"]:
        found = walk(vertex, [], [vertex])
        if found:
            return found
    raise AssertionError("No path found")


def test_setup_uses_snake_order_and_second_settlement_produces_resources():
    game = started_game()
    order = list(game.turn_order)
    placements = finish_setup(game)

    assert [player_id for player_id, _ in placements] == order + list(reversed(order))
    assert game.active_player_id == order[0]
    assert game.phase == "roll"
    assert all(len(player.settlements) == 2 and len(player.roads) == 2 for player in game.players)
    assert sum(player.resource_total() for player in game.players) > 0


def test_distance_rule_blocks_adjacent_intersections():
    game = started_game()
    player_id = game.active_player_id
    vertex = game.legal_settlements(player_id, setup=True)[0]
    game.place_setup_settlement(player_id, vertex)

    blocked = TOPOLOGY["vertex_neighbors"][vertex][0]
    assert blocked not in game.legal_settlements(game.setup_sequence[1], setup=True)


def test_seven_requires_half_discard_then_moves_robber():
    game = started_game()
    finish_setup(game)
    active = game.active_player_id
    player = game._player(active)
    player.resources = Counter({"brick": 5, "lumber": 4})
    game.bank["brick"] -= 5
    game.bank["lumber"] -= 4

    game.roll_dice(active, (3, 4))
    assert game.phase == "discard"
    assert game.discard_required[active] == 4

    with pytest.raises(GameError):
        game.discard(active, {"brick": 1})

    game.discard(active, {"brick": 2, "lumber": 2})
    assert game.phase == "move_robber"
    destination = game.legal_robber_hexes()[0]
    game.move_robber(active, destination)
    if game.phase == "steal":
        game.steal(active, game.legal_victims(active)[0])
    assert game.phase == "action"


def test_resource_shortage_pays_nobody_when_multiple_players_claim():
    game = started_game()
    finish_setup(game)
    producing_hex = next(
        item
        for item in game.board["hexes"]
        if item["resource"] and len(
            {
                game._building_at(vertex)[0]
                for vertex in item["vertices"]
                if game._building_at(vertex)
            }
        )
        >= 2
    )
    resource = producing_hex["resource"]
    claimants = {
        game._building_at(vertex)[0]
        for vertex in producing_hex["vertices"]
        if game._building_at(vertex)
    }
    before = {player_id: game._player(player_id).resources[resource] for player_id in claimants}
    game.bank[resource] = 0

    game._produce(producing_hex["number"])

    assert {player_id: game._player(player_id).resources[resource] for player_id in claimants} == before


def test_maritime_trade_uses_best_owned_harbor_rate():
    game = started_game()
    finish_setup(game)
    set_action_turn(game)
    player = game._player("p1")
    generic = next(harbor for harbor in game.board["harbors"] if harbor["type"] == "generic")
    occupied_vertex = generic["vertices"][0]
    for other in game.players:
        other.settlements.discard(occupied_vertex)
        other.cities.discard(occupied_vertex)
    player.settlements.add(occupied_vertex)
    player.resources["brick"] = 3
    game.bank["brick"] -= 3
    before_ore = player.resources["ore"]

    assert game.harbor_rates("p1")["brick"] == 3
    game.maritime_trade("p1", "brick", "ore")

    assert player.resources["brick"] == 0
    assert player.resources["ore"] == before_ore + 1


def test_domestic_trade_requires_active_player_and_exchanges_atomically():
    game = started_game()
    finish_setup(game)
    set_action_turn(game, "p1")
    game._player("p1").resources = Counter({"brick": 1})
    game._player("p2").resources = Counter({"ore": 1})

    offer_id = game.offer_trade("p2", "p1", {"ore": 1}, {"brick": 1})
    game.respond_trade("p1", offer_id, True)

    assert game._player("p1").resources["ore"] == 1
    assert game._player("p2").resources["brick"] == 1
    with pytest.raises(GameError):
        game.offer_trade("p2", "p3", {"brick": 1}, {"ore": 1})


def test_broadcast_trade_first_accept_exchanges_and_closes_offer():
    game = started_game()
    finish_setup(game)
    set_action_turn(game, "p1")
    game._player("p1").resources = Counter({"brick": 1})
    game._player("p2").resources = Counter({"ore": 1})
    game._player("p3").resources = Counter({"ore": 1})

    offer_id = game.offer_trade("p1", None, {"brick": 1}, {"ore": 1})

    assert game.trade_offers[offer_id]["to"] is None
    assert game.trade_offers[offer_id]["eligible_to"] == ["p2", "p3"]
    game.respond_trade("p2", offer_id, True)

    assert offer_id not in game.trade_offers
    assert game._player("p1").resources["brick"] == 0
    assert game._player("p1").resources["ore"] == 1
    assert game._player("p2").resources["ore"] == 0
    assert game._player("p2").resources["brick"] == 1
    assert game._player("p3").resources == Counter({"ore": 1})
    with pytest.raises(GameError, match="no longer available"):
        game.respond_trade("p3", offer_id, True)


def test_broadcast_trade_passes_do_not_cancel_until_everyone_passes():
    game = started_game()
    finish_setup(game)
    set_action_turn(game, "p1")
    game._player("p1").resources = Counter({"brick": 1})
    game._player("p2").resources = Counter({"ore": 1})
    game._player("p3").resources = Counter({"ore": 1})

    offer_id = game.offer_trade("p1", None, {"brick": 1}, {"ore": 1})
    game.respond_trade("p2", offer_id, False)

    assert offer_id in game.trade_offers
    assert game.trade_offers[offer_id]["declined_by"] == ["p2"]
    with pytest.raises(GameError, match="already passed"):
        game.respond_trade("p2", offer_id, True)

    game.respond_trade("p3", offer_id, False)

    assert offer_id not in game.trade_offers


def test_broadcast_trade_stale_resources_are_handled_at_acceptance():
    game = started_game()
    finish_setup(game)
    set_action_turn(game, "p1")
    game._player("p1").resources = Counter({"brick": 1})
    game._player("p2").resources = Counter()
    game._player("p3").resources = Counter({"ore": 1})

    offer_id = game.offer_trade("p1", None, {"brick": 1}, {"ore": 1})

    with pytest.raises(GameError, match="requested resources"):
        game.respond_trade("p2", offer_id, True)
    assert offer_id in game.trade_offers

    game._player("p1").resources.clear()
    with pytest.raises(GameError, match="proposer no longer has"):
        game.respond_trade("p3", offer_id, True)

    assert offer_id not in game.trade_offers
    assert game._player("p3").resources == Counter({"ore": 1})


def test_trade_offer_can_be_cancelled_by_proposer_only():
    game = started_game()
    finish_setup(game)
    set_action_turn(game, "p1")
    game._player("p1").resources = Counter({"brick": 1})

    offer_id = game.offer_trade("p1", None, {"brick": 1}, {"ore": 1})

    with pytest.raises(GameError, match="Only the proposer"):
        game.cancel_trade("p2", offer_id)
    assert offer_id in game.trade_offers

    game.cancel_trade("p1", offer_id)

    assert offer_id not in game.trade_offers


def test_development_card_cannot_be_played_when_bought_and_knight_returns_to_roll():
    game = started_game()
    finish_setup(game)
    active = game.active_player_id
    player = game._player(active)
    player.development_cards.append({"type": "knight", "bought_turn": game.turn_number})

    assert "knight" not in game.playable_development_cards(active)
    player.development_cards[0]["bought_turn"] = game.turn_number - 1
    game.play_development_card(active, "knight")
    assert game.phase == "move_robber"

    game.move_robber(active, game.legal_robber_hexes()[0])
    if game.phase == "steal":
        game.steal(active, game.legal_victims(active)[0])
    assert game.phase == "roll"


def test_invalid_year_of_plenty_does_not_consume_card():
    game = started_game()
    finish_setup(game)
    active = game.active_player_id
    player = game._player(active)
    player.development_cards.append({"type": "year_of_plenty", "bought_turn": 0})
    count_before = len(player.development_cards)

    with pytest.raises(GameError):
        game.play_development_card(active, "year_of_plenty", ["brick"])

    assert len(player.development_cards) == count_before
    assert not game.played_development_this_turn


def test_longest_road_is_interrupted_by_opponent_settlement():
    game = started_game()
    path, vertices = simple_edge_path(5)
    game._player("p1").roads = set(path)
    game._update_longest_road()

    assert game._road_length("p1") == 5
    assert game.longest_road_holder == "p1"

    game._player("p2").settlements.add(vertices[2])
    game._update_longest_road()
    assert game._road_length("p1") < 5
    assert game.longest_road_holder is None


def test_hidden_victory_points_only_win_on_players_turn():
    game = started_game()
    player = game._player("p1")
    player.settlements = set(list(TOPOLOGY["vertex_positions"])[:5])
    player.cities = set(list(TOPOLOGY["vertex_positions"])[5:7])
    player.development_cards.append({"type": "victory_point", "bought_turn": 0})
    game.active_player_id = "p2"
    game.phase = "action"

    assert game.score("p1") == 10
    game._check_win()
    assert game.status == "playing"

    game.active_player_id = "p1"
    game._check_win()
    assert game.status == "finished"
    assert game.winner_id == "p1"


def test_ten_points_reached_off_turn_wins_when_turn_begins():
    game = started_game()
    game.turn_order = ["p2", "p1", "p3"]
    game.active_player_id = "p2"
    game.phase = "action"
    player = game._player("p1")
    player.settlements = set(list(TOPOLOGY["vertex_positions"])[:5])
    player.cities = set(list(TOPOLOGY["vertex_positions"])[5:7])
    player.development_cards.append({"type": "victory_point", "bought_turn": 0})

    game.end_turn("p2")

    assert game.status == "finished"
    assert game.winner_id == "p1"


def test_component_piece_limits_and_costs_are_enforced():
    game = started_game()
    finish_setup(game)
    set_action_turn(game, "p1")
    player = game._player("p1")
    player.resources.update({resource: 10 for resource in RESOURCES})
    player.roads = set(list(TOPOLOGY["edge_vertices"])[:15])

    with pytest.raises(GameError):
        game.build("p1", "road", next(iter(game.legal_roads("p1")), "e0"))
