# Showdown Tracker: setup

A deck tracker for **Showdown** (https://play.showdown.game) that runs on your PC while you play:
- your deck on the left of the screen (cards left, greyed out when drawn)
- your opponent on the right: what they played, their **likely cards** from earlier matches, and in
  tournaments their **known deck**
- your match history and the players you've met on the website:
  https://brainiac1830.github.io/showdown-tracker/

It reads the game's own messages (no screen reading), and only knows what you can see.

Takes about 10 minutes, once. Windows only.

---

## 1. Install Python (once)
1. Go to https://www.python.org/downloads/ and click the big yellow **Download Python** button.
2. Open the file you downloaded.
3. **IMPORTANT:** on the first screen, tick **"Add python.exe to PATH"** at the bottom, then click
   **Install Now**.
4. When it says "Setup was successful", click **Close**.

## 2. Download the tracker
1. Go to https://github.com/Brainiac1830/showdown-tracker
2. Click the green **Code** button > **Download ZIP**.
3. Before opening it: right-click the ZIP > **Properties** > tick **Unblock** at the bottom (if you see it) > **OK**.
   (Otherwise Windows may block start.bat because it came from the internet.)
4. Right-click the ZIP > **Extract All...** > pick a place like `Documents\ShowdownTracker` > **Extract**.

## 3. Link it to your account (so your matches are saved)
1. Open https://brainiac1830.github.io/showdown-tracker/tools.html
2. Click **Sign in with Google** (top right), then **Create key**, then **Copy**.
3. Open **Notepad**, paste (**Ctrl+V**), then **File > Save As...**:
   - go to the tracker folder (the one with `start.bat` in it)
   - **Save as type: All files (\*.\*)**  <- important
   - File name: `tracker_key.txt`
   - click **Save**
   
   If you leave "Save as type" on "Text Documents", Windows saves it as `tracker_key.txt.txt` and the
   tracker won't find it (start.bat tells you if that happened: just rename the file).

The key works like a password for your matches on the site: don't share it or post it anywhere.

## 4. Start it
**Double-click `start.bat`.** The first time, it installs what it needs (about a minute).

Then a **new browser window** opens on Showdown. It has its own profile, so the first time:
**log in to Showdown in that window**. After that it remembers you.

**Always play (or watch) in that window**: the tracker can't see your normal browser.

The two overlay windows appear at the edges of the screen. Drag them where you like.

## 5. Good to know
- **Your decks:** open the game's deck screen once (Change Deck) so the tracker learns your decks.
  After that it picks the right one by itself in each match.
- **Likely cards** (lilac, dashed): cards that player played in earlier matches with the same classes.
  It's a guess, **not their decklist**. Click its title to hide it.
- **Tournaments:** decks are locked in a tournament, so every card a player plays is in their deck.
  Open the tournament in the game once (e.g. to watch a table): the tracker then recognises its matches
  by itself and shows each player's **TOURNAMENT DECK**. The trophy button (left window) is for doing it by hand.
- **Watching (spectating)** other players' matches works the same way: both players are tracked.
- **Leaving a match early** is fine: what you saw still counts.
- **What's shared:** your match history is private. The cards you saw *other* players play are shared
  with everyone using the tracker (that's what makes "likely cards" and tournament decks work).
  Your own deck is never shared by your tracker.

## 6. Updating
**Double-click `update.bat`** (close the tracker first). It downloads the newest version from GitHub,
replaces the tracker files and shows what changed. Your key, your matches (`games` folder), your login
and your settings are kept.

(By hand: download the ZIP again as in step 2 and extract it into the same folder, choosing
**Replace the files**.)

## Problems?
| What you see | What to do |
|---|---|
| "Python isn't installed" | Step 1. If you installed it already, reinstall and tick **Add python.exe to PATH**. |
| "Windows protected your PC" when opening start.bat | Click **More info** > **Run anyway** (or do the **Unblock** part of step 2). |
| The overlay says "Waiting for a match..." | Play or watch in the window the tracker opened, not in your normal browser. |
| You want a different browser | Make a file `browser_path.txt` in the tracker folder with the full path of the browser in it (Edge, Chrome, Brave, Vivaldi or Opera; Firefox can't be used). |
| Anything else | Send a screenshot of the black start.bat window to whoever gave you the tracker. |
