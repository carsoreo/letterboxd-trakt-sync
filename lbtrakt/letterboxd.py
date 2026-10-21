"""Reading Letterboxd data (RSS feed, export ZIP/CSV) and writing Letterboxd import CSVs."""
import csv
import io
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import Optional

NS = {"letterboxd": "https://letterboxd.com", "tmdb": "https://themoviedb.org"}
USER_AGENT = "letterboxd-trakt-sync/0.1 (+https://github.com/carsoreo/letterboxd-trakt-sync)"
IMPORT_FIELDS = ["tmdbID", "imdbID", "Title", "Year", "WatchedDate", "Rating10"]
MAX_IMPORT_BYTES = 1_000_000  # Letterboxd rejects import files over 1 MB


def norm(title):
    """Title for matching: lower case, punctuation ignored ("Part II" == ": Part II", en dash == hyphen)."""
    return " ".join(re.findall(r"\w+", title.casefold()))


@dataclass
class Watch:
    title: str
    year: Optional[int]
    date: Optional[str]            # YYYY-MM-DD, None = date unknown
    tmdb: Optional[int] = None
    imdb: Optional[str] = None
    rating: Optional[float] = None  # Letterboxd stars, 0.5 to 5
    rewatch: bool = False
    source_id: str = ""             # RSS guid, used to remember what was synced

    def keys(self):
        """Identity keys for spotting the same viewing on both services."""
        day = self.date or "?"
        out = {f"t:{norm(self.title)}|{self.year}|{day}"}
        # Letterboxd and Trakt sometimes disagree on the year by one (festival vs release year)
        if self.date:
            out.add(f"d:{norm(self.title)}|{day}")
        elif self.year:
            out |= {f"t:{norm(self.title)}|{self.year + d}|?" for d in (-1, 1)}
        if self.tmdb:
            out.add(f"tmdb:{self.tmdb}|{day}")
        return out


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_rss(xml_text):
    """Diary entries from a Letterboxd RSS feed. Reviews-only and list items are skipped."""
    watches = []
    for item in ET.fromstring(xml_text).iter("item"):
        date = item.findtext("letterboxd:watchedDate", namespaces=NS)
        title = item.findtext("letterboxd:filmTitle", namespaces=NS)
        if not date or not title:
            continue
        watches.append(Watch(
            title=title,
            year=_int(item.findtext("letterboxd:filmYear", namespaces=NS)),
            date=date,
            tmdb=_int(item.findtext("tmdb:movieId", namespaces=NS)),
            rating=_float(item.findtext("letterboxd:memberRating", namespaces=NS)),
            rewatch=item.findtext("letterboxd:rewatch", namespaces=NS) == "Yes",
            source_id=item.findtext("guid") or "",
        ))
    return watches


def fetch_rss(username, timeout=30):
    url = f"https://letterboxd.com/{username}/rss/"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_rss(resp.read().decode("utf-8"))


def _rows(text):
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def parse_export(diary_csv=None, watched_csv=None, ratings_csv=None):
    """Watches from a Letterboxd data export.

    diary.csv has dated viewings. watched.csv lists every film marked watched; films that
    never got a diary entry come back with date=None. ratings.csv fills in ratings.
    """
    ratings = {}
    for r in _rows(ratings_csv or ""):
        ratings[(r["Name"].casefold(), _int(r["Year"]))] = _float(r["Rating"])

    watches, dated = [], set()
    for r in _rows(diary_csv or ""):
        key = (r["Name"].casefold(), _int(r["Year"]))
        dated.add(key)
        watches.append(Watch(
            title=r["Name"], year=key[1], date=r.get("Watched Date") or r.get("Date"),
            rating=_float(r.get("Rating")) or ratings.get(key),
            rewatch=r.get("Rewatch", "").lower() == "yes",
        ))
    for r in _rows(watched_csv or ""):
        key = (r["Name"].casefold(), _int(r["Year"]))
        if key not in dated:
            watches.append(Watch(title=r["Name"], year=key[1], date=None, rating=ratings.get(key)))
    return watches


def read_export(path):
    """Load a Letterboxd export ZIP, or a folder/CSV taken out of one."""
    names = {"diary.csv": None, "watched.csv": None, "ratings.csv": None}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                # top level only: exports also hold deleted/ and orphaned/ copies of these files
                if n in names:
                    names[n] = z.read(n).decode("utf-8")
    else:
        import os
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        for base in names:
            p = os.path.join(folder, base)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    names[base] = f.read()
    if not names["diary.csv"] and not names["watched.csv"]:
        raise ValueError(f"No diary.csv or watched.csv found in {path}")
    return parse_export(names["diary.csv"], names["watched.csv"], names["ratings.csv"])


def import_csv_chunks(rows):
    """Letterboxd import CSV text, split into files under the 1 MB limit (header repeated)."""
    header = io.StringIO()
    csv.DictWriter(header, IMPORT_FIELDS).writeheader()
    chunks, buf = [], header.getvalue()
    for row in rows:
        line = io.StringIO()
        csv.DictWriter(line, IMPORT_FIELDS).writerow(row)
        if len(buf.encode()) + len(line.getvalue().encode()) > MAX_IMPORT_BYTES:
            chunks.append(buf)
            buf = header.getvalue()
        buf += line.getvalue()
    if buf != header.getvalue():
        chunks.append(buf)
    return chunks
