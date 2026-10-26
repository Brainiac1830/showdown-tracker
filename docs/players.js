// ============================================================
// players.js — the Players page.
// Everyone you've played against or watched (spectated), plus the players other
// people's trackers shared (showdown_sightings), most seen first.
// Click a player to see, for each pair of classes they used, the cards they
// played and in how many of those matches (%).
//
// This is NOT their decklist: we only see the cards a player PLAYS (about 10 of
// their 30 per match), so even a card they always run can show 40-60%.
// The tracker's overlay uses the same numbers (profiles.py) for its "likely cards".
// ============================================================

import { watchUser } from "./firebase.js";
import { loadMatches, loadSightings } from "./database.js";

const pageStatus   = document.getElementById("page-status");
const playerSearch = document.getElementById("player-search");
const listBox      = document.getElementById("player-list");

let players = [];     // one entry per player, see buildPlayers()


// ---------- 1. FROM MATCHES TO PLAYERS ----------
// Python equivalent: a dict  name.lower() -> {"name", "seen": [appearances...]}
// Each match counts once per player, even if several people shared it.
function buildPlayers(matches, sightings) {
  const all = {};                       // "<game id>|<name>" -> appearance
  for (const match of matches) {
    for (const a of appearances(match)) {
      all[match.gameId + "|" + a.name.toLowerCase()] = a;
    }
  }
  for (const s of sightings) {
    const id = s.gameId + "|" + (s.name || "").toLowerCase();
    const cardsSeen = Object.values(s.cards || {}).reduce(function (sum, n) { return sum + n; }, 0);
    const tooLittle = !(s.classes || []).length && cardsSeen < 2;     // unknown classes, almost nothing seen
    if (s.name && !all[id] && !tooLittle) {
      // shared by someone else: no result, not "mine"
      all[id] = { name: s.name, classes: s.classes || [], cards: s.cards || {}, generated: {},
                  shared: true, match: { gameId: s.gameId, playedAt: s.playedAt || 0, spectated: true } };
    }
  }
  // My own names (from my matches): others share me as their opponent, but I don't need my own page
  const myNames = new Set(matches.filter(function (m) { return m.myName; })
    .map(function (m) { return m.myName.toLowerCase(); }));

  const byName = {};
  for (const a of Object.values(all)) {
    const key = a.name.toLowerCase();
    if (myNames.has(key)) {
      continue;
    }
    byName[key] = byName[key] || { name: a.name, seen: [] };
    byName[key].seen.push(a);
  }
  return Object.values(byName).map(function (p) {
    p.seen.sort(function (a, b) { return b.match.playedAt - a.match.playedAt; });   // newest first
    p.name = p.seen[0].name;                       // the newest spelling of the name
    p.lastSeen = p.seen[0].match.playedAt;
    const mine = p.seen.filter(function (a) { return !a.match.spectated; });
    p.wins = mine.filter(function (a) { return a.match.result === "win"; }).length;
    p.losses = mine.filter(function (a) { return a.match.result === "loss"; }).length;
    p.shared = p.seen.filter(function (a) { return a.shared; }).length;     // seen by other people
    p.watched = p.seen.length - mine.length - p.shared;                       // matches I watched
    return p;
  }).sort(function (a, b) { return b.seen.length - a.seen.length || b.lastSeen - a.lastSeen; });
}

// For one player and one class pair: each card with the % of matches it was played in.
// (Same as predict() in profiles.py.) Generated cards are left out: not part of the deck.
function likelyCards(seen) {
  const count = {}, most = {};
  for (const a of seen) {
    for (const [id, n] of Object.entries(a.cards)) {
      if (n > 0) {
        count[id] = (count[id] || 0) + 1;
        most[id] = Math.max(most[id] || 0, n);
      }
    }
  }
  return Object.keys(count).map(function (id) {
    return { card: findCard(id), seen: count[id], percent: Math.round((100 * count[id]) / seen.length), most: most[id] };
  });
}


// ---------- 2. DRAWING ----------

function render() {
  const text = playerSearch.value.trim().toLowerCase();
  const shown = players.filter(function (p) { return p.name.toLowerCase().includes(text); });
  listBox.innerHTML = "";
  if (players.length === 0) {
    listBox.innerHTML = `<p class="page-status">No players yet. Play or spectate a match with the tracker running.</p>`;
    return;
  }
  if (shown.length === 0) {
    listBox.innerHTML = `<p class="page-status">No player with that name.</p>`;
    return;
  }
  for (const p of shown) {
    listBox.appendChild(createRow(p));
  }
}

function createRow(p) {
  const row = document.createElement("div");
  row.className = "match-row player-row";

  // Class pairs used, most used first: "Protector / Rebel ×3"
  const pairs = {};
  for (const a of p.seen) {
    const key = classKey(a.classes);
    pairs[key] = (pairs[key] || 0) + 1;
  }
  const pairTags = Object.entries(pairs).sort(function (a, b) { return b[1] - a[1]; })
    .map(function ([key, n]) {
      return `<span class="pair-tag">${classTags(key.split(" / "))}<span class="dim small">×${n}</span></span>`;
    }).join("");

  const record = p.wins + p.losses > 0
    ? `<span style="color: var(--win)">${p.wins}W</span> <span style="color: var(--loss)">${p.losses}L</span>`
    : `<span class="dim">never played</span>`;

  row.innerHTML = `
    <div class="match-main player-main">
      <span class="match-name">${escapeHtml(p.name)}</span>
      <span class="small">${pairTags}</span>
      <span class="small" title="My record against them">${record}${p.watched ? ` <span class="dim">· watched ${p.watched}</span>` : ""}${p.shared ? ` <span class="dim" title="Matches other players' trackers shared">· +${p.shared} shared</span>` : ""}</span>
      <span class="match-date dim small">${formatDate(p.lastSeen)}</span>
    </div>
    <div class="match-details hidden"></div>
  `;
  const details = row.querySelector(".match-details");
  row.querySelector(".match-main").addEventListener("click", function () {
    if (details.innerHTML === "") {
      details.innerHTML = detailsHtml(p);
    }
    details.classList.toggle("hidden");
  });
  return row;
}

// One block per class pair, most used first
function detailsHtml(p) {
  const groups = {};
  for (const a of p.seen) {
    (groups[classKey(a.classes)] = groups[classKey(a.classes)] || []).push(a);
  }
  return Object.entries(groups).sort(function (a, b) { return b[1].length - a[1].length; })
    .map(function ([key, seen]) {
      const cards = likelyCards(seen).sort(function (a, b) {
        return STAGES.indexOf(a.card.type) - STAGES.indexOf(b.card.type) || b.percent - a.percent || a.card.name.localeCompare(b.card.name);
      });
      const n = seen.length;
      return `
        <div class="pair-block">
          <p class="details-title">${classTags(key.split(" / "))} ${n} match${n === 1 ? "" : "es"} · last ${formatDate(seen[0].match.playedAt)}</p>
          <p class="guess-note">Likely cards, <b>not their decklist</b>: % = in how many of these ${n} matches they played it
            (yours and shared by other players). We only see played cards, so cards they run can still show a low %.</p>
          <div class="card-list">${cards.map(function (c) { return cardBar(c.card, c.percent + "%", "guess"); }).join("")
            || `<p class="dim small">No cards seen yet</p>`}</div>
        </div>`;
    }).join("");
}


// ---------- 3. START ----------
playerSearch.addEventListener("input", render);

watchUser(async function (user) {
  if (!user) {
    players = [];
    listBox.innerHTML = "";
    pageStatus.textContent = "Sign in (top menu) to see the players you've met.";
    return;
  }
  pageStatus.textContent = "Loading your matches...";
  try {
    const matches = await loadMatches();
    let sightings = [];
    try {
      sightings = await loadSightings();
      pageStatus.textContent = "";
    } catch (error) {
      // e.g. the database rules don't allow shared data yet: show my own players only
      pageStatus.textContent = "Shared player data couldn't be loaded (" + error.code + "): showing your own matches only.";
      console.error(error);
    }
    players = buildPlayers(matches, sightings);
    render();
  } catch (error) {
    pageStatus.textContent = "Couldn't load your matches: " + error.message;
    console.error(error);
  }
});
