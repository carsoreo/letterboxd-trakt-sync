"""Command line: python -m lbtrakt [--config config.json] <command>"""
import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime

from . import letterboxd, sync
from .trakt import Trakt, TraktError

DEFAULTS = {"letterboxd_username": "", "trakt_client_id": "", "trakt_client_secret": "",
            "export_dir": "exports", "sync_ratings": True, "interval_hours": 6}


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def load_json(path, default):
    if not os.path.exists(path):
        return dict(default)
    with open(path, encoding="utf-8") as f:
        return {**default, **json.load(f)}


def save_state(path, state):
    tmp = path + ".tmp"
    # holds Trakt tokens: create it owner-only from the start, then swap it in atomically
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, path)


def main(argv=None):
    p = argparse.ArgumentParser(prog="lbtrakt", description="Sync Letterboxd and Trakt movie history.")
    p.add_argument("--config", default="config.json")
    p.add_argument("--state", help="defaults to state.json next to the config")
    p.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth", help="sign in to Trakt with a device code")
    imp = sub.add_parser("import-letterboxd", help="one-time import of a Letterboxd export (ZIP or folder) into Trakt")
    imp.add_argument("path")
    sub.add_parser("sync", help="Letterboxd RSS -> Trakt, then Trakt -> Letterboxd import CSV")
    exp = sub.add_parser("export-letterboxd", help="only write the Letterboxd import CSV")
    exp.add_argument("--since", help="ISO time, e.g. 2026-01-01T00:00:00.000Z (default: last export)")
    sub.add_parser("run", help="run sync forever, every interval_hours")
    args = p.parse_args(argv)

    cfg = load_json(args.config, DEFAULTS)
    if not cfg["trakt_client_id"]:
        sys.exit(f"Set trakt_client_id in {args.config} (see config.example.json)")
    cfg["interval_hours"] = max(1, float(cfg["interval_hours"]))  # be gentle with Letterboxd and Trakt
    base = os.path.dirname(os.path.abspath(args.config))
    state_path = args.state or os.path.join(base, "state.json")
    state = load_json(state_path, {})
    out_dir = os.path.join(base, cfg["export_dir"])

    def store_tokens(tokens):
        state["trakt_tokens"] = tokens
        save_state(state_path, state)

    trakt = Trakt(cfg["trakt_client_id"], cfg["trakt_client_secret"], state.get("trakt_tokens"), store_tokens)

    def run_sync():
        if not cfg["letterboxd_username"]:
            sys.exit(f"Set letterboxd_username in {args.config}")
        watches = letterboxd.fetch_rss(cfg["letterboxd_username"])
        log(f"Letterboxd -> Trakt: {sync.letterboxd_to_trakt(trakt, watches, state, cfg['sync_ratings'], args.dry_run)}")
        log(f"Trakt -> Letterboxd: {sync.trakt_to_letterboxd(trakt, state, out_dir, dry_run=args.dry_run)}")

    try:
        if args.cmd == "auth":
            trakt.device_login(show=log)
            log("Signed in to Trakt.")
        elif args.cmd == "import-letterboxd":
            watches = letterboxd.read_export(args.path)
            log(f"Read {len(watches)} Letterboxd entries from {args.path}")
            log(f"Letterboxd -> Trakt: {sync.letterboxd_to_trakt(trakt, watches, state, cfg['sync_ratings'], args.dry_run)}")
        elif args.cmd == "export-letterboxd":
            log(f"Trakt -> Letterboxd: {sync.trakt_to_letterboxd(trakt, state, out_dir, since=args.since, dry_run=args.dry_run)}")
        elif args.cmd == "sync":
            run_sync()
        elif args.cmd == "run":
            while True:
                try:
                    run_sync()
                    if not args.dry_run:
                        save_state(state_path, state)
                except (TraktError, OSError, ET.ParseError) as e:  # network hiccups shouldn't kill the loop
                    log(f"sync failed, will retry next round: {e}")
                time.sleep(cfg["interval_hours"] * 3600)
    except TraktError as e:
        sys.exit(f"Trakt error: {e}")
    except (ValueError, OSError, ET.ParseError) as e:
        sys.exit(f"Error: {e}")
    if not args.dry_run:
        save_state(state_path, state)


if __name__ == "__main__":
    main()
