import os
import tempfile
import unittest

from lbtrakt import letterboxd, sync
from lbtrakt.letterboxd import Watch

RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:letterboxd="https://letterboxd.com" xmlns:tmdb="https://themoviedb.org"><channel>
<item><title>Heat, 1995 - ★★★★½</title><guid>letterboxd-watch-1</guid>
 <letterboxd:watchedDate>2026-10-20</letterboxd:watchedDate><letterboxd:rewatch>Yes</letterboxd:rewatch>
 <letterboxd:filmTitle>Heat</letterboxd:filmTitle><letterboxd:filmYear>1995</letterboxd:filmYear>
 <letterboxd:memberRating>4.5</letterboxd:memberRating><tmdb:movieId>949</tmdb:movieId></item>
<item><title>A list</title><guid>letterboxd-list-9</guid></item>
<item><title>Review only</title><guid>letterboxd-review-3</guid><letterboxd:filmTitle>Alien</letterboxd:filmTitle></item>
</channel></rss>"""

DIARY = "﻿Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date\n" \
        "2026-01-02,Heat,1995,https://boxd.it/x,4.5,,,2026-01-01\n"
WATCHED = "Date,Name,Year,Letterboxd URI\n2026-01-02,Heat,1995,https://boxd.it/x\n2025-05-05,Alien,1979,https://boxd.it/y\n"
RATINGS = "Date,Name,Year,Letterboxd URI,Rating\n2025-05-05,Alien,1979,https://boxd.it/y,5\n"


def play(pid, tmdb, title, year, when):
    return {"id": pid, "watched_at": when, "movie": {"title": title, "year": year, "ids": {"tmdb": tmdb, "imdb": "tt1"}}}


class FakeTrakt:
    def __init__(self, history=(), ratings=()):
        self.history, self.ratings = list(history), list(ratings)
        self.added_history, self.added_ratings = [], []

    def movie_history(self, start_at=None):
        return [p for p in self.history if not start_at or p["watched_at"] >= start_at]

    def movie_ratings(self):
        return self.ratings

    def add_history(self, movies):
        self.added_history += movies
        return {"added": len(movies), "not_found": []}

    def add_ratings(self, movies):
        self.added_ratings += movies
        return {"added": len(movies), "not_found": []}


class LetterboxdParsing(unittest.TestCase):
    def test_rss_keeps_only_diary_entries(self):
        w = letterboxd.parse_rss(RSS)
        self.assertEqual(len(w), 1)
        self.assertEqual((w[0].title, w[0].year, w[0].date, w[0].tmdb, w[0].rating, w[0].rewatch, w[0].source_id),
                         ("Heat", 1995, "2026-10-20", 949, 4.5, True, "letterboxd-watch-1"))

    def test_export_merges_diary_watched_and_ratings(self):
        w = {(x.title, x.date): x for x in letterboxd.parse_export(DIARY, WATCHED, RATINGS)}
        self.assertEqual(set(w), {("Heat", "2026-01-01"), ("Alien", None)})  # Heat not duplicated
        self.assertEqual(w[("Alien", None)].rating, 5.0)

    def test_import_csv_splits_under_limit(self):
        rows = [{"tmdbID": i, "imdbID": "", "Title": "x" * 200, "Year": 2000, "WatchedDate": "2026-01-01", "Rating10": ""}
                for i in range(6000)]
        chunks = letterboxd.import_csv_chunks(rows)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c.encode()), letterboxd.MAX_IMPORT_BYTES)
            self.assertTrue(c.startswith("tmdbID,"))
        self.assertEqual(sum(c.count("\n") - 1 for c in chunks), 6000)


class LetterboxdToTrakt(unittest.TestCase):
    def test_adds_new_skips_existing_and_remembers(self):
        t = FakeTrakt(history=[play(1, 949, "Heat", 1995, "2026-10-20T12:00:00.000Z")])
        state = {}
        new = Watch("Alien", 1979, "2026-10-19", tmdb=348, rating=5.0, source_id="g2")
        dup = Watch("Heat", 1995, "2026-10-20", tmdb=949, source_id="g1")
        s = sync.letterboxd_to_trakt(t, [dup, new], state)
        self.assertEqual((s["added"], s["already_on_trakt"]), (1, 1))
        self.assertEqual(t.added_history, [{"ids": {"tmdb": 348}, "watched_at": "2026-10-19T12:00:00.000Z"}])
        self.assertEqual(t.added_ratings, [{"ids": {"tmdb": 348}, "rating": 10}])
        # second run: guids remembered, nothing re-sent
        s2 = sync.letterboxd_to_trakt(t, [dup, new], state)
        self.assertEqual(s2["checked"], 0)

    def test_undated_watch_matches_any_play_and_uses_release_date(self):
        t = FakeTrakt(history=[play(1, 949, "Heat", 1995, "2020-01-01T20:00:00.000Z")])
        s = sync.letterboxd_to_trakt(t, [Watch("Heat", 1995, None), Watch("Alien", 1979, None)], {}, sync_ratings=False)
        self.assertEqual(s["added"], 1)
        self.assertEqual(t.added_history, [{"title": "Alien", "year": 1979, "watched_at": "released"}])

    def test_unchanged_rating_not_resent(self):
        t = FakeTrakt(ratings=[{"rating": 9, "movie": {"ids": {"tmdb": 949}}}])
        sync.letterboxd_to_trakt(t, [Watch("Heat", 1995, "2026-10-20", tmdb=949, rating=4.5)], {})
        self.assertEqual(t.added_ratings, [])

    def test_dry_run_changes_nothing(self):
        t, state = FakeTrakt(), {}
        s = sync.letterboxd_to_trakt(t, [Watch("Heat", 1995, "2026-10-20", tmdb=949)], state, dry_run=True)
        self.assertEqual((s["added"], t.added_history, state), (1, [], {}))


class TraktToLetterboxd(unittest.TestCase):
    def test_first_run_only_sets_watermark(self):
        state = {}
        s = sync.trakt_to_letterboxd(FakeTrakt(), state, "unused", now="2026-10-21T00:00:00.000Z")
        self.assertEqual((s["exported"], state["export_since"]), (0, "2026-10-21T00:00:00.000Z"))

    def test_exports_trakt_only_plays_once(self):
        t = FakeTrakt(history=[  # newest first, like the API
            play(3, 348, "Alien", 1979, "2026-10-21T02:00:00.000Z"),
            play(2, 949, "Heat", 1995, "2026-10-20T16:00:00.000Z"),
        ], ratings=[{"rating": 8, "movie": {"ids": {"tmdb": 348}}}])
        state = {"export_since": "2026-10-01T00:00:00.000Z"}
        sync.letterboxd_to_trakt(t, [Watch("Heat", 1995, "2026-10-20", tmdb=949)], state)  # Heat came from Letterboxd
        with tempfile.TemporaryDirectory() as d:
            s = sync.trakt_to_letterboxd(t, state, d, now="2026-10-22T00:00:00.000Z")
            self.assertEqual(s["exported"], 1)
            with open(s["files"][0], encoding="utf-8") as f:
                text = f.read()
            self.assertIn("348,tt1,Alien,1979,", text)
            self.assertIn(",8", text)
            self.assertNotIn("Heat", text)
            again = sync.trakt_to_letterboxd(t, state, d, since="2026-10-01T00:00:00.000Z")
            self.assertEqual(again["exported"], 0)  # play id remembered
            self.assertEqual(len(os.listdir(d)), 1)


if __name__ == "__main__":
    unittest.main()
