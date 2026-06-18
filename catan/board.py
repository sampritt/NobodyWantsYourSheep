from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any

RESOURCE_BY_TERRAIN = {
    "forest": "lumber",
    "hills": "brick",
    "pasture": "wool",
    "fields": "grain",
    "mountains": "ore",
    "desert": None,
}

TERRAIN_POOL = (
    ["forest"] * 4
    + ["pasture"] * 4
    + ["fields"] * 4
    + ["hills"] * 3
    + ["mountains"] * 3
    + ["desert"]
)

NUMBER_POOL = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]
HARBOR_POOL = ["generic"] * 4 + ["brick", "lumber", "wool", "grain", "ore"]


def _axial_coordinates(radius: int = 2) -> list[tuple[int, int]]:
    coordinates = []
    for q in range(-radius, radius + 1):
        lower = max(-radius, -q - radius)
        upper = min(radius, -q + radius)
        for r in range(lower, upper + 1):
            coordinates.append((q, r))
    return sorted(coordinates, key=lambda value: (value[1], value[0]))


def _center(q: int, r: int, size: float = 64.0) -> tuple[float, float]:
    return 1.5 * size * q, math.sqrt(3) * size * (r + q / 2)


def create_topology() -> dict[str, Any]:
    vertex_lookup: dict[tuple[float, float], str] = {}
    vertex_positions: dict[str, tuple[float, float]] = {}
    hex_vertices: dict[str, list[str]] = {}
    hex_centers: dict[str, tuple[float, float]] = {}

    for index, (q, r) in enumerate(_axial_coordinates()):
        hex_id = f"h{index}"
        cx, cy = _center(q, r)
        hex_centers[hex_id] = (cx, cy)
        vertices = []
        for corner in range(6):
            angle = math.radians(60 * corner)
            point = (round(cx + 64 * math.cos(angle), 3), round(cy + 64 * math.sin(angle), 3))
            if point not in vertex_lookup:
                vertex_id = f"v{len(vertex_lookup)}"
                vertex_lookup[point] = vertex_id
                vertex_positions[vertex_id] = point
            vertices.append(vertex_lookup[point])
        hex_vertices[hex_id] = vertices

    edge_lookup: dict[tuple[str, str], str] = {}
    edge_vertices: dict[str, tuple[str, str]] = {}
    edge_hexes: dict[str, list[str]] = defaultdict(list)
    vertex_edges: dict[str, list[str]] = defaultdict(list)
    vertex_hexes: dict[str, list[str]] = defaultdict(list)

    for hex_id, vertices in hex_vertices.items():
        for vertex_id in vertices:
            vertex_hexes[vertex_id].append(hex_id)
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % 6]
            key = tuple(sorted((start, end)))
            if key not in edge_lookup:
                edge_id = f"e{len(edge_lookup)}"
                edge_lookup[key] = edge_id
                edge_vertices[edge_id] = key
                vertex_edges[start].append(edge_id)
                vertex_edges[end].append(edge_id)
            edge_hexes[edge_lookup[key]].append(hex_id)

    vertex_neighbors: dict[str, list[str]] = defaultdict(list)
    for start, end in edge_vertices.values():
        vertex_neighbors[start].append(end)
        vertex_neighbors[end].append(start)

    boundary_edges = [edge_id for edge_id, hexes in edge_hexes.items() if len(hexes) == 1]
    boundary_edges.sort(
        key=lambda edge_id: math.atan2(
            sum(vertex_positions[v][1] for v in edge_vertices[edge_id]) / 2,
            sum(vertex_positions[v][0] for v in edge_vertices[edge_id]) / 2,
        )
    )
    harbor_edge_indexes = [0, 3, 7, 10, 13, 17, 20, 23, 27]

    return {
        "hex_centers": hex_centers,
        "hex_vertices": hex_vertices,
        "vertex_positions": vertex_positions,
        "edge_vertices": edge_vertices,
        "edge_hexes": dict(edge_hexes),
        "vertex_edges": dict(vertex_edges),
        "vertex_hexes": dict(vertex_hexes),
        "vertex_neighbors": dict(vertex_neighbors),
        "boundary_edges": boundary_edges,
        "harbor_edge_indexes": harbor_edge_indexes,
    }


TOPOLOGY = create_topology()


def _numbers_are_balanced(hexes: list[dict[str, Any]]) -> bool:
    red_hexes = {item["id"] for item in hexes if item["number"] in (6, 8)}
    for edge_hexes in TOPOLOGY["edge_hexes"].values():
        if len(edge_hexes) == 2 and red_hexes.issuperset(edge_hexes):
            return False
    return True


def generate_board(rng: random.Random) -> dict[str, Any]:
    terrains = list(TERRAIN_POOL)
    rng.shuffle(terrains)

    hexes: list[dict[str, Any]] = []
    number_pool = list(NUMBER_POOL)
    for _ in range(500):
        rng.shuffle(number_pool)
        number_iterator = iter(number_pool)
        hexes = []
        for index, terrain in enumerate(terrains):
            hex_id = f"h{index}"
            q, r = _axial_coordinates()[index]
            cx, cy = TOPOLOGY["hex_centers"][hex_id]
            hexes.append(
                {
                    "id": hex_id,
                    "q": q,
                    "r": r,
                    "x": cx,
                    "y": cy,
                    "terrain": terrain,
                    "resource": RESOURCE_BY_TERRAIN[terrain],
                    "number": None if terrain == "desert" else next(number_iterator),
                    "vertices": TOPOLOGY["hex_vertices"][hex_id],
                }
            )
        if _numbers_are_balanced(hexes):
            break

    harbor_types = list(HARBOR_POOL)
    rng.shuffle(harbor_types)
    harbors = []
    for harbor_id, (boundary_index, harbor_type) in enumerate(
        zip(TOPOLOGY["harbor_edge_indexes"], harbor_types)
    ):
        edge_id = TOPOLOGY["boundary_edges"][boundary_index]
        vertices = TOPOLOGY["edge_vertices"][edge_id]
        x = sum(TOPOLOGY["vertex_positions"][vertex][0] for vertex in vertices) / 2
        y = sum(TOPOLOGY["vertex_positions"][vertex][1] for vertex in vertices) / 2
        distance = math.hypot(x, y) or 1
        harbors.append(
            {
                "id": f"p{harbor_id}",
                "type": harbor_type,
                "edge": edge_id,
                "vertices": list(vertices),
                "x": x + (x / distance) * 52,
                "y": y + (y / distance) * 52,
            }
        )

    desert = next(item for item in hexes if item["terrain"] == "desert")
    return {
        "hexes": hexes,
        "vertices": {
            vertex_id: {"id": vertex_id, "x": position[0], "y": position[1]}
            for vertex_id, position in TOPOLOGY["vertex_positions"].items()
        },
        "edges": {
            edge_id: {"id": edge_id, "vertices": list(vertices)}
            for edge_id, vertices in TOPOLOGY["edge_vertices"].items()
        },
        "harbors": harbors,
        "robber_hex": desert["id"],
    }

