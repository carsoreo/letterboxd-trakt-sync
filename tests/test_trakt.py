import unittest

from lbtrakt.trakt import Trakt


def result(title, year, tmdb):
    return {"movie": {"title": title, "year": year, "ids": {"tmdb": tmdb}}}


class FindMovie(unittest.TestCase):
    def find(self, results, title, year):
        t = Trakt("id")
        t._request = lambda *a, **k: (results, {})
        return t.find_movie(title, year)

    def test_punctuation_differences_match(self):
        self.assertEqual(self.find([result("The Godfather: Part II", 1974, 240)], "The Godfather Part II", 1974), {"tmdb": 240})
        self.assertEqual(self.find([result("Chainsaw Man - The Movie: Reze Arc", 2025, 1)],
                                   "Chainsaw Man – The Movie: Reze Arc", 2025), {"tmdb": 1})

    def test_different_title_rejected(self):
        self.assertIsNone(self.find([result("Ping Pong Summer", 2014, 246011)], "Ping Pong the Animation", 2014))

    def test_year_must_be_close(self):
        self.assertIsNone(self.find([result("Halloween", 1978, 948)], "Halloween", 2018))
        self.assertEqual(self.find([result("Sound of Metal", 2020, 5)], "Sound of Metal", 2019), {"tmdb": 5})


if __name__ == "__main__":
    unittest.main()
