from collections import Counter

from catan.board import TOPOLOGY, generate_board


def test_standard_board_topology_and_component_counts():
    board = generate_board(__import__("random").Random(7))

    assert len(board["hexes"]) == 19
    assert len(board["vertices"]) == 54
    assert len(board["edges"]) == 72
    assert len(TOPOLOGY["boundary_edges"]) == 30
    assert len(board["harbors"]) == 9

    terrain_counts = Counter(item["terrain"] for item in board["hexes"])
    assert terrain_counts == {
        "forest": 4,
        "pasture": 4,
        "fields": 4,
        "hills": 3,
        "mountains": 3,
        "desert": 1,
    }
    assert sorted(item["number"] for item in board["hexes"] if item["number"]) == [
        2,
        3,
        3,
        4,
        4,
        5,
        5,
        6,
        6,
        8,
        8,
        9,
        9,
        10,
        10,
        11,
        11,
        12,
    ]


def test_red_numbers_are_never_adjacent():
    for seed in range(30):
        board = generate_board(__import__("random").Random(seed))
        numbers = {item["id"]: item["number"] for item in board["hexes"]}
        for adjacent_hexes in TOPOLOGY["edge_hexes"].values():
            if len(adjacent_hexes) == 2:
                assert not all(numbers[hex_id] in (6, 8) for hex_id in adjacent_hexes)


def test_harbors_use_distinct_coastal_intersections():
    board = generate_board(__import__("random").Random(11))
    harbor_vertices = [vertex for harbor in board["harbors"] for vertex in harbor["vertices"]]

    assert len(set(harbor_vertices)) == 18
    assert Counter(harbor["type"] for harbor in board["harbors"]) == {
        "generic": 4,
        "brick": 1,
        "lumber": 1,
        "wool": 1,
        "grain": 1,
        "ore": 1,
    }

