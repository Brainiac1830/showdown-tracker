// ============================================================
// common.js — small helpers used by every page.
// A normal script (not a module), so its functions are available everywhere,
// like CARDS from cards.js.
// ============================================================

// The four stages, in the order we show them (the game calls Universal "Any")
const STAGES = ["Any", "PreFlop", "Flop", "River"];
const STAGE_NAMES = { Any: "Universal", PreFlop: "Pre-flop", Flop: "Flop", River: "River" };

const RESULT_WORDS = { win: "Win", loss: "Loss", spectated: "Watched", unknown: "?" };


// Text from the database can contain < or &; this makes it safe to put in the page
function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// Find a card by id. Unknown ids (a new card) get a stand-in so nothing breaks.
// Python equivalent: BY_ID.get(card_id) or {...}
const CARDS_BY_ID = Object.fromEntries(CARDS.map(function (c) { return [c.id, c]; }));
function findCard(id) {
  return CARDS_BY_ID[id] || { id: id, name: id, type: "Any", chips: 0, rarity: "", class: "", text: "", art: "" };
}

// +2 / 0 / -1
function scoreText(chips) {
  return chips > 0 ? "+" + chips : String(chips);
}

// Short date like "24 Oct, 10:50 pm"
function formatDate(ms) {
  return new Date(ms).toLocaleString("en-CA", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

// "Rebel / Inventor" as two small coloured tags
function classTags(classes) {
  return (classes || []).map(function (c) {
    return `<span class="class-tag class-${escapeHtml(c.toLowerCase())}">${escapeHtml(c)}</span>`;
  }).join("");
}


// ---------- Ranks (same as ranks.py) ----------
// 0-9 Bronze, 10-19 Silver, 20-29 Gold, 30-39 Diamond (stars = number - start), 40 Elite.
// Bots: the game sends their rank as the text "0" (saved as bot: true).
const RANK_TIERS = [[0, "Bronze", "#be7850"], [10, "Silver", "#bec6cd"], [20, "Gold", "#d7b446"],
                    [30, "Diamond", "#aa82e6"], [40, "Elite", "#96dceb"]];

function rankBadge(rank, bot) {
  if (bot) {
    return `<span class="rank-badge bot" title="A bot (its rank is sent as text &quot;0&quot;)">BOT</span>`;
  }
  if (typeof rank !== "number") {
    return "";
  }
  for (let i = RANK_TIERS.length - 1; i >= 0; i--) {
    const [start, name, colour] = RANK_TIERS[i];
    if (rank >= start) {
      const text = name === "Elite" ? "Elite" : `${name} ${rank - start}★`;
      return `<span class="rank-badge" style="color: ${colour}; border-color: ${colour}">${text}</span>`;
    }
  }
  return "";
}

// A match against a bot (watched matches: either player is a bot)
function isBotMatch(match) {
  return match.spectated
    ? (match.players || []).some(function (p) { return p.bot; })
    : !!match.opponentBot;
}

// The "Hide bot matches" switch: on by default, remembered in this browser.
// setupHideBots("hide-bots", render) wires a checkbox and returns a function giving its state.
function setupHideBots(checkboxId, onChange) {
  const box = document.getElementById(checkboxId);
  let saved = null;
  try { saved = localStorage.getItem("showdown-hide-bots"); } catch (e) { /* blocked: default */ }
  box.checked = saved !== "no";
  box.addEventListener("change", function () {
    try { localStorage.setItem("showdown-hide-bots", box.checked ? "yes" : "no"); } catch (e) { /* fine */ }
    onChange();
  });
  return function () { return box.checked; };
}


// ---------- Players seen in a match (same idea as profiles.py) ----------

// "Protector / Rebel": classes sorted, so the order doesn't matter
function classKey(classes) {
  return [...(classes || [])].sort().join(" / ") || "?";
}

// The players whose cards we saw in one match: the opponent in my own matches,
// both players in a spectated one. Each: { name, classes, cards, generated, match }
function appearances(match) {
  const players = match.spectated
    ? (match.players || [])
    : [{ name: match.opponent, classes: match.opponentClasses, cards: match.opponentCards,
         generated: match.opponentGenerated, discarded: match.opponentDiscarded,
         rank: match.opponentRank, bot: match.opponentBot }];
  return players
    // no name yet, or unknown classes with almost nothing seen (left right away): not worth showing
    .filter(function (p) {
      const cardsSeen = Object.values(p.cards || {}).reduce(function (sum, n) { return sum + n; }, 0);
      return p.name && !["?", "P1", "P2"].includes(p.name) && ((p.classes || []).length > 0 || cardsSeen >= 2);
    })
    .map(function (p) {
      // cards = every deck card SEEN from them: played + discarded (both are in their deck)
      const seen = Object.assign({}, p.cards || {});
      for (const [id, n] of Object.entries(p.discarded || {})) {
        seen[id] = (seen[id] || 0) + n;
      }
      return { name: p.name, classes: p.classes || [], cards: seen, generated: p.generated || {}, match: match,
               rank: p.rank, bot: !!p.bot };
    });
}


// ---------- Card bars (same look as the tracker overlay) ----------
// One bar: stage stripe, chip score badge, name, card art faded in, count.
// kind: "" (normal), "generated" (✦) or "guess" (a likely card: dashed, % in the box)
function cardBar(card, count, kind) {
  const mark = kind === "generated" ? `<span class="spark">✦</span>` : "";
  const art = card.art ? `style="--art: url('${card.art}')"` : "";
  return `
    <div class="card-bar stage-${card.type} ${kind || ""}" ${art}
         title="${escapeHtml(card.name)} · ${STAGE_NAMES[card.type] || ""} · ${escapeHtml(card.class || "")}&#10;${escapeHtml(card.text || "")}">
      <span class="card-score">${scoreText(card.chips)}</span>
      <span class="card-name">${mark}${escapeHtml(card.name)}</span>
      <span class="card-count">${count}</span>
    </div>`;
}

// A whole list of card bars from {card id: times}, sorted by stage then chip score.
// extra = more {card id: times} lists with their kind, e.g. [[opponentGenerated, "generated"]]
function cardBars(counts, extra) {
  const groups = [[counts || {}, ""]].concat(extra || []);
  let html = "";
  for (const [list, kind] of groups) {
    const cards = Object.entries(list)
      .filter(function ([id, n]) { return n > 0; })
      .map(function ([id, n]) { return [findCard(id), n]; })
      .sort(function ([a], [b]) {
        return STAGES.indexOf(a.type) - STAGES.indexOf(b.type) || a.chips - b.chips || a.name.localeCompare(b.name);
      });
    for (const [card, n] of cards) {
      html += cardBar(card, n, kind);
    }
  }
  return html || `<p class="dim small">None</p>`;
}
