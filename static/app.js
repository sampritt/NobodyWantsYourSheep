const root = document.querySelector("#app");
const toastRegion = document.querySelector("#toast-region");
const socket = io();

const RESOURCES = ["brick", "lumber", "wool", "grain", "ore"];
const RESOURCE_LABELS = {
  brick: "Brick",
  lumber: "Lumber",
  wool: "Wool",
  grain: "Grain",
  ore: "Ore",
};
const CARD_LABELS = {
  knight: "Knight",
  road_building: "Road Building",
  year_of_plenty: "Year of Plenty",
  monopoly: "Monopoly",
  victory_point: "Victory Point",
};
const PHASE_LABELS = {
  setup_settlement: "Choose a starting settlement",
  setup_road: "Build its connecting road",
  roll: "Roll for production",
  discard: "Waiting for discards",
  move_robber: "Move the robber",
  steal: "Choose a player to rob",
  action: "Trade and build",
  road_building: "Place your free roads",
  finished: "Game complete",
};

const storedIdentity = localStorage.getItem("catan_client_id");
const clientId = storedIdentity || crypto.randomUUID();
localStorage.setItem("catan_client_id", clientId);

let state = null;
let ui = {
  username: localStorage.getItem("catan_username") || "",
  joinCode: "",
  buildMode: null,
  modal: null,
  discard: Object.fromEntries(RESOURCES.map((resource) => [resource, 0])),
  plenty: [],
  monopoly: "brick",
  tradeMode: "player",
  tradeTarget: "",
  tradeGive: Object.fromEntries(RESOURCES.map((resource) => [resource, 0])),
  tradeReceive: Object.fromEntries(RESOURCES.map((resource) => [resource, 0])),
  bankGive: "brick",
  bankReceive: "lumber",
};

socket.on("connect", () => socket.emit("identify", { client_id: clientId }));
socket.on("state", (nextState) => {
  state = nextState;
  if (!state.legal.legal_roads.includes(ui.buildMode) && state.phase !== "action") {
    ui.buildMode = null;
  }
  if (state.legal.must_discard && ui.modal !== "discard") {
    ui.modal = "discard";
    ui.discard = Object.fromEntries(RESOURCES.map((resource) => [resource, 0]));
  }
  if (state.phase === "steal" && state.active_player_id === clientId) {
    ui.modal = "steal";
  }
  if (state.status === "finished") {
    ui.modal = "winner";
  }
  render();
});
socket.on("left_game", () => {
  state = null;
  ui.modal = null;
  render();
});
socket.on("error_message", ({ message }) => showToast(message, true));
socket.on("action_result", (result) => {
  if (result?.type === "development_card") {
    showToast(`You drew ${CARD_LABELS[result.card]}.`);
  }
  if (result?.type === "stolen_resource") {
    showToast(`You stole ${RESOURCE_LABELS[result.resource]}.`);
  }
});

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message, error = false) {
  const toast = document.createElement("div");
  toast.className = `toast${error ? " error" : ""}`;
  toast.textContent = message;
  toastRegion.append(toast);
  setTimeout(() => toast.remove(), 3400);
}

function emitGame(event, payload = {}) {
  socket.emit(event, { ...payload, client_id: clientId, code: state?.code });
}

function initials(name) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function icon(name) {
  const paths = {
    play: '<path d="M8 5v14l11-7z"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    dice: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1"/><circle cx="16" cy="8" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="8" cy="16" r="1"/><circle cx="16" cy="16" r="1"/>',
    trade: '<path d="M7 7h11l-3-3m3 3-3 3M17 17H6l3 3m-3-3 3-3"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  };
  return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths[name] || ""}</svg>`;
}

function render() {
  if (!state) {
    renderLanding();
  } else if (state.status === "lobby") {
    renderLobby();
  } else {
    renderGame();
  }
}

function renderLanding() {
  root.innerHTML = `
    <main class="landing app-shell">
      <div class="landing-wrap">
        <section>
          <div class="eyebrow">A table for distant friends</div>
          <h1 class="hero-title">Settle the <span>island.</span></h1>
          <p class="hero-copy">
            Raise roads through the wild, barter at the harbor, and build a realm worth ten points.
            A complete real-time Catan table for three or four players.
          </p>
          <div class="feature-row">
            <div class="feature"><span class="feature-dot"></span>Live multiplayer</div>
            <div class="feature"><span class="feature-dot"></span>Official base rules</div>
            <div class="feature"><span class="feature-dot"></span>No account required</div>
          </div>
        </section>
        <section class="entry-card">
          <h2>Take a seat</h2>
          <p>Your gamer tag is all you need. Create a new island or join friends with their room code.</p>
          <form data-form="entry">
            <div class="field">
              <label for="username">Gamer tag</label>
              <input class="input" id="username" name="username" maxlength="24" autocomplete="nickname"
                placeholder="How should the table know you?" value="${escapeHtml(ui.username)}" required>
            </div>
            <button class="btn btn-primary btn-block" type="button" data-action="create-game">
              ${icon("play")} Create a new island
            </button>
            <div class="divider">or join a table</div>
            <div class="join-row">
              <input class="input" name="join-code" maxlength="6" aria-label="Room code"
                placeholder="ROOM CODE" value="${escapeHtml(ui.joinCode)}">
              <button class="btn btn-secondary" type="button" data-action="join-game">Join</button>
            </div>
          </form>
        </section>
      </div>
    </main>`;
}

function renderLobby() {
  const emptySeats = 4 - state.players.length;
  const seats = state.players
    .map(
      (player) => `
        <div class="seat">
          <div class="avatar" style="background:${player.color}">${escapeHtml(initials(player.username))}</div>
          <div>
            <div class="seat-name">${escapeHtml(player.username)}</div>
            <div class="player-status">${player.is_host ? "Expedition host" : "Ready to settle"}</div>
          </div>
          <div class="seat-meta">${player.connected ? "Connected" : "Reconnecting"}</div>
        </div>`,
    )
    .join("");
  const empties = Array.from(
    { length: emptySeats },
    () => '<div class="seat empty">Waiting for another settler</div>',
  ).join("");
  root.innerHTML = `
    <main class="lobby app-shell">
      <div class="lobby-ocean"></div>
      <div class="lobby-island"></div>
      <section class="lobby-card">
        <div class="lobby-top">
          <div>
            <div class="eyebrow">Expedition lobby</div>
            <h1>Gather the settlers</h1>
          </div>
          <button class="room-code" data-action="copy-code" title="Copy room code">
            <small>Room code</small>
            <strong>${state.code}</strong>
          </button>
        </div>
        <p>Share the code with friends. The host can launch with three players; a fourth player fills the final seat automatically.</p>
        <div class="seat-list">${seats}${empties}</div>
        <div class="lobby-actions">
          ${
            state.legal.can_start
              ? `<button class="btn btn-primary" data-action="start-game">${icon("users")} Reveal the island</button>`
              : `<button class="btn btn-primary" disabled>${
                  state.players.length < 3 ? `Waiting for ${3 - state.players.length} more` : "Waiting for the host"
                }</button>`
          }
          <button class="btn btn-secondary" data-action="leave-game">Leave</button>
        </div>
      </section>
    </main>`;
}

function renderGame() {
  const active = state.players.find((player) => player.id === state.active_player_id);
  root.innerHTML = `
    <main class="game-shell app-shell">
      <header class="game-header">
        <div class="wordmark">Settlers' <span>Table</span></div>
        <div class="turn-banner">
          <span class="turn-pip" style="background:${active?.color || "#aaa"}"></span>
          <div class="turn-copy">
            <strong>${escapeHtml(active?.username || "Game complete")}</strong>
            <span>${escapeHtml(PHASE_LABELS[state.phase] || state.phase)}${state.turn_number ? ` · Turn ${state.turn_number}` : ""}</span>
          </div>
        </div>
        <div class="header-tools">
          <button class="code-chip" data-action="copy-code">${state.code}</button>
        </div>
      </header>
      <section class="game-main">
        ${renderPlayerRail()}
        <div class="board-stage">${renderBoard()}</div>
        ${renderActionRail()}
      </section>
      ${renderHand()}
    </main>
    ${renderModal()}
  `;
}

function renderPlayerRail() {
  return `
    <aside class="player-rail">
      <h2 class="rail-title">Settlers</h2>
      ${state.players
        .map(
          (player) => `
          <article class="player-card${player.is_active ? " active" : ""}">
            <div class="player-head">
              <div class="avatar" style="background:${player.color}">${escapeHtml(initials(player.username))}</div>
              <div>
                <div class="player-name">${escapeHtml(player.username)}${player.id === clientId ? " · You" : ""}</div>
                <div class="player-status">${player.connected ? "At the table" : "Away"}</div>
              </div>
              <div class="score-badge" title="Visible victory points">${player.score}</div>
            </div>
            <div class="player-stats">
              <div class="stat">Cards <strong>${player.resource_count}</strong></div>
              <div class="stat">Dev <strong>${player.development_count}</strong></div>
              <div class="stat">Road <strong>${player.longest_road_length}</strong></div>
              <div class="stat">Knights <strong>${player.played_knights}</strong></div>
              ${
                state.longest_road_holder === player.id
                  ? '<div class="stat award">Longest Road · 2 VP</div>'
                  : ""
              }
              ${
                state.largest_army_holder === player.id
                  ? '<div class="stat award">Largest Army · 2 VP</div>'
                  : ""
              }
            </div>
          </article>`,
        )
        .join("")}
    </aside>`;
}

function terrainPatternDefs() {
  return `
    <defs>
      <linearGradient id="forestBase" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#5f8a4d"/><stop offset="1" stop-color="#274e3b"/>
      </linearGradient>
      <pattern id="forestPattern" width="22" height="24" patternUnits="userSpaceOnUse">
        <rect width="22" height="24" fill="url(#forestBase)"/>
        <path d="M5 20 10 6l5 14M1 22 6 11l5 11M12 22l5-12 5 12" fill="#244b36" stroke="#79a45a" stroke-width="1"/>
      </pattern>
      <linearGradient id="hillsBase" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#c9834a"/><stop offset="1" stop-color="#8c4937"/>
      </linearGradient>
      <pattern id="hillsPattern" width="34" height="24" patternUnits="userSpaceOnUse">
        <rect width="34" height="24" fill="url(#hillsBase)"/>
        <path d="M-4 24Q7 7 18 24M12 24Q23 6 38 24" fill="#a75d3b" stroke="#e0a05e" stroke-width="1"/>
      </pattern>
      <linearGradient id="pastureBase" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#9dbd68"/><stop offset="1" stop-color="#6f984e"/>
      </linearGradient>
      <pattern id="pasturePattern" width="28" height="24" patternUnits="userSpaceOnUse">
        <rect width="28" height="24" fill="url(#pastureBase)"/>
        <path d="M4 24q3-8 5 0m5 0q3-11 6 0m3 0q2-6 4 0" fill="none" stroke="#d1dd82" stroke-width="1.5"/>
      </pattern>
      <linearGradient id="fieldsBase" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#e2bd58"/><stop offset="1" stop-color="#b7822f"/>
      </linearGradient>
      <pattern id="fieldsPattern" width="18" height="26" patternUnits="userSpaceOnUse">
        <rect width="18" height="26" fill="url(#fieldsBase)"/>
        <path d="M2 26 14 0M-6 26 6 0M10 26 22 0" stroke="#f3d879" stroke-width="2"/>
      </pattern>
      <linearGradient id="mountainsBase" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#89919a"/><stop offset="1" stop-color="#515c66"/>
      </linearGradient>
      <pattern id="mountainsPattern" width="42" height="30" patternUnits="userSpaceOnUse">
        <rect width="42" height="30" fill="url(#mountainsBase)"/>
        <path d="M-5 30 10 5l7 12 7-9 20 22" fill="#626c75" stroke="#b9c0bf" stroke-width="1.2"/>
        <path d="m6 12 4-7 4 7" fill="#e1dfd3"/>
      </pattern>
      <linearGradient id="desertPattern" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#d9b978"/><stop offset="0.5" stop-color="#c69a59"/><stop offset="1" stop-color="#e1c98d"/>
      </linearGradient>
      <filter id="tileShadow" x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#05242b" flood-opacity=".45"/>
      </filter>
      <filter id="pieceShadow" x="-80%" y="-80%" width="260%" height="260%">
        <feDropShadow dx="0" dy="4" stdDeviation="3" flood-color="#06181d" flood-opacity=".7"/>
      </filter>
      <filter id="targetGlow" x="-80%" y="-80%" width="260%" height="260%">
        <feDropShadow dx="0" dy="0" stdDeviation="7" flood-color="#ffe4a1" flood-opacity=".9"/>
      </filter>
    </defs>`;
}

function polygonPoints(x, y, radius = 62) {
  return Array.from({ length: 6 }, (_, index) => {
    const angle = (Math.PI / 3) * index;
    return `${x + radius * Math.cos(angle)},${y + radius * Math.sin(angle)}`;
  }).join(" ");
}

function pips(number) {
  return { 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1 }[number] || 0;
}

function harborResourceIcon(type, x, y) {
  const icons = {
    brick: `
      <g class="harbor-resource-icon" transform="translate(${x} ${y - 4})">
        <rect x="-9" y="-5" width="8" height="5" rx="1" fill="#a94f3d"/>
        <rect x="1" y="-5" width="8" height="5" rx="1" fill="#c9684d"/>
        <rect x="-5" y="2" width="8" height="5" rx="1" fill="#c9684d"/>
        <rect x="5" y="2" width="6" height="5" rx="1" fill="#a94f3d"/>
      </g>`,
    lumber: `
      <g class="harbor-resource-icon" transform="translate(${x} ${y - 4})">
        <path d="M0-11-8-1h5l-6 7h7v5h4V6h7L3-1h5Z" fill="#326847" stroke="#234735" stroke-width="1"/>
      </g>`,
    wool: `
      <g class="harbor-resource-icon" transform="translate(${x} ${y - 4})">
        <path d="M-8 4a5 5 0 0 1 1-9 6 6 0 0 1 11-1 5 5 0 0 1 3 9H-8Z" fill="#f6f0db" stroke="#665d4c" stroke-width="1.2"/>
        <circle cx="7" cy="1" r="3.5" fill="#5e5547"/>
        <path d="M-5 4v5M2 4v5" stroke="#5e5547" stroke-width="1.5"/>
      </g>`,
    grain: `
      <g class="harbor-resource-icon" transform="translate(${x} ${y - 4})" fill="none" stroke="#b98224" stroke-linecap="round" stroke-width="1.7">
        <path d="M0 10V-10M-1-5l-5-4M1-2l5-4M-1 1l-6-3M1 4l6-3"/>
        <path d="M-5-9c3 0 4 1 4 4M5-6c-3 0-4 1-4 4M-6-2c3 0 5 1 5 4M6 1C3 1 1 2 1 5" fill="#d3a43e"/>
      </g>`,
    ore: `
      <g class="harbor-resource-icon" transform="translate(${x} ${y - 4})">
        <path d="m-11 8 8-17 5 8 4-6 7 15Z" fill="#7b8790" stroke="#424d55" stroke-linejoin="round" stroke-width="1.2"/>
        <path d="m-3-9-3 7 3-2 3 3 2-1Z" fill="#e7e4d8"/>
        <circle cx="5" cy="4" r="2" fill="#4d5a63"/>
      </g>`,
  };
  return icons[type] || "";
}

function renderBoard() {
  const board = state.board;
  const playerById = Object.fromEntries(state.players.map((player) => [player.id, player]));
  const showRoads =
    state.phase === "setup_road" ||
    state.phase === "road_building" ||
    (state.phase === "action" && ui.buildMode === "road");
  const showSettlements =
    state.phase === "setup_settlement" ||
    (state.phase === "action" && ["settlement", "city"].includes(ui.buildMode));
  const legalRoads = showRoads ? new Set(state.legal.legal_roads) : new Set();
  const legalVertices = showSettlements
    ? new Set(ui.buildMode === "city" ? state.legal.legal_cities : state.legal.legal_settlements)
    : new Set();
  const robberTargets = new Set(state.legal.robber_hexes || []);

  const harbors = board.harbors
    .map((harbor) => {
      const edge = board.edges[harbor.edge];
      const midpoint = {
        x: (board.vertices[edge.vertices[0]].x + board.vertices[edge.vertices[1]].x) / 2,
        y: (board.vertices[edge.vertices[0]].y + board.vertices[edge.vertices[1]].y) / 2,
      };
      const marker =
        harbor.type === "generic"
          ? `<text class="harbor-label" x="${harbor.x}" y="${harbor.y + 3}">3:1</text>`
          : `${harborResourceIcon(harbor.type, harbor.x, harbor.y)}
             <text class="harbor-rate" x="${harbor.x}" y="${harbor.y + 14}">2:1</text>`;
      const harborName =
        harbor.type === "generic" ? "3:1 harbor" : `2:1 ${RESOURCE_LABELS[harbor.type]} harbor`;
      return `
        <g class="harbor-marker" role="img" aria-label="${harborName}">
          <title>${harborName}</title>
          <path class="harbor-line" d="M${midpoint.x} ${midpoint.y} L${harbor.x} ${harbor.y}"/>
          <circle class="harbor-badge" cx="${harbor.x}" cy="${harbor.y}" r="20"/>
          ${marker}
        </g>`;
    })
    .join("");

  const hexes = board.hexes
    .map((hex) => {
      const fill = hex.terrain === "desert" ? "url(#desertPattern)" : `url(#${hex.terrain}Pattern)`;
      const target = robberTargets.has(hex.id);
      const token = hex.number
        ? `<circle class="number-token" cx="${hex.x}" cy="${hex.y}" r="25"/>
           <text class="number-text${[6, 8].includes(hex.number) ? " hot" : ""}" x="${hex.x}" y="${hex.y + 3}">${hex.number}</text>
           <text class="pip-text" x="${hex.x}" y="${hex.y + 15}">${"•".repeat(pips(hex.number))}</text>`
        : "";
      return `
        <g ${target ? `data-action="move-robber" data-id="${hex.id}"` : ""}>
          <polygon class="hex-tile${target ? " robber-target" : ""}" points="${polygonPoints(hex.x, hex.y)}" fill="${fill}"/>
          ${token}
        </g>`;
    })
    .join("");

  const roads = Object.entries(state.roads)
    .map(([edgeId, road]) => {
      const edge = board.edges[edgeId];
      const start = board.vertices[edge.vertices[0]];
      const end = board.vertices[edge.vertices[1]];
      const color = playerById[road.player_id].color;
      return `<line class="road-under" x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}"/>
        <line class="road-piece" x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}" stroke="${color}"/>`;
    })
    .join("");

  const legalRoadMarkup = [...legalRoads]
    .map((edgeId) => {
      const edge = board.edges[edgeId];
      const start = board.vertices[edge.vertices[0]];
      const end = board.vertices[edge.vertices[1]];
      return `<line class="legal-road" data-action="place-road" data-id="${edgeId}"
        x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}"/>`;
    })
    .join("");

  const buildings = Object.entries(state.buildings)
    .map(([vertexId, building]) => {
      const vertex = board.vertices[vertexId];
      const color = playerById[building.player_id].color;
      if (building.type === "city") {
        return `<path class="piece" fill="${color}" d="M${vertex.x - 15} ${vertex.y + 11}v-19l9-8 8 7v-5h10v35z"/>`;
      }
      return `<path class="piece" fill="${color}" d="M${vertex.x - 13} ${vertex.y + 11}v-17l13-11 13 11v17z"/>`;
    })
    .join("");

  const legalVertexMarkup = [...legalVertices]
    .map((vertexId) => {
      const vertex = board.vertices[vertexId];
      const kind =
        state.phase === "setup_settlement" ? "setup" : ui.buildMode === "city" ? "city" : "settlement";
      return `<circle class="legal-vertex" data-action="place-vertex" data-kind="${kind}" data-id="${vertexId}"
        cx="${vertex.x}" cy="${vertex.y}" r="8"/>`;
    })
    .join("");

  const robberHex = board.hexes.find((hex) => hex.id === board.robber_hex);
  const robber = `
    <g class="robber" transform="translate(${robberHex.x} ${robberHex.y - 2})">
      <ellipse cx="0" cy="19" rx="14" ry="6" fill="rgba(0,0,0,.3)"/>
      <circle cx="0" cy="-9" r="9" fill="#3a4547" stroke="#d0c6ae" stroke-width="2"/>
      <path d="M-11 16Q-10-2 0-4Q10-2 11 16Z" fill="#303b3e" stroke="#d0c6ae" stroke-width="2"/>
    </g>`;

  return `
    <svg class="board-svg" viewBox="-370 -340 740 680" role="img" aria-label="Catan game board">
      ${terrainPatternDefs()}
      <g>${harbors}</g>
      <g>${hexes}</g>
      <g>${roads}${legalRoadMarkup}</g>
      <g>${buildings}${legalVertexMarkup}</g>
      ${robber}
    </svg>`;
}

function renderActionRail() {
  const isActive = state.active_player_id === clientId;
  const rollCard =
    state.phase === "roll"
      ? `<article class="action-card emphasis">
          <h3>${isActive ? "Your roll" : "Awaiting the dice"}</h3>
          <p>${isActive ? "Roll both dice to begin resource production." : "The active settler is deciding their move."}</p>
          <button class="btn btn-primary btn-block" data-action="roll-dice" ${state.legal.can_roll ? "" : "disabled"}>
            ${icon("dice")} Roll the dice
          </button>
        </article>`
      : state.last_roll
        ? `<article class="action-card">
            <h3>Last production roll</h3>
            <div class="dice"><div class="die">${state.last_roll[0]}</div><div class="die">${state.last_roll[1]}</div></div>
          </article>`
        : "";

  const setupCard = state.phase.startsWith("setup_")
    ? `<article class="action-card emphasis">
        <h3>${isActive ? "Place your pieces" : "Opening settlement"}</h3>
        <p>${
          isActive
            ? state.phase === "setup_settlement"
              ? "Choose any glowing intersection that follows the distance rule."
              : "Choose a glowing path touching your new settlement."
            : `${escapeHtml(state.players.find((player) => player.is_active)?.username)} is choosing.`
        }</p>
      </article>`
    : "";

  const actionCard =
    isActive && ["action", "road_building"].includes(state.phase)
      ? `<article class="action-card emphasis">
          <h3>${state.phase === "road_building" ? "Free road placement" : "Shape your turn"}</h3>
          <p>${state.phase === "road_building" ? "Place up to two connected roads without paying resources." : "Trade and build in any order, then end your turn."}</p>
          <div class="action-grid">
            <button class="btn ${ui.buildMode === "road" ? "btn-primary" : "btn-secondary"}" data-action="build-mode" data-kind="road"
              ${state.legal.legal_roads.length ? "" : "disabled"}>Road<span class="cost">brick + lumber</span></button>
            <button class="btn ${ui.buildMode === "settlement" ? "btn-primary" : "btn-secondary"}" data-action="build-mode" data-kind="settlement"
              ${state.phase === "action" && state.legal.legal_settlements.length ? "" : "disabled"}>Settlement<span class="cost">4 resources</span></button>
            <button class="btn ${ui.buildMode === "city" ? "btn-primary" : "btn-secondary"}" data-action="build-mode" data-kind="city"
              ${state.phase === "action" && state.legal.legal_cities.length ? "" : "disabled"}>City<span class="cost">3 ore + 2 grain</span></button>
            <button class="btn btn-secondary" data-action="buy-development" ${state.legal.can_buy_development ? "" : "disabled"}>Dev card<span class="cost">ore + wool + grain</span></button>
            <button class="btn btn-secondary" data-action="open-trade" ${state.phase === "action" ? "" : "disabled"}>${icon("trade")} Trade</button>
            ${
              state.phase === "road_building"
                ? '<button class="btn btn-secondary" data-action="finish-roads">Finish roads</button>'
                : '<button class="btn btn-primary" data-action="end-turn">End turn</button>'
            }
          </div>
        </article>`
      : "";

  const waitingCard =
    !isActive && !state.phase.startsWith("setup_") && state.phase !== "finished"
      ? `<article class="action-card">
          <h3>Watch the table</h3>
          <p>You can review your hand and make trade offers when the active player reaches their action phase.</p>
          ${
            state.phase === "action"
              ? `<button class="btn btn-secondary btn-block" data-action="open-trade">${icon("trade")} Offer a trade</button>`
              : ""
          }
        </article>`
      : "";

  const offers = state.trade_offers
    .map((offer) => {
      const from = state.players.find((player) => player.id === offer.from);
      const to = state.players.find((player) => player.id === offer.to);
      const give = bundleText(offer.give);
      const receive = bundleText(offer.receive);
      return `<div class="offer">
        <strong>${escapeHtml(from.username)}</strong> offers ${give} to ${escapeHtml(to.username)} for ${receive}.
        ${
          offer.to === clientId
            ? `<div class="offer-actions">
                <button class="btn btn-primary" data-action="respond-trade" data-id="${offer.id}" data-accept="true">Accept</button>
                <button class="btn btn-secondary" data-action="respond-trade" data-id="${offer.id}" data-accept="false">Decline</button>
              </div>`
            : ""
        }
      </div>`;
    })
    .join("");

  const log = [...state.log]
    .reverse()
    .map((line) => `<div class="log-line">${escapeHtml(line)}</div>`)
    .join("");

  return `
    <aside class="action-rail">
      <h2 class="rail-title">Turn actions</h2>
      ${setupCard}${rollCard}${actionCard}${waitingCard}
      ${
        offers
          ? `<article class="action-card"><h3>Trade table</h3><div class="mini-list">${offers}</div></article>`
          : ""
      }
      <article class="action-card">
        <h3>Table chronicle</h3>
        <div class="game-log">${log}</div>
      </article>
    </aside>`;
}

function renderHand() {
  const counts = state.you.resources;
  const cardCounts = state.you.development_cards.reduce((all, card) => {
    all[card] = (all[card] || 0) + 1;
    return all;
  }, {});
  const playable = new Set(state.legal.playable_development || []);
  const cards = Object.entries(cardCounts)
    .map(
      ([card, count]) => `
        <button class="dev-chip" data-action="play-development" data-kind="${card}"
          ${playable.has(card) ? "" : "disabled"}>${escapeHtml(CARD_LABELS[card])} ×${count}</button>`,
    )
    .join("");
  return `
    <footer class="hand-tray">
      <div class="hand-summary">
        <div class="dev-stack">
          <strong>Your private hand</strong>
          Score ${state.you.score} · ${state.you.development_cards.length} development cards
          <div>${cards || '<span class="player-status">No development cards yet</span>'}</div>
        </div>
      </div>
      <div class="resource-hand">
        ${RESOURCES.map(
          (resource) => `
            <div class="resource-card ${resource}">
              <strong>${counts[resource] || 0}</strong>
              <span>${RESOURCE_LABELS[resource]}</span>
            </div>`,
        ).join("")}
      </div>
      <div class="hand-actions">
        <div class="dev-stack">
          <strong>${state.development_deck_count} cards in deck</strong>
          Bank: ${RESOURCES.map((resource) => `${state.bank[resource]} ${resource}`).join(" · ")}
        </div>
      </div>
    </footer>`;
}

function renderModal() {
  if (!ui.modal) return "";
  if (ui.modal === "discard") return renderDiscardModal();
  if (ui.modal === "steal") return renderStealModal();
  if (ui.modal === "trade") return renderTradeModal();
  if (ui.modal === "plenty") return renderPlentyModal();
  if (ui.modal === "monopoly") return renderMonopolyModal();
  if (ui.modal === "winner") return renderWinnerModal();
  return "";
}

function renderDiscardModal() {
  const required = state.legal.must_discard;
  const chosen = Object.values(ui.discard).reduce((sum, amount) => sum + amount, 0);
  return `
    <div class="modal-backdrop">
      <section class="modal">
        <h2>The robber strikes</h2>
        <p>You hold more than seven cards. Return exactly ${required} cards to the bank before play continues.</p>
        ${renderCounters("discard", ui.discard, state.you.resources)}
        <div class="modal-actions">
          <span class="player-status">${chosen} of ${required} selected</span>
          <button class="btn btn-primary" data-action="submit-discard" ${chosen === required ? "" : "disabled"}>Return cards</button>
        </div>
      </section>
    </div>`;
}

function renderStealModal() {
  const victims = state.legal.victims || [];
  return `
    <div class="modal-backdrop">
      <section class="modal">
        <h2>Choose a card to steal</h2>
        <p>The card will be selected at random from the chosen player's hidden resource hand.</p>
        <div class="mini-list">
          ${victims
            .map((victimId) => {
              const player = state.players.find((candidate) => candidate.id === victimId);
              return `<button class="btn btn-secondary btn-block" data-action="steal" data-id="${victimId}">
                <span class="avatar" style="background:${player.color}">${escapeHtml(initials(player.username))}</span>
                ${escapeHtml(player.username)} · ${player.resource_count} cards
              </button>`;
            })
            .join("")}
        </div>
      </section>
    </div>`;
}

function renderTradeModal() {
  const targets =
    state.active_player_id === clientId
      ? state.players.filter((player) => player.id !== clientId)
      : state.players.filter((player) => player.id === state.active_player_id);
  if (!targets.some((target) => target.id === ui.tradeTarget)) {
    ui.tradeTarget = targets[0]?.id || "";
  }
  const rate = state.legal.harbor_rates[ui.bankGive];
  return `
    <div class="modal-backdrop" data-action="close-modal">
      <section class="modal" data-modal-panel>
        <h2>Trade table</h2>
        <p>Trade with the bank at your best harbor rate, or propose an exchange with another settler.</p>
        <div class="action-grid">
          <button class="btn ${ui.tradeMode === "player" ? "btn-primary" : "btn-secondary"}" data-action="trade-mode" data-kind="player">Player trade</button>
          <button class="btn ${ui.tradeMode === "bank" ? "btn-primary" : "btn-secondary"}" data-action="trade-mode" data-kind="bank">Maritime trade</button>
        </div>
        ${
          ui.tradeMode === "player"
            ? `<div class="field">
                <label>Trade with</label>
                <select class="input" data-change="trade-target">
                  ${targets.map((player) => `<option value="${player.id}" ${player.id === ui.tradeTarget ? "selected" : ""}>${escapeHtml(player.username)}</option>`).join("")}
                </select>
              </div>
              <div class="trade-columns">
                <div class="trade-side"><h3>You give</h3>${renderCounters("trade-give", ui.tradeGive, state.you.resources)}</div>
                <div class="trade-side"><h3>You request</h3>${renderCounters("trade-receive", ui.tradeReceive)}</div>
              </div>
              <div class="modal-actions">
                <button class="btn btn-secondary" data-action="close-modal">Cancel</button>
                <button class="btn btn-primary" data-action="submit-trade">Send offer</button>
              </div>`
            : `<div class="trade-columns">
                <div class="field">
                  <label>You give ${rate}</label>
                  <select class="input" data-change="bank-give">
                    ${RESOURCES.map((resource) => `<option value="${resource}" ${resource === ui.bankGive ? "selected" : ""}>${RESOURCE_LABELS[resource]} (${state.legal.harbor_rates[resource]}:1)</option>`).join("")}
                  </select>
                </div>
                <div class="field">
                  <label>You receive 1</label>
                  <select class="input" data-change="bank-receive">
                    ${RESOURCES.filter((resource) => resource !== ui.bankGive).map((resource) => `<option value="${resource}" ${resource === ui.bankReceive ? "selected" : ""}>${RESOURCE_LABELS[resource]} · bank ${state.bank[resource]}</option>`).join("")}
                  </select>
                </div>
              </div>
              <div class="modal-actions">
                <button class="btn btn-secondary" data-action="close-modal">Cancel</button>
                <button class="btn btn-primary" data-action="submit-bank-trade"
                  ${state.you.resources[ui.bankGive] >= rate && state.bank[ui.bankReceive] > 0 ? "" : "disabled"}>
                  Trade ${rate} for 1
                </button>
              </div>`
        }
      </section>
    </div>`;
}

function renderPlentyModal() {
  return `
    <div class="modal-backdrop">
      <section class="modal">
        <h2>Year of Plenty</h2>
        <p>Choose any two resources from the bank. You may choose the same resource twice if the bank has both cards.</p>
        <div class="resource-choice">
          ${RESOURCES.map((resource) => {
            const selected = ui.plenty.filter((item) => item === resource).length;
            return `<button class="choice-card${selected ? " selected" : ""}" data-action="plenty-choice" data-kind="${resource}"
              ${state.bank[resource] <= selected ? "disabled" : ""}>${RESOURCE_LABELS[resource]}${selected ? ` ×${selected}` : ""}<br><small>Bank ${state.bank[resource]}</small></button>`;
          }).join("")}
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" data-action="plenty-clear">Clear</button>
          <button class="btn btn-primary" data-action="submit-plenty" ${ui.plenty.length === 2 ? "" : "disabled"}>Take resources</button>
        </div>
      </section>
    </div>`;
}

function renderMonopolyModal() {
  return `
    <div class="modal-backdrop">
      <section class="modal">
        <h2>Declare a monopoly</h2>
        <p>Every other player must give you every card they hold of the resource you name.</p>
        <div class="resource-choice">
          ${RESOURCES.map(
            (resource) => `<button class="choice-card${ui.monopoly === resource ? " selected" : ""}" data-action="monopoly-choice" data-kind="${resource}">${RESOURCE_LABELS[resource]}</button>`,
          ).join("")}
        </div>
        <div class="modal-actions">
          <button class="btn btn-primary" data-action="submit-monopoly">Claim ${RESOURCE_LABELS[ui.monopoly]}</button>
        </div>
      </section>
    </div>`;
}

function renderWinnerModal() {
  const winner = state.players.find((player) => player.id === state.winner_id);
  return `
    <div class="modal-backdrop">
      <section class="modal winner-card">
        <div class="winner-sun">${winner.score}</div>
        <div class="eyebrow" style="justify-content:center">The island is settled</div>
        <h2>${escapeHtml(winner.username)} wins</h2>
        <p>Ten victory points have been revealed. The roads, cities, army, and hidden achievements now belong to Catan history.</p>
        <button class="btn btn-primary" data-action="dismiss-winner">View the final board</button>
      </section>
    </div>`;
}

function renderCounters(prefix, values, limits = null) {
  return `<div class="counter-grid">
    ${RESOURCES.map(
      (resource) => `
      <div class="counter">
        <strong>${RESOURCE_LABELS[resource]}</strong>
        <div class="counter-controls">
          <button data-action="counter" data-prefix="${prefix}" data-kind="${resource}" data-delta="-1">−</button>
          <span>${values[resource] || 0}</span>
          <button data-action="counter" data-prefix="${prefix}" data-kind="${resource}" data-delta="1"
            ${limits && (values[resource] || 0) >= (limits[resource] || 0) ? "disabled" : ""}>+</button>
        </div>
      </div>`,
    ).join("")}
  </div>`;
}

function bundleText(bundle) {
  return Object.entries(bundle)
    .filter(([, amount]) => amount)
    .map(([resource, amount]) => `${amount} ${resource}`)
    .join(", ");
}

root.addEventListener("input", (event) => {
  if (event.target.name === "username") {
    ui.username = event.target.value;
  }
  if (event.target.name === "join-code") {
    ui.joinCode = event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    event.target.value = ui.joinCode;
  }
});

root.addEventListener("change", (event) => {
  const action = event.target.dataset.change;
  if (action === "trade-target") ui.tradeTarget = event.target.value;
  if (action === "bank-give") {
    ui.bankGive = event.target.value;
    if (ui.bankReceive === ui.bankGive) {
      ui.bankReceive = RESOURCES.find((resource) => resource !== ui.bankGive);
    }
  }
  if (action === "bank-receive") ui.bankReceive = event.target.value;
  render();
});

root.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target || target.disabled) return;
  const action = target.dataset.action;

  if (action === "create-game" || action === "join-game") {
    const username = ui.username.trim();
    if (!username) {
      showToast("Enter a gamer tag first.", true);
      return;
    }
    localStorage.setItem("catan_username", username);
    if (action === "create-game") {
      socket.emit("create_game", { client_id: clientId, username });
    } else {
      socket.emit("join_game", { client_id: clientId, username, code: ui.joinCode });
    }
    return;
  }

  if (action === "copy-code") {
    navigator.clipboard?.writeText(state.code);
    showToast(`Room code ${state.code} copied.`);
  } else if (action === "start-game") {
    emitGame("start_game");
  } else if (action === "leave-game") {
    emitGame("leave_game");
  } else if (action === "roll-dice") {
    emitGame("roll_dice");
  } else if (action === "build-mode") {
    ui.buildMode = ui.buildMode === target.dataset.kind ? null : target.dataset.kind;
    render();
  } else if (action === "place-road") {
    if (state.phase === "setup_road") {
      emitGame("setup_road", { edge_id: target.dataset.id });
    } else {
      emitGame("build", { kind: "road", location_id: target.dataset.id });
    }
  } else if (action === "place-vertex") {
    if (target.dataset.kind === "setup") {
      emitGame("setup_settlement", { vertex_id: target.dataset.id });
    } else {
      emitGame("build", { kind: target.dataset.kind, location_id: target.dataset.id });
    }
  } else if (action === "move-robber") {
    emitGame("move_robber", { hex_id: target.dataset.id });
  } else if (action === "steal") {
    ui.modal = null;
    emitGame("steal", { victim_id: target.dataset.id });
  } else if (action === "buy-development") {
    emitGame("buy_development");
  } else if (action === "finish-roads") {
    emitGame("finish_road_building");
  } else if (action === "end-turn") {
    ui.buildMode = null;
    emitGame("end_turn");
  } else if (action === "open-trade") {
    ui.modal = "trade";
    render();
  } else if (action === "trade-mode") {
    ui.tradeMode = target.dataset.kind;
    render();
  } else if (action === "close-modal") {
    if (event.target.closest("[data-modal-panel]") && target.classList.contains("modal-backdrop")) return;
    ui.modal = null;
    render();
  } else if (action === "counter") {
    updateCounter(target.dataset.prefix, target.dataset.kind, Number(target.dataset.delta));
  } else if (action === "submit-discard") {
    emitGame("discard", { cards: ui.discard });
  } else if (action === "submit-trade") {
    const giveTotal = Object.values(ui.tradeGive).reduce((sum, amount) => sum + amount, 0);
    const receiveTotal = Object.values(ui.tradeReceive).reduce((sum, amount) => sum + amount, 0);
    if (!giveTotal || !receiveTotal) {
      showToast("Add resources to both sides of the offer.", true);
      return;
    }
    emitGame("offer_trade", {
      target_id: ui.tradeTarget,
      give: ui.tradeGive,
      receive: ui.tradeReceive,
    });
    ui.modal = null;
    resetTrade();
  } else if (action === "submit-bank-trade") {
    emitGame("maritime_trade", { give: ui.bankGive, receive: ui.bankReceive });
    ui.modal = null;
  } else if (action === "respond-trade") {
    emitGame("respond_trade", { offer_id: target.dataset.id, accept: target.dataset.accept === "true" });
  } else if (action === "play-development") {
    playDevelopment(target.dataset.kind);
  } else if (action === "plenty-choice") {
    if (ui.plenty.length < 2) ui.plenty.push(target.dataset.kind);
    render();
  } else if (action === "plenty-clear") {
    ui.plenty = [];
    render();
  } else if (action === "submit-plenty") {
    ui.modal = null;
    emitGame("play_development", { card_type: "year_of_plenty", choice: ui.plenty });
    ui.plenty = [];
  } else if (action === "monopoly-choice") {
    ui.monopoly = target.dataset.kind;
    render();
  } else if (action === "submit-monopoly") {
    ui.modal = null;
    emitGame("play_development", { card_type: "monopoly", choice: ui.monopoly });
  } else if (action === "dismiss-winner") {
    ui.modal = null;
    render();
  }
});

function updateCounter(prefix, resource, delta) {
  const map = {
    discard: ui.discard,
    "trade-give": ui.tradeGive,
    "trade-receive": ui.tradeReceive,
  }[prefix];
  if (!map) return;
  const next = Math.max(0, (map[resource] || 0) + delta);
  if (prefix === "discard" || prefix === "trade-give") {
    map[resource] = Math.min(next, state.you.resources[resource] || 0);
  } else {
    map[resource] = next;
  }
  render();
}

function resetTrade() {
  ui.tradeGive = Object.fromEntries(RESOURCES.map((resource) => [resource, 0]));
  ui.tradeReceive = Object.fromEntries(RESOURCES.map((resource) => [resource, 0]));
}

function playDevelopment(card) {
  if (card === "year_of_plenty") {
    ui.plenty = [];
    ui.modal = "plenty";
    render();
  } else if (card === "monopoly") {
    ui.modal = "monopoly";
    render();
  } else if (card !== "victory_point") {
    emitGame("play_development", { card_type: card });
  }
}

render();
