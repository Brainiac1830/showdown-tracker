# update_cards.py
# Builds cards.json: every Showdown action card with its stage, chip score and art.
#
# The game keeps its card list inside one of its website scripts
# (named like "card-faces.catalog-XXXX.js"). This script downloads the game page,
# finds that script, and reads each card out of it.
#
# Run it again when the game adds or changes cards:
#     python update_cards.py
#
# Each card in cards.json looks like:
#   {"id": "salvaged_goods", "name": "Salvaged Goods", "type": "Flop", "chips": 0,
#    "rarity": "Common", "class": "Rebel", "text": "...", "art": "https://..."}
# type is one of: Any (= Universal), PreFlop, Flop, River

import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = "https://play.showdown.game"
CHUNKS = SITE + "/_next/static/chunks/"
# The game's pictures live here ("../../objects/x.webp" in the script = this folder)
OBJECTS = "https://showdown-assets-prod.fra1.cdn.digitaloceanspaces.com/showdownweb/objects/"
ART_WIDTH = 256   # small art picture is plenty for the overlay


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as answer:
        return answer.read().decode("utf-8", errors="replace")


def find_catalog_script():
    """Go through the game's scripts until one has the card list in it.
    Scripts load other scripts with import(`./Name-1234.js`), so we follow those."""
    page = download(SITE + "/")
    to_check = [name.split("/")[-1] for name in re.findall(r'/_next/static/chunks/([^"]+?\.js)', page)]
    checked = set()
    while to_check and len(checked) < 400:
        name = to_check.pop(0)
        if name in checked:
            continue
        checked.add(name)
        try:
            text = download(CHUNKS + name)
        except Exception:
            continue
        if "artwork:`" in text and "type:`River`" in text:
            print(f"Card list found in {name} (checked {len(checked)} scripts)")
            return text
        # Scripts this one loads later. The list is usually named "card-faces...", check those first.
        for more in re.findall(r'["`]\./([A-Za-z0-9_.-]+\.js)["`]', text):
            if more not in checked:
                if "card-faces" in more:
                    to_check.insert(0, more)
                else:
                    to_check.append(more)
    raise SystemExit("Could not find the card list in the game's scripts. The game may have changed.")


def read_cards(text):
    # Card art: "artwork:salvaged_goods":{"url":"../../objects/x.webp", ..., "variants":[{url, width}, ...]}
    art = {}
    for m in re.finditer(r'"artwork:([a-z0-9_]+)":\{"url":"([^"]+)"[^\[]*"variants":\[(.*?)\]\}', text):
        variants = re.findall(r'"url":"([^"]+)"[^}]*"width":(\d+)', m.group(3))
        small = [url for url, width in variants if int(width) == ART_WIDTH]
        url = small[0] if small else m.group(2)
        art[m.group(1)] = OBJECTS + url.split("objects/")[-1]

    # Cards: {id:`x`,artwork:`artwork:x`,chips:0,rarity:`Common`,name:`...`,type:`Flop`,text:`...`,...,class:`Rebel`}
    cards = []
    for part in re.split(r"(?=\{id:`[a-z0-9_]+`,artwork:)", text)[1:]:
        card = {}
        for key in ("id", "name", "type", "rarity", "class", "text"):
            found = re.search(key + r":`([^`]*)`", part)
            card[key] = found.group(1) if found else None
        chips = re.search(r"chips:(-?\d+)", part)
        card["chips"] = int(chips.group(1)) if chips else 0
        card["art"] = art.get(card["id"])
        cards.append(card)
    return cards


def write_site_cards(cards):
    """The same list for the website: docs/cards.js, one card per line, as
       const CARDS = [ {...}, ... ];"""
    lines = [json.dumps({k: c[k] for k in ("id", "name", "type", "chips", "rarity", "class", "text", "art")},
                        ensure_ascii=False) for c in cards]
    with open(HERE / "docs" / "cards.js", "w", encoding="utf-8") as f:
        f.write("// cards.js — every Showdown action card. Made by update_cards.py: don't edit by hand.\n")
        f.write("// type: Any (= Universal), PreFlop, Flop, River.  chips: the card's chip score.\n")
        f.write("const CARDS = [\n" + ",\n".join(lines) + "\n];\n")


if __name__ == "__main__":
    cards = read_cards(find_catalog_script())
    if len(cards) < 50:
        raise SystemExit(f"Only {len(cards)} cards found, something went wrong. cards.json not changed.")
    cards.sort(key=lambda c: c["id"])
    with open(HERE / "cards.json", "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=1, ensure_ascii=False)
    write_site_cards(cards)
    stages = {}
    for c in cards:
        stages[c["type"]] = stages.get(c["type"], 0) + 1
    print(f"Saved {len(cards)} cards in cards.json  {stages}")
