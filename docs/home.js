// ============================================================
// home.js — the Home page: your overall stats.
//   - tiles: matches, record, win rate, last 10 matches
//   - win rate for each of my decks
//   - win rate against each opponent class pair (e.g. Rebel / Gambler)
//   - the opponent cards I run into most
// ============================================================

import { watchUser } from "./firebase.js";
import { loadMatches } from "./database.js";

const pageStatus = document.getElementById("page-status");
const content    = document.getElementById("home-content");
const tiles      = document.getElementById("stat-tiles");
const deckTable  = document.getElementById("deck-table");
const classTable = document.getElementById("class-table");
const seenCards  = document.getElementById("seen-cards");


// ---------- Helpers ----------

// Wins, losses and win rate of a list of matches
function record(matches) {
  const wins = matches.filter(function (m) { return m.result === "win"; }).length;
  const losses = matches.filter(function (m) { return m.result === "loss"; }).length;
  const rate = wins + losses > 0 ? Math.round((wins / (wins + losses)) * 100) : 0;
  return { wins: wins, losses: losses, rate: rate };
}

// Put matches in groups. keyOf(match) gives the group name.
// Python equivalent: groups = defaultdict(list); groups[key_of(m)].append(m)
function groupBy(matches, keyOf) {
  const groups = {};
  for (const m of matches) {
    const key = keyOf(m);
    (groups[key] = groups[key] || []).push(m);
  }
  return groups;
}

function rateCell(r) {
  return `<td class="num"><span class="rate">${r.rate}%
    <span class="rate-bar"><span class="rate-fill" style="display:block; width: ${r.rate}%"></span></span></span></td>`;
}

// A table: one line per group, most played first
function statsTable(table, groups, firstColumn, firstHeader) {
  const rows = Object.entries(groups).sort(function (a, b) { return b[1].length - a[1].length; });
  table.innerHTML = `
    <tr><th>${firstHeader}</th><th class="num">Played</th><th class="num">W – L</th><th class="num">Win rate</th></tr>
    ${rows.map(function ([key, list]) {
      const r = record(list);
      return `<tr><td>${firstColumn(key, list)}</td><td class="num">${list.length}</td>
        <td class="num"><span style="color: var(--win)">${r.wins}</span> – <span style="color: var(--loss)">${r.losses}</span></td>
        ${rateCell(r)}</tr>`;
    }).join("")}`;
}


// ---------- Drawing ----------
function render(matches) {
  const all = record(matches);
  const last10 = record([...matches].sort(function (a, b) { return b.playedAt - a.playedAt; }).slice(0, 10));
  tiles.innerHTML = `
    <div class="stat-tile"><div class="stat-value">${matches.length}</div><div class="stat-label">Matches</div></div>
    <div class="stat-tile"><div class="stat-value"><span class="w">${all.wins}</span> – <span class="l">${all.losses}</span></div><div class="stat-label">Record</div></div>
    <div class="stat-tile"><div class="stat-value">${all.rate}%</div><div class="stat-label">Win rate</div></div>
    <div class="stat-tile"><div class="stat-value">${last10.rate}%</div><div class="stat-label">Last 10 matches</div></div>`;

  // My decks (with their classes)
  statsTable(deckTable, groupBy(matches, function (m) { return m.deckName || "(unknown deck)"; }),
    function (name, list) { return `<b>${escapeHtml(name)}</b> ${classTags(list[0].myClasses)}`; }, "Deck");

  // Opponent class pairs, e.g. "Gambler / Rebel" (sorted so the order doesn't matter)
  statsTable(classTable,
    groupBy(matches, function (m) { return [...(m.opponentClasses || [])].sort().join(" / ") || "?"; }),
    function (key) { return classTags(key.split(" / ")); }, "Opponent classes");

  // Opponent cards: in how many matches each was played (deck or generated)
  const seen = {};
  for (const m of matches) {
    const ids = new Set(Object.keys(m.opponentCards || {}).concat(Object.keys(m.opponentGenerated || {})));
    for (const id of ids) {
      seen[id] = (seen[id] || 0) + 1;
    }
  }
  const top = Object.entries(seen).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 12);
  seenCards.innerHTML = top.length
    ? top.map(function ([id, n]) { return cardBar(findCard(id), n, ""); }).join("")
    : `<p class="dim small">None yet</p>`;
}


// ---------- Start ----------
watchUser(async function (user) {
  if (!user) {
    content.classList.add("hidden");
    pageStatus.textContent = "Sign in (top menu) to see your stats.";
    return;
  }
  pageStatus.textContent = "Loading your matches...";
  try {
    // Spectated matches are other people's games: they're on the Players page, not in my stats
    const matches = (await loadMatches()).filter(function (m) { return !m.spectated; });
    if (matches.length === 0) {
      pageStatus.textContent = "No matches yet. Play a match with the tracker running and your stats appear here.";
      return;
    }
    pageStatus.textContent = "";
    render(matches);
    content.classList.remove("hidden");
  } catch (error) {
    pageStatus.textContent = "Couldn't load your matches: " + error.message;
    console.error(error);
  }
});
