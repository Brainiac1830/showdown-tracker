// ============================================================
// card-stats.js — the Cards page: win rate when a card was played.
//
//   Per hand: of the hands where the card was played, how many did that player win?
//             (+ average chip swing: that player's chips minus the opponent's, that hand)
//   Per game: of the matches where the card was played at least once, how many did they win?
//
//   My plays: only my cards, in my matches (filter by deck and deck version)
//   Everyone: every player in my matches and the matches I watched (much more data)
//
// It's what happened when a card was played, not proof the card caused it: you may play
// some cards when you're already ahead. "vs avg" compares to the overall win rate.
// Generated cards (made during the match) are left out unless "+ Generated" is on:
// some only come after winning (Prototype, Card Protector), which would flatter them.
// With it on, the ✦ number says how many of a card's hands/games were generated copies.
// Uses each match's handLog (saved by the tracker since 2026-10-25; older matches get it
// with  python website.py --upload-all --replace).
// ============================================================

import { watchUser } from "./firebase.js";
import { loadMatches } from "./database.js";

const MIN_SAMPLES = 20;      // fewer than this = "low data" (greyed out)

const pageStatus = document.getElementById("page-status");
const deckFilter = document.getElementById("deck-filter");
const sortBy     = document.getElementById("sort-by");
const baselineBox = document.getElementById("baseline");
const explainBox = document.getElementById("explain");
const table      = document.getElementById("card-table");

let matches = [];
let mode = "hand";           // "hand" or "game"
let scope = "me";            // "me" or "all"
let withGenerated = false;   // count generated copies too
const hideBots = setupHideBots("hide-bots", function () { render(); });
let versions = {};           // match id -> "Theory Craft v2"


// ---------- 1. DECK VERSIONS ----------
// Same deck name + a different card list = a new version, numbered in the order first played.
function buildVersions() {
  versions = {};
  const byName = {};
  const mine = matches.filter(function (m) { return !m.spectated; })
    .sort(function (a, b) { return a.playedAt - b.playedAt; });
  for (const m of mine) {
    const name = m.deckName || "(unknown deck)";
    const list = m.deckCards && Object.keys(m.deckCards).length
      ? JSON.stringify(Object.entries(m.deckCards).sort())     // the exact list, as text
      : null;
    byName[name] = byName[name] || [];
    let v = list ? byName[name].indexOf(list) : -1;
    if (list && v === -1) {
      byName[name].push(list);
      v = byName[name].length - 1;
    }
    versions[m.id] = list ? `${name} v${v + 1}` : `${name} (version unknown)`;
  }
  // Fill the deck menu: all decks, then each deck (all versions), then each version
  const options = [`<option value="all">All my decks</option>`];
  for (const name of Object.keys(byName).sort()) {
    options.push(`<option value="name:${escapeHtml(name)}">${escapeHtml(name)} (all versions)</option>`);
    const count = byName[name].length;
    for (let v = 1; v <= count; v++) {
      const label = `${name} v${v}` + (v === count ? " (current)" : "");
      options.push(`<option value="version:${escapeHtml(name)} v${v}">&nbsp;&nbsp;${escapeHtml(label)}</option>`);
    }
  }
  deckFilter.innerHTML = options.join("");
}

function deckOk(match) {
  const choice = deckFilter.value || "all";
  if (choice === "all" || scope === "all") {
    return true;
  }
  if (match.spectated) {
    return false;
  }
  if (choice.startsWith("name:")) {
    return (match.deckName || "(unknown deck)") === choice.slice(5);
  }
  return versions[match.id] === choice.slice(8);
}


// ---------- 2. SAMPLES: one per player per hand (or per match) ----------
// Each sample: { cards: {card id: n}, won: true/false, swing: chips difference (hands only) }

function playersOf(match) {
  // pid -> did this player win the match? (null = unknown, e.g. left early)
  if (match.spectated) {
    const names = (match.players || []).map(function (p) { return p.name; });
    const winner = match.winner;
    return {
      P1: winner && !match.leftEarly ? names[0] === winner : null,
      P2: winner && !match.leftEarly ? names[1] === winner : null,
      cards: { P1: (match.players[0] || {}).cards || {}, P2: (match.players[1] || {}).cards || {} },
      generated: { P1: (match.players[0] || {}).generated || {}, P2: (match.players[1] || {}).generated || {} },
    };
  }
  const me = match.me || "P1";
  const opp = me === "P1" ? "P2" : "P1";
  const result = match.result === "win" ? true : match.result === "loss" ? false : null;
  const out = { cards: {}, generated: {} };
  out[me] = result;
  out[opp] = result === null ? null : !result;
  out.cards[me] = match.myCards || {};
  out.cards[opp] = match.opponentCards || {};
  out.generated[me] = match.myGenerated || {};
  out.generated[opp] = match.opponentGenerated || {};
  return out;
}

function samples() {
  const list = [];
  for (const m of matches) {
    if (!deckOk(m) || (hideBots() && isBotMatch(m))) {
      continue;
    }
    // whose plays count: me only, or everyone
    let pids;
    if (scope === "me") {
      if (m.spectated) {
        continue;
      }
      pids = [m.me || "P1"];
    } else {
      pids = ["P1", "P2"];
    }
    if (mode === "hand") {
      for (const h of m.handLog || []) {
        for (const pid of pids) {
          const other = pid === "P1" ? "P2" : "P1";
          list.push({
            cards: (h.cards || {})[pid] || {},
            generated: (h.generated || {})[pid] || {},
            won: h.winner === pid,
            swing: h.chips ? (h.chips[pid] || 0) - (h.chips[other] || 0) : null,
          });
        }
      }
    } else {
      const info = playersOf(m);
      for (const pid of pids) {
        if (info[pid] === null || info[pid] === undefined) {
          continue;           // no result (left early): can't count for "per game"
        }
        list.push({ cards: info.cards[pid] || {}, generated: info.generated[pid] || {}, won: info[pid], swing: null });
      }
    }
  }
  return list;
}


// ---------- 3. DRAWING ----------

function render() {
  const all = samples();
  const unit = mode === "hand" ? "hand" : "game";
  const wins = all.filter(function (s) { return s.won; }).length;
  const base = all.length ? (100 * wins) / all.length : 0;
  const who = scope === "me" ? "You" : "Players";
  baselineBox.innerHTML = all.length
    ? `Average: ${who} won <b>${Math.round(base)}%</b> of ${all.length} ${unit}s`
    : "";
  explainBox.textContent = all.length
    ? `Win rate when the card was played at least once in the ${unit}` +
      (withGenerated ? " (generated copies included: ✦ = how many of those had one)" : " (deck cards only, generated copies left out)") +
      `. Rows with fewer than ${MIN_SAMPLES} ${unit}s are greyed out: too little data to trust.` +
      (mode === "hand" ? " Chips = average chip swing in those hands (their chips minus the opponent's)." : "")
    : "";

  if (all.length === 0) {
    table.innerHTML = `<tr><td class="page-status">No ${unit} data yet for this choice.` +
      (mode === "hand" ? " Older matches get hand data with: python website.py --upload-all --replace" : "") + "</td></tr>";
    return;
  }

  // Add up per card
  const stats = {};
  for (const s of all) {
    const fromDeck = Object.keys(s.cards);
    const made = withGenerated ? Object.keys(s.generated || {}) : [];
    for (const id of new Set(fromDeck.concat(made))) {
      const st = stats[id] = stats[id] || { n: 0, gen: 0, wins: 0, swing: 0, swingN: 0 };
      st.n += 1;
      if (made.includes(id)) {
        st.gen += 1;
      }
      st.wins += s.won ? 1 : 0;
      if (s.swing !== null) {
        st.swing += s.swing;
        st.swingN += 1;
      }
    }
  }
  const rows = Object.entries(stats).map(function ([id, st]) {
    const rate = (100 * st.wins) / st.n;
    return { card: findCard(id), n: st.n, gen: st.gen, wins: st.wins, rate: rate, diff: rate - base,
             swing: st.swingN ? st.swing / st.swingN : null };
  }).sort(function (a, b) {
    if (sortBy.value === "rate") return b.rate - a.rate || b.n - a.n;
    if (sortBy.value === "diff") return b.diff - a.diff || b.n - a.n;
    return b.n - a.n || b.rate - a.rate;
  });

  table.innerHTML = `
    <tr><th>Card</th><th class="num">${unit === "hand" ? "Hands" : "Games"}</th><th class="num">Won</th>
      <th class="num">Win rate</th><th class="num">vs avg</th>${mode === "hand" ? `<th class="num">Chips</th>` : ""}</tr>
    ${rows.map(function (r) {
      const low = r.n < MIN_SAMPLES;
      const diff = Math.round(r.diff);
      const diffText = (diff > 0 ? "+" : "") + diff;
      const diffColour = low ? "" : diff >= 5 ? "color: var(--win)" : diff <= -5 ? "color: var(--loss)" : "";
      const swing = r.swing === null ? "" : (r.swing > 0 ? "+" : "") + r.swing.toFixed(1);
      return `<tr class="${low ? "low-data" : ""}" title="${low ? "Low data: " : ""}${r.wins} won of ${r.n}">
        <td class="card-cell">${cardBar(r.card, r.n, "")}</td>
        <td class="num">${r.n}${r.gen ? ` <span class="spark" title="${r.gen} with a generated copy">✦${r.gen}</span>` : ""}</td>
        <td class="num">${r.wins}</td>
        <td class="num"><span class="rate">${Math.round(r.rate)}%
          <span class="rate-bar"><span class="rate-fill" style="display:block; width: ${r.rate}%"></span></span></span></td>
        <td class="num" style="${diffColour}">${diffText}</td>
        ${mode === "hand" ? `<td class="num">${swing}</td>` : ""}
      </tr>`;
    }).join("")}`;
}

// The two toggles: [Per hand | Per game] and [My plays | Everyone]
function setupToggle(id, onChange) {
  const box = document.getElementById(id);
  box.addEventListener("click", function (event) {
    const button = event.target.closest("button");
    if (!button) {
      return;
    }
    box.querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", b === button); });
    onChange(button.dataset.value);
    render();
  });
}
setupToggle("mode-toggle", function (value) { mode = value; });
setupToggle("gen-toggle", function (value) { withGenerated = value === "on"; });
setupToggle("scope-toggle", function (value) {
  scope = value;
  deckFilter.disabled = value === "all";      // decks are only mine
});
deckFilter.addEventListener("change", render);
sortBy.addEventListener("change", render);


// ---------- 4. START ----------
watchUser(async function (user) {
  if (!user) {
    matches = [];
    table.innerHTML = "";
    baselineBox.innerHTML = "";
    pageStatus.textContent = "Sign in (top menu) to see your card stats.";
    return;
  }
  pageStatus.textContent = "Loading your matches...";
  try {
    matches = await loadMatches();
    pageStatus.textContent = "";
    buildVersions();
    render();
  } catch (error) {
    pageStatus.textContent = "Couldn't load your matches: " + error.message;
    console.error(error);
  }
});
