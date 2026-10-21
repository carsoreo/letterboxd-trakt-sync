# letterboxd-trakt-sync

Keep your movie history in step between [Letterboxd](https://letterboxd.com) and [Trakt](https://trakt.tv), so apps that read Trakt (media centers, recommendation tools, Trakt's own apps) know everything you've logged on Letterboxd, and films you watch elsewhere can land in your Letterboxd diary.

- **Letterboxd → Trakt (automatic):** a one-time import of your full Letterboxd history, then new diary entries every few hours from your public Letterboxd RSS feed. Watches and ratings are copied; anything already on Trakt is skipped.
- **Trakt → Letterboxd (one manual upload):** Letterboxd has no public API for adding watches, so new Trakt movie plays are written to a CSV in Letterboxd's own import format. You upload it at [letterboxd.com/import](https://letterboxd.com/import/). Films that came from Letterboxd are never exported back.

Pure Python standard library (3.9+), no dependencies. Runs on Windows, macOS, Linux, a Raspberry Pi or a media box like Batocera.

## Setup

**1. Get the code**

```
git clone https://github.com/carsoreo/letterboxd-trakt-sync
cd letterboxd-trakt-sync
```

Run commands from this folder as `python -m lbtrakt …`. Or install it (`pip install .`) and use the `lbtrakt` command from anywhere; it reads `config.json` from the current folder unless you pass `--config`.

**2. Make your Letterboxd profile public.** The ongoing sync reads `https://letterboxd.com/<username>/rss/`, which only works for public profiles.

**3. Create a Trakt app** at [developer.trakt.tv](https://developer.trakt.tv) → My Apps → New app: any name, type **Development**, redirect URI `http://localhost`. Copy its **Client ID**.

- Apps created since 2026 get no client secret; leave `trakt_client_secret` empty. Older apps can put theirs in.
- **Free Trakt accounts can only have one third-party app connected.** If another app (a media center add-on, for example) is already connected, either reuse that app's Client ID here, disconnect it, or use Trakt VIP. The tool tells you when you hit this limit.

**4. Configure:** copy `config.example.json` to `config.json` and fill it in.

| Setting | Meaning |
| --- | --- |
| `letterboxd_username` | Your Letterboxd username |
| `trakt_client_id` | Client ID from step 3 |
| `trakt_client_secret` | Leave empty unless your Trakt app has one |
| `export_dir` | Where Letterboxd import CSVs are written (relative to the config file, or absolute) |
| `sync_ratings` | Copy Letterboxd ratings to Trakt (`true`/`false`) |
| `interval_hours` | How often `run` syncs (minimum 1) |

**5. Sign in to Trakt:**

```
python -m lbtrakt auth
```

Enter the code it prints at the Trakt activation page. The sign-in is saved to `state.json` next to your config and renewed automatically.

**6. Import your full history once.** In Letterboxd go to Settings → Import & Export → **Export your data**, then:

```
python -m lbtrakt --dry-run import-letterboxd letterboxd-yourname-….zip
python -m lbtrakt import-letterboxd letterboxd-yourname-….zip
```

The first command shows what would change without changing anything.

## Everyday use

| Command | What it does |
| --- | --- |
| `python -m lbtrakt sync` | New Letterboxd diary entries → Trakt, then new Trakt plays → a Letterboxd import CSV in `export_dir` |
| `python -m lbtrakt run` | `sync` forever, every `interval_hours` |
| `python -m lbtrakt export-letterboxd --since 2026-01-01T00:00:00.000Z` | Export Trakt plays from a given time (the first `sync` only starts the clock; it never dumps your whole Trakt history) |
| `python -m lbtrakt import-letterboxd <export.zip>` | Re-run the full import; safe to repeat, nothing is added twice |

Add `--dry-run` before any command to preview it.

When a `letterboxd-import-*.csv` appears in `export_dir`, upload it at [letterboxd.com/import](https://letterboxd.com/import/) and review it there before confirming.

### Running on a schedule

- **Linux/macOS cron:** `0 */6 * * * cd /path/to/letterboxd-trakt-sync && python3 -m lbtrakt sync >> sync.log 2>&1`
- **Windows:** Task Scheduler → run `python -m lbtrakt sync` with "Start in" set to this folder.
- **Anywhere:** keep `python -m lbtrakt run` running in the background.
- **Batocera:** copy this folder to `/userdata/system/letterboxd-trakt-sync`, add `config.json`, run `auth` once over SSH, then:
  ```
  cp contrib/batocera/letterboxd_trakt_sync /userdata/system/services/
  batocera-services enable letterboxd_trakt_sync
  batocera-services start letterboxd_trakt_sync
  ```
  Logs go to `/userdata/system/logs/letterboxd-trakt-sync.log`.

## How matching works

- Diary entries keep their dates. Films marked watched on Letterboxd without a diary entry are added to Trakt on their release date (Trakt uses today if it has no release date). Those placeholder plays are never exported back to Letterboxd; a real rewatch later on is.
- Films are matched by TMDb ID where available, otherwise by title and year. Punctuation differences ("The Godfather Part II" vs "The Godfather: Part II") and a one-year disagreement between the sites (festival vs release year) still match.
- Titles Trakt can't find by name are looked up with Trakt's search and only accepted on an exact title match.
- Letterboxd half-star ratings become Trakt ratings out of 10 (★★★½ → 7). The full import uses your current ratings; the RSS feed carries the rating given with each diary entry.

## Limitations

- **Movies only.** Letterboxd doesn't track TV episodes. Things Letterboxd lists as films but Trakt only has as shows are reported as not found.
- **Reviews, likes, lists and watchlists are not synced.**
- The RSS feed holds your latest 50 diary entries, so if the tool is off for a long stretch, re-run `import-letterboxd` with a fresh export to catch up.
- Uploading to Letterboxd stays manual: Letterboxd's terms don't allow bots on the website, and its API is invite-only.

## Security and privacy

- `config.json`, `state.json` and the exports folder are in `.gitignore`. Never commit or share `state.json`: it holds your Trakt sign-in.
- `state.json` is created readable only by your user account (on Windows, it inherits your profile folder's permissions).
- The tool only talks to `letterboxd.com` (your public RSS feed) and `api.trakt.tv`. It never asks for your Letterboxd password.
- To revoke access, disconnect the app at [trakt.tv/settings/connected_apps](https://trakt.tv/settings/connected_apps) and delete `state.json`.

## Development

```
python -m unittest
```

Tests use a fake Trakt client and need no network or accounts. CI runs them on Linux and Windows with Python 3.9 and 3.13.

## License

MIT
