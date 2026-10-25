// ============================================================
// firebase.js — connects the site to Firebase and handles sign-in.
// Every page loads this file. It:
//   1. connects to the Firebase project (the same one as the Origins website)
//   2. shows a "Sign in with Google" button in the menu
//   3. after you sign in, checks that the database lets you in
//
// This file is a "module" (loaded with type="module" in the HTML).
// Modules can use "import", which works like Python's import.
// ============================================================

// ---------- 1. IMPORT FIREBASE ----------
// Python equivalent:  from firebase_auth import get_auth, sign_out, ...
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged }
  from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";
import { getFirestore, doc, getDoc }
  from "https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js";

import { firebaseConfig } from "./firebase-config.js";


// ---------- 2. CONNECT ----------
const authArea = document.getElementById("auth-area");

export const app  = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db   = getFirestore(app);

// Every saved copy in the browser starts with this (see database.js)
export const CACHE_PREFIX = "showdown-cache-";


// ---------- 3. THE SIGN-IN AREA IN THE MENU ----------

function showSignedOut() {
  authArea.innerHTML = `<button class="auth-btn" id="sign-in-btn">Sign in with Google</button>`;
  document.getElementById("sign-in-btn").addEventListener("click", signIn);
}

function showSignedIn(user) {
  // Only the first name of your Google account
  const firstName = (user.displayName || user.email).split(" ")[0];
  authArea.innerHTML = `
    <span class="auth-status" id="db-status" title="Checking the database...">●</span>
    <span class="auth-name">${escapeHtml(firstName)}</span>
    <button class="auth-btn" id="sign-out-btn">Sign out</button>
  `;
  document.getElementById("sign-out-btn").addEventListener("click", function () {
    clearLocalCopies();
    signOut(auth);
  });
  checkDatabase(user);
}

// Opens the Google sign-in pop-up window
async function signIn() {
  try {
    await signInWithPopup(auth, new GoogleAuthProvider());
    // onAuthStateChanged (below) notices the sign-in by itself
  } catch (error) {
    if (error.code === "auth/popup-closed-by-user" || error.code === "auth/cancelled-popup-request") {
      return;   // you closed the pop-up: not a real error
    }
    if (error.code === "auth/unauthorized-domain") {
      alert(`Firebase doesn't allow sign-in from "${location.hostname}" yet.\n\n` +
            `Add it in Firebase: Authentication > Settings > Authorized domains.`);
      return;
    }
    alert("Sign-in failed: " + error.message);
    console.error(error);
  }
}

// Signing out removes the copy of your matches kept in this browser
function clearLocalCopies() {
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (key.startsWith(CACHE_PREFIX)) {
      localStorage.removeItem(key);
    }
  }
  sessionStorage.removeItem("showdown-db-ok");
}


// ---------- 4. DATABASE CHECK ----------
// Reads one tiny document: the dot turns green if the security rules let us in.
// Only checked once per browser session (sessionStorage is forgotten when you close the browser).
async function checkDatabase(user) {
  const status = document.getElementById("db-status");
  if (sessionStorage.getItem("showdown-db-ok") === user.email) {
    status.classList.add("ok");
    status.title = "Database connected";
    return;
  }
  try {
    await getDoc(doc(db, "users", user.uid, "meta", "lastChange"));
    sessionStorage.setItem("showdown-db-ok", user.email);
    status.classList.add("ok");
    status.title = "Database connected";
  } catch (error) {
    status.classList.add("error");
    status.title = error.code === "permission-denied"
      ? "This Google account isn't on the player list (the email list in the Firestore rules)."
      : "Database error: " + error.message;
    console.error(error);
  }
}


// ---------- 5. LET OTHER PAGES KNOW WHO'S SIGNED IN ----------
// Pages call  watchUser(myFunction) ; myFunction(user) runs when the page opens
// and every time you sign in or out (user is null when signed out).
export function watchUser(callback) {
  onAuthStateChanged(auth, callback);
}


// ---------- 6. START ----------
onAuthStateChanged(auth, function (user) {
  if (user) {
    showSignedIn(user);
  } else {
    showSignedOut();
  }
});
