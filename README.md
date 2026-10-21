# letterboxd-trakt-sync

[![tests](https://github.com/carsoreo/letterboxd-trakt-sync/actions/workflows/test.yml/badge.svg)](https://github.com/carsoreo/letterboxd-trakt-sync/actions/workflows/test.yml)

Keep your movie history in step between [Letterboxd](https://letterboxd.com) and [Trakt](https://trakt.tv).

Lots of apps read your watch history from Trakt: media centers and their add-ons, recommendation tools, "continue watching" and "watched" markers, Trakt's own apps. If you log films on Letterboxd, those apps don't know about any of it. This tool copies your Letterboxd diary and ratings to Trakt, keeps them coming automatically, and hands films you watched elsewhere back to Letterboxd.

- **Letterboxd → Trakt (automatic):** a one-time import of your full Letterboxd history, then new diary entries every few hours from your public Letterboxd RSS feed. Watches and ratings are copied; anything already on Trakt is skipped.
- **Trakt → Letterboxd (one manual upload):** Letterboxd has no public API for adding watches, so new Trakt movie plays are written to a CSV in Letterboxd's own import format. You upload it at [letterboxd.com/import](https://letterboxd.com/import/). Films that came from Letterboxd are never exported back.

Pure Python standard library (3.9+), no dependencies, no Letterboxd password needed. Runs on Windows, macOS, Linux, a Raspberry Pi or a media box like Batocera.

**Contents:** [How it works](#how-it-works) · [Quick start](#quick-start) · [Setup in detail](#setup-in-detail) · [Everyday use](#everyday-use) · [Running on a schedule](#running-on-a-schedule) · [How matching works](#how-matching-works) · [Limitations](#limitations) · [Troubleshooting](#troubleshooting) · [Security and privacy](#security-and-privacy) · [Updating and uninstalling](#updating-and-uninstalling) · [Development](#development)

## How it works

```
                  one-time: Letterboxd data export (ZIP)
                  ongoing:  letterboxd.com/<you>/rss/  (latest 50 diary entries)
Letterboxd  ───────────────────────────────────────────────▶  Trakt
   ▲                    watches + ratings, deduplicated          │
   │                                                             │  movie plays logged by other apps
   │   you upload at letterboxd.com/import                       ▼
   └──────────────  exports/letterboxd-import-<time>.csv  ◀──────┘
                    (only plays that didn't come from Letterboxd)
```

The tool keeps a small `state.json` next to your config with your Trakt sign-in and what it has already synced, so every run only handles what's new and repeated runs never create duplicates.

## Quick start

```
git clone https://github.com/carsoreo/letterboxd-trakt-sync
cd letterboxd-trakt-sync
cp config.example.json config.json        # then edit it: username + Trakt Client ID
python -m lbtrakt auth                     # sign in to Trakt with a code
python -m lbtrakt import-letterboxd ~/Downloads/letterboxd-yourname-*.zip
python -m lbtrakt run                      # keep syncing every few hours
```

Each step is explained below. Use `python3` instead of `python` if that's what your system calls it, and `copy` instead of `cp` on Windows.

## Setup in detail

### 1. Get the code

```
git clone https://github.com/carsoreo/letterboxd-trakt-sync
cd letterboxd-trakt-sync
```

Run commands from this folder as `python -m lbtrakt …`. Or install it with `pip install .` and use the `lbtrakt` command from anywhere; it reads `config.json` from the current folder unless you pass `--config path/to/config.json`.

### 2. Make your Letterboxd profile public

The ongoing sync reads `https://letterboxd.com/<username>/rss/`, which only works for public profiles. (The one-time import uses your data export and works either way.)

### 3. Create a Trakt app

Go to [developer.trakt.tv](https://developer.trakt.tv) → **My Apps** → **New app**:

- **Name:** anything, e.g. "Letterboxd Sync"
- **Type:** Development (only you can sign in with it, which is all this needs)
- **Redirect URI:** `http://localhost` (not used; the tool signs in with a device code)

Copy the **Client ID** from the app's page.

- Apps created since 2026 get no client secret; leave `trakt_client_secret` empty. Older apps that have one can put it in.
- **Free Trakt accounts can only have one third-party app connected.** If something else is already connected (a media center add-on, for example), either reuse that app's Client ID here (both can share it), disconnect the other app, or use Trakt VIP. The tool tells you plainly if you hit this limit.

### 4. Configure

Copy `config.example.json` to `config.json` and fill it in:

```json
{
  "letterboxd_username": "yourname",
  "trakt_client_id": "the-client-id-you-copied",
  "trakt_client_secret": "",
  "export_dir": "exports",
  "sync_ratings": true,
  "interval_hours": 6
}
```

| Setting | Meaning |
| --- | --- |
| `letterboxd_username` | Your Letterboxd username, as in `letterboxd.com/<username>/` |
| `trakt_client_id` | Client ID from step 3 |
| `trakt_client_secret` | Leave empty unless your Trakt app has one |
| `export_dir` | Where Letterboxd import CSVs are written: relative to the config file, or an absolute path (e.g. a shared folder) |
| `sync_ratings` | Copy Letterboxd ratings to Trakt (`true` / `false`) |
| `interval_hours` | How often `run` syncs (minimum 1) |

### 5. Sign in to Trakt

```
python -m lbtrakt auth
```

It prints something like:

```
2026-03-14 09:00:00 Go to https://auth.trakt.tv/activate and enter code: ABCD1234
```

Open that page on any device, enter the code and approve the app. The sign-in is saved to `state.json` and renewed automatically; you shouldn't need to do this again.

### 6. Import your full history (once)

In Letterboxd go to **Settings → Import & Export → Export your data** and download the ZIP. Then preview and import it:

```
python -m lbtrakt --dry-run import-letterboxd letterboxd-yourname-2026-10-21.zip
python -m lbtrakt import-letterboxd letterboxd-yourname-2026-10-21.zip
```

Example output:

```
Read 310 Letterboxd entries from letterboxd-yourname-2026-10-21.zip
Letterboxd -> Trakt: {'checked': 310, 'added': 287, 'already_on_trakt': 21, 'ratings': 295, 'not_found': [...]}
```

- `added`: viewings added to Trakt
- `already_on_trakt`: skipped because Trakt already had them
- `ratings`: ratings added or changed on Trakt
- `not_found`: titles Trakt has no matching film for (see [Limitations](#limitations))

Running the import again later is safe; nothing is added twice.

## Everyday use

| Command | What it does |
| --- | --- |
| `python -m lbtrakt sync` | New Letterboxd diary entries → Trakt, then new Trakt plays → a Letterboxd import CSV in `export_dir` |
| `python -m lbtrakt run` | `sync` forever, every `interval_hours` (keeps going through network errors) |
| `python -m lbtrakt export-letterboxd --since 2026-01-01T00:00:00.000Z` | Export Trakt plays from a given time. The first `sync` only starts the clock; it never dumps your whole Trakt history |
| `python -m lbtrakt import-letterboxd <export.zip>` | Re-run the full import |
| `python -m lbtrakt auth` | Sign in to Trakt again |

Put `--dry-run` before any command to preview it without changing anything. `--config` and `--state` let you keep several setups side by side.

### Getting new Trakt watches into Letterboxd

When a film you watched through another app reaches Trakt, the next sync writes something like `exports/letterboxd-import-20260314-0900.csv`:

```
tmdbID,imdbID,Title,Year,WatchedDate,Rating10
949,tt0113277,Heat,1995,2026-03-13,9
```

Upload it at [letterboxd.com/import](https://letterboxd.com/import/), check the matches Letterboxd shows, and confirm. Each play is exported once; afterwards you can delete or move the file. When the entry then appears in your Letterboxd RSS feed, the tool recognises it as already on Trakt and leaves it alone.

## Running on a schedule

- **Linux / macOS (cron):** `crontab -e`, then
  ```
  0 */6 * * * cd /path/to/letterboxd-trakt-sync && python3 -m lbtrakt sync >> sync.log 2>&1
  ```
- **Windows (Task Scheduler):** create a basic task that runs every few hours, action *Start a program*: `python`, arguments `-m lbtrakt sync`, *Start in*: this folder.
- **Anywhere:** keep `python -m lbtrakt run` running in the background (tmux, screen, a systemd user service, …).
- **Batocera:** copy this folder to `/userdata/system/letterboxd-trakt-sync`, add `config.json`, run `python -m lbtrakt auth` there once over SSH, then:
  ```
  cp contrib/batocera/letterboxd_trakt_sync /userdata/system/services/
  batocera-services enable letterboxd_trakt_sync
  batocera-services start letterboxd_trakt_sync
  ```
  It starts with the system and logs to `/userdata/system/logs/letterboxd-trakt-sync.log`.

Don't run two copies against the same `state.json` at the same time (for example `run` in the background plus a manual `sync`); stop the background one first.

## How matching works

- **Dates:** diary entries keep their dates. Films marked watched on Letterboxd without a diary entry are added to Trakt on their release date (Trakt uses today if it has no release date). Those placeholder plays are never exported back to Letterboxd; a real rewatch later on is.
- **Identity:** films are matched by TMDb ID where available (the RSS feed has them), otherwise by title and year (the export doesn't). Punctuation differences ("The Godfather Part II" vs "The Godfather: Part II") and a one-year disagreement between the sites (festival vs release year) still match.
- **Search fallback:** titles Trakt can't find by name are looked up with Trakt's search and only accepted on an exact title match within a year, so a similarly named film is never picked by mistake.
- **Ratings:** Letterboxd half stars become Trakt ratings out of 10 (★★★½ → 7). The full import uses your current ratings; the RSS feed carries the rating given with each diary entry. Ratings Trakt already has at the same value aren't re-sent.
- **No loops:** everything that came from Letterboxd is remembered, so it's never written into an export file.

## Limitations

- **Movies only.** Letterboxd doesn't track TV episodes. Things Letterboxd lists as films but Trakt only has as shows (some anime series, for example) come back as `not_found` and are skipped.
- **Not synced:** reviews, likes, lists, tags and watchlists.
- **The RSS feed holds your latest 50 diary entries.** If the tool is off for a long stretch and you log more than that, run `import-letterboxd` with a fresh export to catch up.
- **Uploading to Letterboxd stays manual.** Letterboxd's terms don't allow bots on the website and its API is invite-only, so the tool prepares the file and you upload it.
- **Undated films get approximate dates** on Trakt (their release date), because Letterboxd doesn't record when you watched them.

## Troubleshooting

| Message | What to do |
| --- | --- |
| `Set trakt_client_id in config.json` | Create `config.json` from `config.example.json` and fill it in |
| `Not signed in to Trakt; run: python -m lbtrakt auth` | Run `auth` once |
| `HTTP 420: your Trakt account has reached its connected-app limit` | Free accounts allow one connected app: reuse that app's Client ID, disconnect it at trakt.tv/settings/connected_apps, or use VIP |
| `HTTP 401: Trakt sign-in is no longer valid` | The app was disconnected or the sign-in expired; run `auth` again |
| `Device code expired before it was approved` | Run `auth` again and enter the code within a few minutes |
| `Not a valid Letterboxd username` | Use the name from your profile URL (letters, digits, underscores) |
| `Error: HTTP Error 404` during sync | Check the username and that your Letterboxd profile is public |
| `No diary.csv or watched.csv found` | Pass the ZIP from Letterboxd's *Export your data*, or the folder you unzipped it to |
| A film shows under `not_found` | Usually a TV series on Trakt, or a film Trakt doesn't have yet; add it on trakt.tv by hand if you like |

Run any command with `--dry-run` to see what it would do.

## Security and privacy

- `config.json`, `state.json`, the exports folder and export ZIPs are in `.gitignore`. **Never commit or share `state.json`:** it holds your Trakt sign-in.
- `state.json` is created readable only by your user account. On Windows it inherits your user folder's permissions.
- The tool talks only to `letterboxd.com` (your public RSS feed) and `api.trakt.tv`, over HTTPS. It never asks for or stores your Letterboxd password, and it only uses your Trakt account for movie history and ratings.
- Your Letterboxd username is checked before it's put into a web address, and the sync interval can't go below an hour.
- To revoke access at any time, disconnect the app at [trakt.tv/settings/connected_apps](https://trakt.tv/settings/connected_apps) and delete `state.json`.

## Updating and uninstalling

- **Update:** `git pull` in this folder (then `pip install .` again if you installed it). Your `config.json` and `state.json` are kept. Restart a running `run` / service afterwards.
- **Uninstall:** stop any scheduled task or service, disconnect the app on Trakt, then delete this folder (`pip uninstall letterboxd-trakt-sync` if you installed it). On Batocera also run `batocera-services disable letterboxd_trakt_sync` and remove `/userdata/system/services/letterboxd_trakt_sync`.

Nothing the tool added to Trakt is removed on uninstall; your Trakt history stays as it is.

## Development

```
python -m unittest
```

The tests use a fake Trakt client and need no network or accounts. CI runs them on Linux and Windows with Python 3.9 and 3.13.

Code layout:

| File | Role |
| --- | --- |
| `lbtrakt/letterboxd.py` | Reads the RSS feed and export ZIP, writes Letterboxd import CSVs |
| `lbtrakt/trakt.py` | Small Trakt API client: device sign-in, token renewal, history, ratings, search |
| `lbtrakt/sync.py` | Matching and deduplication in both directions |
| `lbtrakt/__main__.py` | Command line |
| `contrib/batocera/` | Service script for Batocera |

Issues and pull requests are welcome. Please keep it dependency-free and add a test for any new matching rule.

## License

MIT
