// ============================================================
// database.js — reading and deleting Showdown matches in Firestore.
//
// Where they live (in the same Firebase project as the Origins site):
//
//   users/<your id>/showdown_matches/<game id>   one document per match
//   users/<your id>/meta/lastChange              field "showdownMatches" = when they last changed
//
// The tracker (website.py) saves the matches; the site only reads them (and can delete one).
//
// One match (see website_record() in game_state.py):
//   { gameId, playedAt (ms), result: win|loss|unknown, myName, opponent, deckName,
//     myClasses: [..], opponentClasses: [..], myChips, opponentChips,
//     hands: [{hand, won: me|opponent|split, myHand, opponentHand}],
//     startingHand: [card ids],
//     myCards / myGenerated / opponentCards / opponentGenerated / opponentMaybe: {card id: times} }
//
// ---------- Staying inside the free plan ----------
// Every document downloaded counts as 1 read (50,000 free per day). So the browser
// keeps a copy of your matches, and each page load only reads "lastChange" (1 read).
// Everything is downloaded again only when the tracker saved something since.
// ============================================================

import { collection, doc, getDoc, getDocs, deleteDoc, setDoc }
  from "https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js";
import { db, auth, CACHE_PREFIX } from "./firebase.js";


function uid() {
  return auth.currentUser.uid;
}

function matchesFolder() {
  return collection(db, "users", uid(), "showdown_matches");
}

function metaDoc() {
  return doc(db, "users", uid(), "meta", "lastChange");
}


// ---------- The browser's copy (cache) ----------
function cacheKey() {
  return CACHE_PREFIX + uid() + "-matches";
}

function readCache() {
  try {
    return JSON.parse(localStorage.getItem(cacheKey()));
  } catch (error) {
    return null;    // broken or blocked: just ignore it
  }
}

function writeCache(data) {
  try {
    localStorage.setItem(cacheKey(), JSON.stringify(data));
  } catch (error) {
    console.warn("Couldn't save the local copy:", error);   // the site still works without it
  }
}


// ---------- Reading ----------
// Returns a list of matches (each with an "id"), in no particular order.
export async function loadMatches() {
  const meta = await getDoc(metaDoc());
  const stamp = meta.exists() ? meta.data().showdownMatches || 0 : 0;

  const cached = readCache();
  if (cached && cached.stamp === stamp) {
    return cached.matches;     // nothing new since last time
  }

  const snapshot = await getDocs(matchesFolder());
  // Python equivalent: [dict(d.data(), id=d.id) for d in snapshot.docs]
  const matches = snapshot.docs.map(function (d) {
    return Object.assign({ id: d.id }, d.data());
  });
  writeCache({ stamp: stamp, matches: matches });
  return matches;
}


// ---------- Deleting ----------
export async function deleteMatch(id) {
  await deleteDoc(doc(db, "users", uid(), "showdown_matches", id));
  // "merge" only changes this one field, the Origins site's fields stay as they are
  await setDoc(metaDoc(), { showdownMatches: Date.now() }, { merge: true });
  const cached = readCache();
  if (cached) {
    cached.matches = cached.matches.filter(function (m) { return m.id !== id; });
    cached.stamp = null;     // reload next time, to be safe
    writeCache(cached);
  }
}
