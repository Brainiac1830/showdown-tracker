// ============================================================
// tournaments.js — the Tournaments page.
// Pick a tournament: every player seen in it (by you or shared by others),
// with their KNOWN deck. Decks are locked during a tournament, so every card a
// player played in their tournament matches is in their deck.
// Known copies = the most copies seen in one match (same as tournament_deck() in profiles.py).
// Generated cards are never in a sighting's cards, so they never count.
// ============================================================

import { watchUser } from "./firebase.js";
import { loadMatches, loadSightings } from "./database.js";

const pageStatus   = document.getElementById("page-status");
const pick         = document.getElementById("tournament-pick");
const playerSearch = document.getElementById("player-search");
const listBox      = document.getElementById("tournament-players");

let tournaments = [];      // [{ key, name, lastPlayed, players: [...] }], newest first


// ---------- 1. FROM MATCHES + SIGHTINGS TO TOURNAMENTS ----------

// "Sunday  Cup " and "sunday cup" are the same tournament
function tournamentKey(name) {
  return (name || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function buildTournaments(matches, sightings) {
  // Every player appearance with a tournament, each match counted once per player
  const all = {};
  for (const match of matches) {
    if (!tournamentKey(match.tournament)) {
      continue;
    }
    for (const a of appearances(match)) {
      all[match.gameId + "|" + a.name.toLowerCase()] = {
        name: a.name, classes: a.classes, cards: a.cards, playedAt: match.playedAt,
        tournament: match.tournament, mine: !match.spectated, result: match.result };
    }
  }
  for (const s of sightings) {
    const id = s.gameId + "|" + (s.name || "").toLowerCase();
    const cardsSeen = Object.values(s.cards || {}).reduce(function (sum, n) { return sum + n; }, 0);
    const tooLittle = !(s.classes || []).length && cardsSeen < 2;     // unknown classes, almost nothing seen
    if (s.name && tournamentKey(s.tournament) && !all[id] && !tooLittle) {
      all[id] = { name: s.name, classes: s.classes || [], cards: s.cards || {}, playedAt: s.playedAt || 0,
                  tournament: s.tournament, mine: false };
    }
  }

  // Group: tournament -> player -> known deck
  const byTournament = {};
  for (const a of Object.values(all)) {
    const tKey = tournamentKey(a.tournament);
    const t = byTournament[tKey] = byTournament[tKey] || { key: tKey, name: a.tournament.trim(), lastPlayed: 0, players: {} };
    if (a.playedAt > t.lastPlayed) {
      t.lastPlayed = a.playedAt;
      t.name = a.tournament.trim();            // the newest spelling
    }
    const pKey = a.name.toLowerCase();
    const p = t.players[pKey] = t.players[pKey] || { name: a.name, classes: a.classes, matches: 0, cards: {},
                                                     wins: 0, losses: 0, lastSeen: 0 };
    p.matches += 1;
    if (a.playedAt >= p.lastSeen) {
      p.lastSeen = a.playedAt;
      p.name = a.name;
      p.classes = a.classes;
    }
    if (a.mine) {                              // my own match against them
      p.wins += a.result === "win" ? 1 : 0;
      p.losses += a.result === "loss" ? 1 : 0;
    }
    for (const [id, n] of Object.entries(a.cards)) {
      p.cards[id] = Math.max(p.cards[id] || 0, n);      // most copies seen in one match
    }
  }
  return Object.values(byTournament)
    .map(function (t) {
      t.players = Object.values(t.players).map(function (p) {
        p.known = Object.values(p.cards).reduce(function (sum, n) { return sum + n; }, 0);
        return p;
      }).sort(function (a, b) { return b.known - a.known || a.name.localeCompare(b.name); });
      return t;
    })
    .sort(function (a, b) { return b.lastPlayed - a.lastPlayed; });
}


// ---------- 2. DRAWING ----------

function fillPicker() {
  pick.innerHTML = tournaments.map(function (t) {
    return `<option value="${escapeHtml(t.key)}">${escapeHtml(t.name)} (${t.players.length} players)</option>`;
  }).join("");
}

function render() {
  listBox.innerHTML = "";
  if (tournaments.length === 0) {
    listBox.innerHTML = `<p class="page-status">No tournaments yet. Click the trophy on the tracker's overlay to turn on
      tournament mode, then play or watch tournament matches.</p>`;
    return;
  }
  const t = tournaments.find(function (x) { return x.key === pick.value; }) || tournaments[0];
  const text = playerSearch.value.trim().toLowerCase();
  const shown = t.players.filter(function (p) { return p.name.toLowerCase().includes(text); });
  if (shown.length === 0) {
    listBox.innerHTML = `<p class="page-status">No player with that name in this tournament.</p>`;
    return;
  }
  for (const p of shown) {
    listBox.appendChild(createRow(p));
  }
}

function createRow(p) {
  const row = document.createElement("div");
  row.className = "match-row player-row";
  const record = p.wins + p.losses > 0
    ? `<span style="color: var(--win)">${p.wins}W</span> <span style="color: var(--loss)">${p.losses}L</span> · `
    : "";
  row.innerHTML = `
    <div class="match-main player-main">
      <span class="match-name">${escapeHtml(p.name)}</span>
      <span class="small">${classTags(p.classes)}</span>
      <span class="small"><b style="color: var(--yellow)">${p.known}/30</b> known
        <span class="dim">· ${record}${p.matches} match${p.matches === 1 ? "" : "es"}</span></span>
      <span class="match-date dim small">${formatDate(p.lastSeen)}</span>
    </div>
    <div class="match-details hidden">
      <p class="details-title">Known deck · count = copies seen in one match (they may have more)</p>
      <div class="card-list">${cardBars(p.cards)}</div>
    </div>
  `;
  const details = row.querySelector(".match-details");
  row.querySelector(".match-main").addEventListener("click", function () {
    details.classList.toggle("hidden");
  });
  return row;
}


// ---------- 3. START ----------
pick.addEventListener("change", render);
playerSearch.addEventListener("input", render);

watchUser(async function (user) {
  if (!user) {
    tournaments = [];
    listBox.innerHTML = "";
    pick.innerHTML = "";
    pageStatus.textContent = "Sign in (top menu) to see the tournaments.";
    return;
  }
  pageStatus.textContent = "Loading...";
  try {
    const matches = await loadMatches();
    let sightings = [];
    try {
      sightings = await loadSightings();
      pageStatus.textContent = "";
    } catch (error) {
      pageStatus.textContent = "Shared player data couldn't be loaded (" + error.code + "): showing your own matches only.";
      console.error(error);
    }
    tournaments = buildTournaments(matches, sightings);
    fillPicker();
    render();
  } catch (error) {
    pageStatus.textContent = "Couldn't load the matches: " + error.message;
    console.error(error);
  }
});
