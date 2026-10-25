// ============================================================
// match-history.js — the Match History page.
// Every match, newest first: result, my deck, opponent, final chips, date.
// Click a match to see each hand and the cards both of you played
// (coloured by stage like the overlay, ✦ = generated during the match).
// ============================================================

import { watchUser } from "./firebase.js";
import { loadMatches, deleteMatch } from "./database.js";


// ---------- 1. PAGE PARTS AND DATA ----------
const pageStatus   = document.getElementById("page-status");
const playerSearch = document.getElementById("player-search");
const deckFilter   = document.getElementById("deck-filter");
const resultFilter = document.getElementById("result-filter");
const summaryBox   = document.getElementById("history-summary");
const listBox      = document.getElementById("history-list");

let allMatches = [];


// ---------- 2. FILTERS ----------

// Fill the deck list with the decks found in your matches
function fillDeckFilter() {
  const mine = allMatches.filter(function (m) { return !m.spectated; });
  const names = [...new Set(mine.map(function (m) { return m.deckName || "(unknown deck)"; }))].sort();
  deckFilter.innerHTML = `<option value="all">All my decks</option>` +
    names.map(function (n) { return `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`; }).join("");
}

// The matches that pass the 3 filters, newest first
function filteredMatches() {
  const text = playerSearch.value.trim().toLowerCase();
  return allMatches
    .filter(function (m) {
      // a player's name: the opponent, or either player in a watched match
      const names = appearances(m).map(function (a) { return a.name.toLowerCase(); });
      const playerOk = names.some(function (n) { return n.includes(text); });
      // "My matches" = everything I played; watched matches only under their own choice
      const resultOk = resultFilter.value === "all" ? !m.spectated : m.result === resultFilter.value;
      const deckOk = m.spectated || deckFilter.value === "all" || (m.deckName || "(unknown deck)") === deckFilter.value;
      return playerOk && deckOk && resultOk;
    })
    .sort(function (a, b) { return b.playedAt - a.playedAt; });
}

// "12 matches · 7W 5L · 58% win rate"
function renderSummary(matches) {
  if (allMatches.length === 0) {
    summaryBox.innerHTML = "";
    return;
  }
  if (resultFilter.value === "spectated") {
    summaryBox.innerHTML = `<b>${matches.length}</b> watched match${matches.length === 1 ? "" : "es"}`;
    return;
  }
  const wins = matches.filter(function (m) { return m.result === "win"; }).length;
  const losses = matches.filter(function (m) { return m.result === "loss"; }).length;
  const rate = wins + losses > 0 ? Math.round((wins / (wins + losses)) * 100) : 0;
  const total = allMatches.filter(function (m) { return !m.spectated; }).length;
  const filtered = matches.length !== total;
  summaryBox.innerHTML = `
    <b>${matches.length}</b> match${matches.length === 1 ? "" : "es"}${filtered ? ` (of ${total})` : ""}
    · <span class="w">${wins}W</span> <span class="l">${losses}L</span>
    · <b>${rate}%</b> win rate`;
}


// ---------- 3. THE LIST ----------

function render() {
  const matches = filteredMatches();
  renderSummary(matches);
  listBox.innerHTML = "";
  if (allMatches.length === 0) {
    listBox.innerHTML = `<p class="page-status">No matches yet. Play a match with the tracker running and it appears here.</p>`;
    return;
  }
  if (matches.length === 0) {
    listBox.innerHTML = `<p class="page-status">No matches for these filters.</p>`;
    return;
  }
  for (const match of matches) {
    listBox.appendChild(createRow(match));
  }
}

function createRow(match) {
  const row = document.createElement("div");
  row.className = "match-row result-" + match.result;

  if (match.spectated) {
    // A match I watched: player 1 vs player 2, the winner in green
    const [p1, p2] = match.players || [{}, {}];
    const nameHtml = function (p) {
      const won = p.name && p.name === match.winner;
      return `<span class="match-name" style="${won ? "color: var(--win)" : ""}">${escapeHtml(p.name || "?")}${won ? " ★" : ""}</span>`;
    };
    row.innerHTML = `
      <div class="match-main">
        <span class="match-result">${RESULT_WORDS.spectated}</span>
        <span class="match-deck">${nameHtml(p1)}<br>${classTags(p1.classes)}</span>
        <span class="match-enemy"><span class="dim small">vs</span> ${nameHtml(p2)}<br>${classTags(p2.classes)}</span>
        <span class="match-score" title="Final chips">${p1.chips ?? "?"} – ${p2.chips ?? "?"}</span>
        <span class="match-date dim small">${formatDate(match.playedAt)}</span>
      </div>
      <div class="match-details hidden"></div>
    `;
  } else {
    row.innerHTML = `
      <div class="match-main">
        <span class="match-result">${RESULT_WORDS[match.result] || "?"}</span>
        <span class="match-deck">
          <span class="match-name">${escapeHtml(match.deckName || "(unknown deck)")}</span><br>
          ${classTags(match.myClasses)}
        </span>
        <span class="match-enemy">
          <span class="dim small">vs</span> <span class="match-name">${escapeHtml(match.opponent)}</span><br>
          ${classTags(match.opponentClasses)}
        </span>
        <span class="match-score" title="Final chips: you – opponent">${match.myChips ?? "?"} – ${match.opponentChips ?? "?"}</span>
        <span class="match-date dim small">${formatDate(match.playedAt)}</span>
      </div>
      <div class="match-details hidden"></div>
    `;
  }

  const details = row.querySelector(".match-details");
  row.querySelector(".match-main").addEventListener("click", function () {
    if (details.innerHTML === "") {
      details.innerHTML = detailsHtml(match);         // only built when first opened
      details.querySelector('[data-action="delete"]').addEventListener("click", function () {
        removeMatch(match);
      });
    }
    details.classList.toggle("hidden");
  });
  return row;
}

// The inside of an opened watched match: both players' cards
function spectatedDetailsHtml(match) {
  const hands = (match.hands || []).map(function (h) {
    const how = h.p1Hand || h.p2Hand
      ? `${escapeHtml(h.p1Hand || "?")} vs ${escapeHtml(h.p2Hand || "?")}`
      : `<span class="dim">by fold</span>`;
    return `<p class="hand-line">${escapeHtml(h.hand)}: ${escapeHtml(h.winner)} · ${how}</p>`;
  }).join("") || `<p class="dim small">No hands recorded</p>`;
  const column = function (p) {
    return `<div>
        <p class="details-title">${escapeHtml(p.name || "?")} played</p>
        <div class="card-list">${cardBars(p.cards, [[p.generated || {}, "generated"]])}</div>
      </div>`;
  };
  const [p1, p2] = match.players || [{}, {}];
  return `
    <p class="details-title">Hands (from when I started watching)</p>
    ${hands}
    <div class="details-columns" style="margin-top: 12px">${column(p1)}${column(p2)}</div>
    <div class="details-footer">
      <span class="dim small">✦ generated during the match</span>
      <button class="btn btn-danger" data-action="delete">Delete</button>
    </div>`;
}

// The inside of an opened match
function detailsHtml(match) {
  if (match.spectated) {
    return spectatedDetailsHtml(match);
  }
  const hands = (match.hands || []).map(function (h) {
    const won = h.won === "me" ? `<span class="w">Won</span>` : h.won === "opponent" ? `<span class="l">Lost</span>` : "Split";
    // No poker hands shown = someone folded before the showdown
    const how = h.myHand || h.opponentHand
      ? `${escapeHtml(h.myHand || "?")} vs ${escapeHtml(h.opponentHand || "?")}`
      : `<span class="dim">by fold</span>`;
    return `<p class="hand-line">${escapeHtml(h.hand)}: ${won} · ${how}</p>`;
  }).join("") || `<p class="dim small">No hands recorded</p>`;

  const start = (match.startingHand || []).map(function (id) { return escapeHtml(findCard(id).name); }).join(", ");

  return `
    <div class="details-columns">
      <div>
        <p class="details-title">Hands</p>
        ${hands}
        <p class="details-title" style="margin-top: 12px">Starting hand</p>
        <p class="small">${start || `<span class="dim">Not recorded</span>`}</p>
        <p class="details-title" style="margin-top: 12px">I played</p>
        <div class="card-list">${cardBars(match.myCards)}</div>
      </div>
      <div>
        <p class="details-title">${escapeHtml(match.opponent)} played</p>
        <div class="card-list">${cardBars(match.opponentCards, [[match.opponentGenerated || {}, "generated"]])}</div>
      </div>
    </div>
    <div class="details-footer">
      <span class="dim small">✦ generated during the match</span>
      <button class="btn btn-danger" data-action="delete">Delete</button>
    </div>`;
}

async function removeMatch(match) {
  const who = appearances(match).map(function (a) { return a.name; }).join(" vs ");
  if (!confirm(`Delete this match (${RESULT_WORDS[match.result]}: ${who}, ${formatDate(match.playedAt)})? This can't be undone.`)) {
    return;
  }
  try {
    await deleteMatch(match.id);
    allMatches = allMatches.filter(function (m) { return m.id !== match.id; });
    render();
  } catch (error) {
    alert("Couldn't delete the match: " + error.message);
  }
}


// ---------- 4. START ----------
playerSearch.addEventListener("input", render);     // filter on every key you type
deckFilter.addEventListener("change", render);
resultFilter.addEventListener("change", render);

watchUser(async function (user) {
  if (!user) {
    allMatches = [];
    listBox.innerHTML = "";
    summaryBox.innerHTML = "";
    pageStatus.textContent = "Sign in (top menu) to see your matches.";
    return;
  }
  pageStatus.textContent = "Loading your matches...";
  try {
    allMatches = await loadMatches();
    pageStatus.textContent = "";
    fillDeckFilter();
    render();
  } catch (error) {
    pageStatus.textContent = "Couldn't load your matches: " + error.message;
    console.error(error);
  }
});
