"""Sync logic between Letterboxd watches and Trakt movie history.

state (a dict saved as JSON) remembers:
  lb_seen         identity keys of every Letterboxd viewing, so they are never exported back
  synced_guids    RSS entries already pushed to Trakt
  export_since    Trakt plays after this time are exported to Letterboxd
  exported_ids    Trakt history ids already written to an import file
"""
import os
from datetime import date, datetime, timedelta, timezone

from .letterboxd import import_csv_chunks


def local_date(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().date().isoformat()


def play_keys(play, any_date=True):
    """Identity keys for a Trakt history item. '?' keys let undated Letterboxd films match any play."""
    m = play["movie"]
    day = local_date(play["watched_at"])
    keys = {f"d:{m['title'].casefold()}|{day}"}
    for d in (day, "?") if any_date else (day,):
        keys.add(f"t:{m['title'].casefold()}|{m.get('year')}|{d}")
        if m["ids"].get("tmdb"):
            keys.add(f"tmdb:{m['ids']['tmdb']}|{d}")
    return keys


def _movie_ref(w):
    if w.tmdb:
        return {"ids": {"tmdb": w.tmdb}}
    return {"title": w.title, "year": w.year}


def letterboxd_to_trakt(trakt, watches, state, sync_ratings=True, dry_run=False):
    synced = set(state.get("synced_guids", []))
    watches = [w for w in watches if not (w.source_id and w.source_id in synced)]
    summary = {"checked": len(watches), "added": 0, "already_on_trakt": 0, "ratings": 0, "not_found": []}
    if not watches:
        return summary

    dates = [w.date for w in watches]
    # a day early so time-zone shifts can't hide a same-day play; undated films need full history
    start = None if None in dates else (date.fromisoformat(min(dates)) - timedelta(days=1)).isoformat() + "T00:00:00.000Z"
    existing = set()
    for play in trakt.movie_history(start_at=start):
        existing |= play_keys(play)

    new = [w for w in watches if not (w.keys() & existing)]
    summary["already_on_trakt"] = len(watches) - len(new)
    history = [dict(_movie_ref(w), watched_at=f"{w.date}T12:00:00.000Z" if w.date else "released") for w in new]

    ratings = []
    if sync_ratings:
        current = {}
        for r in trakt.movie_ratings():
            m = r["movie"]
            current[m["ids"].get("tmdb")] = current[(m["title"].casefold(), m.get("year"))] = r["rating"]
        latest = {}
        for w in watches:  # later entries win, so the newest Letterboxd rating is kept
            if w.rating:
                latest[w.tmdb or (w.title.casefold(), w.year)] = w
        for key, w in latest.items():
            r10 = max(1, min(10, round(w.rating * 2)))
            if current.get(key) != r10:
                ratings.append(dict(_movie_ref(w), rating=r10))

    if not dry_run:
        if history:
            res = trakt.add_history(history)
            summary["added"], summary["not_found"] = res["added"], res["not_found"]
        if ratings:
            summary["ratings"] = trakt.add_ratings(ratings)["added"]
        seen = set(state.get("lb_seen", []))
        for w in watches:
            seen |= w.keys()
            if w.source_id:
                synced.add(w.source_id)
        state["lb_seen"], state["synced_guids"] = sorted(seen), sorted(synced)
    else:
        summary["added"], summary["ratings"] = len(history), len(ratings)
    return summary


def trakt_to_letterboxd(trakt, state, out_dir, since=None, now=None, dry_run=False):
    """Write a Letterboxd import CSV of Trakt movie plays that didn't come from Letterboxd."""
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    since = since or state.get("export_since")
    if not since:  # first run: start from now rather than dumping the whole Trakt history
        if not dry_run:
            state["export_since"] = now
        return {"exported": 0, "files": [], "note": "first run, exporting plays from now on"}

    seen = set(state.get("lb_seen", []))
    done = set(state.get("exported_ids", []))
    ratings = {r["movie"]["ids"].get("tmdb"): r["rating"] for r in trakt.movie_ratings()}
    rows, ids = [], []
    for play in reversed(trakt.movie_history(start_at=since)):  # oldest first
        # dated keys only: a Trakt rewatch of a film Letterboxd has without a date still exports
        if play["id"] in done or play_keys(play, any_date=False) & seen:
            continue
        m = play["movie"]
        rows.append({
            "tmdbID": m["ids"].get("tmdb") or "",
            "imdbID": m["ids"].get("imdb") or "",
            "Title": m["title"],
            "Year": m.get("year") or "",
            "WatchedDate": local_date(play["watched_at"]),
            "Rating10": ratings.get(m["ids"].get("tmdb"), ""),
        })
        ids.append(play["id"])

    files = []
    if rows and not dry_run:
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        for n, text in enumerate(import_csv_chunks(rows), 1):
            path = os.path.join(out_dir, f"letterboxd-import-{stamp}{'-%d' % n if n > 1 else ''}.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            files.append(path)
    if not dry_run:
        state["exported_ids"] = sorted(done | set(ids))
        state["export_since"] = now
    return {"exported": len(rows), "files": files}
