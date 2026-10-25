# browsers.py
# Finds a browser the tracker can use, on any PC.
#
# The tracker talks to the browser through a "debugging port", which only exists in
# browsers built on Chrome's engine: Edge, Chrome, Brave, Vivaldi, Opera, Chromium...
# Firefox and Safari can't be used. That's fine: the tracker always opens its OWN
# window with its own profile, so your normal browser can be anything.
#
# Order:
#   1. browser_path.txt (next to tracker.py): the full path to a browser, if you want one in particular
#   2. browsers registered in Windows ("Default apps" list), in the order of PREFERRED
#   3. the usual install folders (incl. per-user installs, Mac and Linux places)
#   4. last resort: download Playwright's own Chromium once (~150 MB) and use that

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Chrome-type browsers, best first. Edge first: it's on every Windows PC.
PREFERRED = ["msedge", "chrome", "brave", "vivaldi", "opera", "launcher", "chromium"]

LOCAL = os.environ.get("LOCALAPPDATA", "")
PLACES = [
    # Windows
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    rf"{LOCAL}\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    rf"{LOCAL}\BraveSoftware\Brave-Browser\Application\brave.exe",
    rf"{LOCAL}\Vivaldi\Application\vivaldi.exe",
    r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
    rf"{LOCAL}\Programs\Opera\opera.exe",
    rf"{LOCAL}\Programs\Opera GX\opera.exe",
    rf"{LOCAL}\Chromium\Application\chrome.exe",
    # Mac
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    # Linux
    "/usr/bin/microsoft-edge", "/usr/bin/google-chrome", "/usr/bin/brave-browser",
    "/usr/bin/vivaldi", "/usr/bin/chromium", "/usr/bin/chromium-browser",
]


def from_setting_file(path):
    """browser_path.txt: the first non-empty line is the browser's full path."""
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip().strip('"')
            if line and not line.startswith("#"):
                return line
    except OSError:
        pass
    return None


def from_windows_list():
    """The browsers Windows knows about (Settings > Default apps), Chrome-type ones only,
    best first. Each entry has the command that starts it."""
    try:
        import winreg      # Windows only
    except ImportError:
        return []
    found = []
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            clients = winreg.OpenKey(root, r"SOFTWARE\Clients\StartMenuInternet")
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(clients)[0]):
            try:
                name = winreg.EnumKey(clients, i)
                command = winreg.QueryValue(clients, name + r"\shell\open\command")
            except OSError:
                continue
            exe = command.split('"')[1] if command.startswith('"') else command.split(" ")[0]
            stem = Path(exe).stem.lower()
            if stem in PREFERRED and os.path.exists(exe):
                found.append(exe)
    found.sort(key=lambda exe: PREFERRED.index(Path(exe).stem.lower()))
    return found


def playwright_chromium(download=True):
    """Playwright's own Chromium (downloaded once into ms-playwright). None if not there."""
    homes = [Path(LOCAL) / "ms-playwright", Path.home() / "Library/Caches/ms-playwright",
             Path.home() / ".cache/ms-playwright"]
    patterns = ["chromium-*/chrome-win*/chrome.exe", "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
                "chromium-*/chrome-linux*/chrome"]
    for home in homes:
        for pattern in patterns:
            hits = sorted(glob.glob(str(home / pattern)))
            if hits:
                return hits[-1]           # the newest version
    if download:
        print("No Chrome-type browser found (Edge, Chrome, Brave...).")
        print("Downloading Playwright's own Chromium once (about 150 MB), please wait...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
        return playwright_chromium(download=False)
    return None


def find_browser(setting_file):
    """The browser to open the game in. Returns its full path, or None."""
    chosen = from_setting_file(setting_file)
    if chosen:
        if os.path.exists(chosen):
            return chosen
        print(f"browser_path.txt says {chosen}, but that file doesn't exist. Looking for another browser.")
    found = from_windows_list()
    if found:
        return found[0]
    for place in PLACES:
        if place and os.path.exists(place):
            return place
    for name in PREFERRED:
        if shutil.which(name):
            return shutil.which(name)
    return playwright_chromium()


if __name__ == "__main__":
    # python browsers.py  ->  shows what the tracker would use
    here = Path(__file__).resolve().parent
    print("Browsers registered in Windows:", from_windows_list() or "none (or not Windows)")
    print("The tracker will use:", find_browser(here / "browser_path.txt"))
