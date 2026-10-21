# letterboxd-trakt-sync

Keep your movie history in step between [Letterboxd](https://letterboxd.com) and [Trakt](https://trakt.tv).

- **Letterboxd → Trakt:** a one-time import of your full Letterboxd history, then new diary entries every few hours from your public Letterboxd RSS feed. Watches and ratings are copied; anything already on Trakt is skipped.
- **Trakt → Letterboxd:** Letterboxd has no public API for adding watches, so new Trakt movie plays are written to a CSV in Letterboxd's import format. Upload it at [letterboxd.com/import](https://letterboxd.com/import/). Plays that came from Letterboxd are never exported back.

Movies only (Letterboxd doesn't track TV). Pure Python 3.9+ standard library, so it runs anywhere Python does, including small boxes like a Batocera or Raspberry Pi media PC.

## Setup

1. **Create a Trakt app** at [developer.trakt.tv](https://developer.trakt.tv) → My Apps → New app. Any name, type *Development*, redirect URI `http://localhost`. Copy its **Client ID**. (Apps created since 2026 get no client secret; leave `trakt_client_secret` empty. Older apps can put theirs in.)
2. **Configure:** copy `config.example.json` to `config.json` and fill in your Letterboxd username and Trakt Client ID. Your Letterboxd profile must be public for the RSS feed to work.
3. **Sign in to Trakt:**
   ```
   python -m lbtrakt auth
   ```
   Enter the code it shows at the Trakt activation page. Tokens are saved to `state.json` (readable only by you) and renewed automatically.

## Use

| Command | What it does |
| --- | --- |
| `python -m lbtrakt import-letterboxd letterboxd-export.zip` | One-time import of your whole Letterboxd history. Get the ZIP from Letterboxd → Settings → Import & Export → Export your data. |
| `python -m lbtrakt sync` | Letterboxd RSS → Trakt, then new Trakt plays → `exports/letterboxd-import-*.csv` |
| `python -m lbtrakt export-letterboxd --since 2026-01-01T00:00:00.000Z` | Export Trakt plays from a given time (the first `sync` only starts the clock, it never dumps your whole Trakt history) |
| `python -m lbtrakt run` | Run `sync` forever, every `interval_hours` |

Add `--dry-run` before the command to see what would change without changing anything.

Diary entries keep their dates. Films marked watched on Letterboxd without a diary date are added to Trakt on their release date. Letterboxd half-star ratings become Trakt ratings out of 10 (★★★½ → 7).

## Running it on a schedule

Any scheduler works: cron, a systemd timer, or `python -m lbtrakt run` in the background.

**Batocera:** copy this folder to `/userdata/system/letterboxd-trakt-sync`, add `config.json`, run `auth` once over SSH, then:
```
cp contrib/batocera/letterboxd_trakt_sync /userdata/system/services/
batocera-services enable letterboxd_trakt_sync
batocera-services start letterboxd_trakt_sync
```
Logs go to `/userdata/system/logs/letterboxd-trakt-sync.log`.

## Tests

```
python -m unittest
```

## Privacy

Your config, Trakt tokens and exports stay on your machine and are git-ignored. The tool only talks to `letterboxd.com` (public RSS) and `api.trakt.tv`.
