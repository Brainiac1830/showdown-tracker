// ============================================================
// tools.js — the Tools page: create the key that links your deck tracker.
//
// The key holds your account id and a "refresh token" (what keeps you signed in),
// turned into base64 text. The tracker (website.py) uses it to save matches as you.
// Same as the Origins website's key.
// ============================================================

import { watchUser, auth } from "./firebase.js";

const signinNote = document.getElementById("key-signin");
const keyBox     = document.getElementById("key-box");
const keyInput   = document.getElementById("tracker-key");
const createBtn  = document.getElementById("key-create");
const copyBtn    = document.getElementById("key-copy");
const message    = document.getElementById("key-message");

watchUser(function (user) {
  keyBox.classList.toggle("hidden", !user);
  signinNote.classList.toggle("hidden", !!user);
  keyInput.value = "";
  copyBtn.classList.add("hidden");
  message.textContent = "";
});

createBtn.addEventListener("click", function () {
  const user = auth.currentUser;
  if (!user) {
    return;
  }
  const key = { v: 1, uid: user.uid, email: user.email, refreshToken: user.refreshToken };
  keyInput.value = btoa(JSON.stringify(key));      // btoa = turn the text into base64 letters
  copyBtn.classList.remove("hidden");
  message.textContent = "Save it as tracker_key.txt in the tracker's folder, then run:  python website.py  to check it works.";
});

copyBtn.addEventListener("click", async function () {
  try {
    await navigator.clipboard.writeText(keyInput.value);
    message.textContent = "Copied! Paste it into tracker_key.txt and save the file.";
  } catch (error) {
    keyInput.select();                              // copying blocked: select it so Ctrl+C works
    message.textContent = "Press Ctrl+C to copy it.";
  }
});
