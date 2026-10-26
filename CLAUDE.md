# Showdown deck tracker + match history website

## About the owner (read first)
- Olivier is a **beginner coder who works in Python**. Give **extra detailed, step-by-step instructions** (where to click in VS Code, exact terminal commands, what output to expect).
- Windows PC, VS Code, PowerShell terminal, Python 3.14. Use `python -m pip ...`. Plays Showdown in **Edge**.
- Code style: lots of plain-English comments, simple names, "Python equivalent" notes in JS.
- Sister project: `..\origins-tracker` (Origins TCG tracker + website). This one copies its style and **shares its Firebase project**.

## What it is
Showdown (https://play.showdown.game): browser poker + action cards, 1v1, first to 100 chips. The tracker reads the game's own network messages (no screen recognition).

## Files
- `tracker.py`: starts Edge with `--remote-debugging-port=9222` and its own profile (`browser-profile/`), connects with Playwright `connect_over_cdp`, listens to `/catchup` responses (game events) and `/moves` requests (my moves), saves deck messages (`/api/Decks/compact` = my decks) to `games/decks/`. Writes `games/<date>_<id>/raw.jsonl, log.txt, summary.json`. Auto-saves finished matches online (`SAVE_ONLINE`). `--replay FILE` re-runs a saved file; `replay_game()` rebuilds a Game.
- `game_state.py`: the Game class (all game logic, incl. spectating). `overlay.py`: two Pillow-drawn tkinter windows (left my deck, right opponent + LIKELY CARDS; spectating: P1 / P2), settings in `overlay_settings.json` (gitignored). `profiles.py`: player profiles / predictions from `games/*/record.json` (written when a match ends; `backfill_records()` rebuilds missing ones). `cards.py`: card list, deck files, `GENERATORS`, `max_copies`. `update_cards.py`: rebuilds `cards.json` + `docs/cards.js` from the game's `card-faces.catalog-*.js` script.
- `website.py`: Firestore REST save to `users/<uid>/showdown_matches/<gameId>` (+ `meta/lastChange.showdownMatches`), using `tracker_key.txt` (made on the site's Tools page). `share_sightings()` adds `showdown_sightings/<gameId>_<name>` (opponents / both spectated players, never my own deck; create-only, `SHARE_PLAYERS`). `sync_sightings()` downloads new ones (savedAt >= last) into `games/shared_sightings.json`. `--upload-all [--replace]`.
- `firestore.rules`: anyone signed in; private `users/<uid>/**`; shared `showdown_sightings` (read all, create own with validated fields + savedAt == request.time; update: own always, someone else's only with MORE distinct cards and same gameId/nameKey; delete only own). `share_sightings()` checks the local copy first: add / update mine if changed / improve someone else's if mine has more / skip.
- `docs/`: the website (GitHub Pages from `/docs`): `index.html/home.js`, `match-history.*`, `database.js`, `firebase.js`, `common.js` (card bars), `cards.js` (generated).
- `.gitignore`: browser-profile/, games/, art/, tracker_key.txt. **Never commit or print tracker_key.txt.**

## Protocol facts (hard-won)
- `/catchup` answer: `{snapshot, batches:[{moveIndex, eventData: "<JSON list>"}], status:{gameId, viewerRole, status:{result, serverNow...}}}`. Snapshot has `initEventData` (start state: CreateCard for decks/hands, SetPlayerDeckClasses, SetGameLogItems).
- `AddGameLogItem` = game log (CardPlayed, Check, PhaseChanged, CardsTargeted, Showdown, Fold), with `P1HandCards/P2HandCards`, `ChipsAfter`. `EndHand` (hand result), `EndGame` (WinnerId) = match end. Status `result`: 3 waiting, 2 playing, 0 over.
- Card tracking by game card id: CreateCard/MoveCards/DestroyCard/UpdateCardVisibility. My draws = my deck card ids moving to `P1_Hand`. Opponent hidden cards get **new ids on every hand change** (can't follow one card).
- Generated cards: `AnimateCard` with `Info.animationId == "generatedCard"` on the card id = the lighter border, sent to **both** players (found 2026-10-25; matched every generated card in 10 matches). My own cards also have `Slots: [{"Type":"Generated"}]`. The class rule and "maybe" guesses were removed. Backcheck by copy limit (Rare 1, Common 2) stays. Opponent's held generated count = hand arrivals − deck draws.
- My deck = the saved deck whose 2 classes match the match (`pick_deck`).
- Card stats: match records have `me`, `deckCards` (exact list -> website numbers versions per deck name) and `handLog` = `Game.hand_log()`: per hand `{hand, winner P1/P2/split, result Wins/Folds/Split, cards {P1,P2}, generated {P1,P2}, chips {P1,P2} delta}`. Chips come from `AnimatePlayer setChips` after each `EndHand` (EndHand `WinnerId` = winner, also for Folds). Website `cards.html` / `card-stats.js`: per hand / per game, my plays / everyone, MIN_SAMPLES = 20.
- Spectating: `viewerRole` 2 (players are 0 = P1, 1 = P2). Snapshot of a joined-midway match has `SetGameLogItems` with the whole log so far + named discard/cast cards; hand results only from joining on. Spectated website record: `{spectated: true, result: "spectated", winner, players: [{name, classes, chips, cards, generated}], hands: [{hand, winner, p1Hand, p2Hand}]}`.
- Website pages: Home (own matches only), Match History (filter "Watched matches"), Players (`players.js`: own matches + shared sightings via `loadSightings()` incremental cache, same % logic as `profiles.predict`, hides my own names), Tools (Create key, setup steps for others).

## Tournament mode
- Trophy button (left overlay window) -> `Recorder.set_tournament(name)` (saved in `tournament_mode.json`, gitignored); `Game.tournament` goes into the match record and into shared sightings (`tournament` field, allowed by firestore.rules).
- `profiles.tournament_deck()`: union of cards a player played in that tournament (max copies per match), my records + shared; names compared with `tournament_key()` (lower case, single spaces). Overlay right window: TOURNAMENT DECK with copies left this match; LIKELY CARDS skips known cards. Website `tournaments.html/js` (same logic).
- Auto-detection (`tournaments.py` TournamentIndex): `GET /api/tournaments/public/<id>` = bracket `{name, status, deckType: "PerTournament" (= locked), participants [{userId, username, gameDeckJson (empty while running)}], stages[].rounds[].matches[] {currentGameId, p1/p2 {userId}, completedAt}}`. Match -> tournament by currentGameId, by `known_games.json` (every id ever seen; the bracket only shows the CURRENT game of each match), or by both player names in an unfinished bracket match (BO3 games 2-3). `Game.detect_tournament()` runs on every catchup and when a bracket arrives; overrides the manual trophy name; banner shows "auto". `replay_game()` detects too, else keeps the name from record.json; `--upload-all` rewrites record.json.

## Testing
- `python tracker.py --replay games\<folder>\raw.jsonl --no-overlay` (regression check on real matches).
- Website: copy `docs` to a temp folder, replace `firebase.js`/`database.js` with stubs that return `website_record()`s, serve with `python -m http.server`, check in the browser pane.

## Status (2026-10-25)
- Tournament mode built and tested with a made-up tournament (stubs/fakes); needs: updated rules published (tournament field), push, a real tournament match to check `games/tournaments/`.
- Opening to everyone: code done (rules, Tools page, sharing, Players merge), tested with fakes/stubs only. **Waiting on Olivier to create the separate Firebase project `showdown-tracker`** (README > One-time setup), then new firebase-config.js values, new key, `--upload-all`. Until then the site still points at the Origins project.
- Website published (GitHub repo Brainiac1830/showdown-tracker, public, Pages from `/docs`); key copied; 7 matches uploaded. `python website.py --upload-all --replace` re-saves old matches after tracker logic changes.
- Rules question: unclear if Showdown's terms allow trackers (real money). Advised: check ToS / ask them, use in free matches until then, no cross-match opponent profiles in the overlay.
