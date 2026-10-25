// ============================================================
// firebase-config.js — the "address" of the Showdown Firebase project
// ("showdown-tracker", separate from the Origins website since 2026-10-25).
//
// Is it safe to put this on GitHub? Yes. These values only tell the site
// WHERE the database is. What protects the data is Google sign-in plus
// the security rules (firestore.rules): your matches can only be read by you.
//
// website.py reads apiKey and projectId from this file too.
// ============================================================

// For Firebase JS SDK v7.20.0 and later, measurementId is optional
export const firebaseConfig = {
  apiKey: "AIzaSyDjxyiA81o6oGd5iH8pD6uai1k3uCKtknE",
  authDomain: "showdown-tracker-87e50.firebaseapp.com",
  projectId: "showdown-tracker-87e50",
  storageBucket: "showdown-tracker-87e50.firebasestorage.app",
  messagingSenderId: "180464462804",
  appId: "1:180464462804:web:7422272b381cded6f64441",
  measurementId: "G-93Z7ZDN4K7"
};
