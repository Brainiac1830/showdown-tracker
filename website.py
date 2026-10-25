# ============================================================
# website.py - saves a finished match to your Showdown website (Firebase).
#
# It uses your "tracker key": create it on the website (Tools page) and save it
# as tracker_key.txt in this folder. That file is your login for the website's
# data: keep it private (.gitignore stops it going to GitHub).
#
# A save:
#   1. writes the match to  users/<you>/showdown_matches/<game id>
#      (the game id is the document's name, so a match can't be saved twice)
#   2. updates  users/<you>/meta/lastChange  field "showdownMatches",
#      so the website downloads your matches again
#   3. shares the players you saw (share_sightings), for everyone's "likely cards"
#
# Commands:
#   python website.py                test the link and download the shared player data
#   python website.py --upload-all   save every finished match in games\ that isn't online yet
#   python website.py --upload-all --replace
#                                    same, but also re-save the matches already online
#                                    (after the tracker learned something new, e.g. the
#                                    lighter "generated" border on 2026-10-25)
# ============================================================

import base64
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY_FILE = HERE / "tracker_key.txt"
CONFIG_FILE = HERE / "docs" / "firebase-config.js"
SITE_URL = "https://brainiac1830.github.io/showdown-tracker/"
FOLDER = "showdown_matches"


# ---------- 1. SETTINGS: the key and the Firebase project ----------

def read_key():
    """The tracker key (a dict with uid, email, refreshToken), or None if missing."""
    if not KEY_FILE.exists():
        return None
    try:
        text = re.sub(r"\s", "", KEY_FILE.read_text(encoding="utf-8"))
        text += "=" * (-len(text) % 4)
        decoded = base64.b64decode(text).decode("utf-8", errors="replace")
        key = json.JSONDecoder().raw_decode(decoded)[0]   # ignores stray characters after the key
        return key if key.get("refreshToken") and key.get("uid") else None
    except Exception:
        return None


def is_linked():
    return read_key() is not None


def firebase_config():
    """apiKey and projectId, read from docs/firebase-config.js."""
    text = CONFIG_FILE.read_text(encoding="utf-8")
    return {name: re.search(name + r':\s*"([^"]+)"', text).group(1) for name in ("apiKey", "projectId")}


# ---------- 2. TALKING TO FIREBASE (plain web requests) ----------

class AlreadySaved(Exception):
    pass


def request(url, data=None, token=None, form=False):
    """Sends a web request and returns the JSON answer. Raises an error with
    Firebase's message if something goes wrong."""
    headers = {"Referer": SITE_URL}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as answer:
            return json.loads(answer.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except Exception:
            pass
        if error.code == 409 or "ALREADY_EXISTS" in str(detail):
            raise AlreadySaved()
        raise RuntimeError(f"{error.code}: {detail}")


_token = {"value": None, "until": 0}


def id_token():
    """A short-lived sign-in token, made from the tracker key (renewed every hour)."""
    if _token["value"] and time.time() < _token["until"] - 60:
        return _token["value"]
    key = read_key()
    if key is None:
        raise RuntimeError("No tracker_key.txt in the showdown-tracker folder.")
    answer = request("https://securetoken.googleapis.com/v1/token?key=" + firebase_config()["apiKey"],
                     {"grant_type": "refresh_token", "refresh_token": key["refreshToken"]}, form=True)
    _token["value"] = answer["id_token"]
    _token["until"] = time.time() + int(answer.get("expires_in", 3600))
    return _token["value"]


def documents_url():
    return f"https://firestore.googleapis.com/v1/projects/{firebase_config()['projectId']}/databases/(default)/documents"


def doc_name(path):
    return f"projects/{firebase_config()['projectId']}/databases/(default)/documents/{path}"


def from_value(value):
    """Firestore's typed value -> Python value (the opposite of to_value)."""
    kind, inner = next(iter(value.items()))
    if kind == "integerValue":
        return int(inner)
    if kind == "arrayValue":
        return [from_value(v) for v in inner.get("values", [])]
    if kind == "mapValue":
        return {k: from_value(v) for k, v in inner.get("fields", {}).items()}
    if kind == "nullValue":
        return None
    return inner                               # strings, numbers, booleans, timestamps (as text)


def to_value(value):
    """Python value -> Firestore's typed value, e.g. "Roo" -> {"stringValue": "Roo"}"""
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [to_value(v) for v in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {str(k): to_value(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


# ---------- 3. SAVING A MATCH ----------

def save_match(record, replace=False):
    """Saves one match (Game.website_record()). Returns True if saved,
    False if it was saved already (unless replace=True: then it's overwritten).
    Raises RuntimeError with a readable message."""
    if record.get("result") not in ("win", "loss", "spectated"):
        raise RuntimeError("The match has no result yet.")
    uid = read_key()["uid"]
    match_write = {
        # 1. the match, named after the game id
        "update": {"name": doc_name(f"users/{uid}/{FOLDER}/{record['gameId']}"),
                   "fields": {k: to_value(v) for k, v in record.items()}},
        "updateTransforms": [{"fieldPath": "savedAt", "setToServerValue": "REQUEST_TIME"}],
    }
    if not replace:
        match_write["currentDocument"] = {"exists": False}    # = refuse if it's there already
    writes = [match_write, {
        # 2. "Showdown matches changed" stamp (only this field: the Origins site's stay as they are)
        "update": {"name": doc_name(f"users/{uid}/meta/lastChange"),
                   "fields": {"showdownMatches": to_value(int(time.time() * 1000))}},
        "updateMask": {"fieldPaths": ["showdownMatches"]},
    }]
    try:
        request(f"{documents_url()}:commit", {"writes": writes}, token=id_token())
        return True
    except AlreadySaved:
        return False


# ---------- 3b. SHARED PLAYER SIGHTINGS ----------
# What we saw other players play, shared with everyone who uses the site:
#   showdown_sightings/<game id>_<player name>  =
#   {gameId, name, nameKey, classes, classKey, cards: {card id: times}, playedAt, savedAt, by}
# Only opponents (and both players of a spectated match): my own deck is never shared.
# The rules (firestore.rules) let everyone read and add them; only the one who
# added a sighting can change it.

SIGHTINGS = "showdown_sightings"
SHARE_PLAYERS = True          # False = never share what you saw (you still get everyone else's)


def sighting_id(game_id, name):
    """<game id>_<name>, with only safe letters (a document name can't contain "/")."""
    return f"{game_id}_{re.sub(r'[^a-z0-9_-]', '_', name.lower())[:40]}"


def share_sightings(record, replace=False):
    """Shares the players seen in this match. Returns a short text for the log.
    A sighting someone else already shared (e.g. you both watched the same match) is skipped."""
    from profiles import appearances, class_key      # here: profiles is only needed for this
    if not SHARE_PLAYERS:
        return "sharing turned off"
    uid = read_key()["uid"]
    shared = skipped = 0
    for a in appearances(record):
        name = a["name"][:40]
        fields = {
            "gameId": record["gameId"], "name": name, "nameKey": name.lower(),
            "classes": list(a["classes"])[:2], "classKey": class_key(a["classes"]),
            "cards": {card: n for card, n in a["cards"].items() if n > 0},
            "playedAt": int(a["playedAt"]), "by": uid,
        }
        write = {"update": {"name": doc_name(f"{SIGHTINGS}/{sighting_id(record['gameId'], name)}"),
                            "fields": {k: to_value(v) for k, v in fields.items()}},
                 "updateTransforms": [{"fieldPath": "savedAt", "setToServerValue": "REQUEST_TIME"}]}
        if not replace:
            write["currentDocument"] = {"exists": False}
        try:
            request(f"{documents_url()}:commit", {"writes": [write]}, token=id_token())
            shared += 1
        except AlreadySaved:
            skipped += 1
        except RuntimeError as error:
            if "403" in str(error) or "PERMISSION_DENIED" in str(error):
                skipped += 1          # shared by someone else: only they can change it
            else:
                raise
    return f"shared {shared} player(s)" + (f", {skipped} already shared" if skipped else "")


def sync_sightings(cache_file):
    """Downloads the shared sightings that are new since last time into cache_file
    (a JSON file), and returns all of them as a list. Only new ones count as reads,
    so this stays cheap however many there are."""
    cache_file = Path(cache_file)
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cache = {"last": None, "sightings": {}}
    while True:
        query = {"structuredQuery": {
            "from": [{"collectionId": SIGHTINGS}],
            "orderBy": [{"field": {"fieldPath": "savedAt"}, "direction": "ASCENDING"}],
            "limit": 300}}
        if cache["last"]:
            # ">=" and not ">": two sightings can have the same time; the dict removes repeats
            query["structuredQuery"]["where"] = {"fieldFilter": {
                "field": {"fieldPath": "savedAt"}, "op": "GREATER_THAN_OR_EQUAL",
                "value": {"timestampValue": cache["last"]}}}
        rows = request(f"{documents_url()}:runQuery", query, token=id_token())
        docs = [row["document"] for row in rows if "document" in row]
        new = 0
        for d in docs:
            doc_id = d["name"].split("/")[-1]
            data = {k: from_value(v) for k, v in d.get("fields", {}).items()}
            if doc_id not in cache["sightings"] or cache["sightings"][doc_id].get("savedAt") != data.get("savedAt"):
                new += 1
            cache["sightings"][doc_id] = data
            cache["last"] = data.get("savedAt") or cache["last"]
        if len(docs) < 300 or new == 0:
            break
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache), encoding="utf-8")
    return list(cache["sightings"].values())


def count_saved():
    """How many Showdown matches are online (only reads their names)."""
    uid = read_key()["uid"]
    total, page = 0, ""
    while True:
        url = f"{documents_url()}/users/{uid}/{FOLDER}?pageSize=300&mask.fieldPaths=gameId"
        answer = request(url + (f"&pageToken={page}" if page else ""), token=id_token())
        total += len(answer.get("documents", []))
        page = answer.get("nextPageToken")
        if not page:
            return total


# ---------- 4. UPLOADING OLD MATCHES ----------

def upload_all(replace=False):
    """Replays every match folder in games\\ and saves the finished ones
    (replace=True: also re-save the ones already online)."""
    from tracker import SAVE_FOLDER, replay_game     # here, not at the top: tracker.py imports this file
    from profiles import appearances
    folders = sorted(p for p in SAVE_FOLDER.glob("*/raw.jsonl")
                     if not p.parent.name.startswith(("replay_", "test_")))
    for raw in folders:
        game = replay_game(raw)
        name = raw.parent.name
        if game is None or not game.ended:
            print(f"  {name}: not finished, skipped")
            continue
        try:
            record = game.website_record()
            saved = save_match(record, replace)
            players = " vs ".join(a["name"] for a in appearances(record))
            print(f"  {name}: {'saved' if saved else 'already online'} ({game.result_word()}: {players})"
                  f" - {share_sightings(record, replace)}")
        except RuntimeError as error:
            print(f"  {name}: not saved - {error}")


if __name__ == "__main__":
    if not is_linked():
        print(f"Not linked yet: create a key on the website (Tools page) and save it as {KEY_FILE}")
        sys.exit(1)
    try:
        if "--upload-all" in sys.argv:
            print("Uploading finished matches from games\\ ...")
            upload_all(replace="--replace" in sys.argv)
        print(f"Linked ✓  ({read_key().get('email', '?')}) - {count_saved()} Showdown matches online")
        shared = sync_sightings(HERE / "games" / "shared_sightings.json")
        print(f"Shared player data: {len(shared)} sightings of {len({s.get('nameKey') for s in shared})} players")
    except Exception as error:
        print("The link didn't work:", error)
