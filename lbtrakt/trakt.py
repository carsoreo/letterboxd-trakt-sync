"""Small Trakt API client: device sign-in, token refresh, movie history and ratings."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .letterboxd import USER_AGENT, norm

API = "https://api.trakt.tv"
POST_BATCH = 500

# plain-language hints for Trakt's account-level errors
HINTS = {
    401: "Trakt sign-in is no longer valid; run: python -m lbtrakt auth",
    420: "your Trakt account has reached its connected-app limit (free accounts allow one). "
         "Disconnect an app at trakt.tv/settings/connected_apps, reuse the Client ID of an app you "
         "already connected, or upgrade to Trakt VIP",
    423: "your Trakt account is locked; check trakt.tv",
    426: "this needs Trakt VIP",
}


class TraktError(Exception):
    pass


class Trakt:
    def __init__(self, client_id, client_secret=None, tokens=None, on_tokens=None):
        self.client_id = client_id
        self.client_secret = client_secret or None
        self.tokens = tokens or {}
        self.on_tokens = on_tokens or (lambda t: None)  # called whenever tokens change, to save them

    # --- HTTP ---------------------------------------------------------------
    def _request(self, method, path, body=None, auth=True, params=None, retries=3):
        url = API + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self.client_id,
            "User-Agent": USER_AGENT,
        }
        if auth:
            headers["Authorization"] = "Bearer " + self._access_token()
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return (json.loads(raw) if raw else None), resp.headers
        except urllib.error.HTTPError as e:
            if e.code == 429 and retries:
                time.sleep(int(e.headers.get("Retry-After", "2")) + 1)
                return self._request(method, path, body, auth, params, retries - 1)
            detail = HINTS.get(e.code) or e.read().decode(errors="replace")[:300]
            raise TraktError(f"{method} {path} -> HTTP {e.code}: {detail}") from None

    def _post_token(self, path, body):
        # New Trakt apps (2026+) get no secret; older apps still send theirs
        if self.client_secret:
            body["client_secret"] = self.client_secret
        result, _ = self._request("POST", path, body, auth=False)
        return result

    def _save(self, result):
        self.tokens = {
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "expires_at": int(result.get("created_at", time.time())) + int(result["expires_in"]),
        }
        self.on_tokens(self.tokens)

    # --- auth ---------------------------------------------------------------
    def device_login(self, show=print):
        code, _ = self._request("POST", "/oauth/device/code", {"client_id": self.client_id}, auth=False)
        show(f"Go to {code['verification_url']} and enter code: {code['user_code']}")
        deadline = time.time() + code["expires_in"]
        while time.time() < deadline:
            time.sleep(code["interval"])
            try:
                result = self._post_token("/oauth/device/token",
                                          {"code": code["device_code"], "client_id": self.client_id})
            except TraktError as e:
                if "HTTP 400" in str(e):  # still waiting for the user
                    continue
                raise
            if result:
                self._save(result)
                return
        raise TraktError("Device code expired before it was approved; run auth again.")

    def refresh(self):
        result = self._post_token("/oauth/token", {
            "refresh_token": self.tokens["refresh_token"],
            "client_id": self.client_id,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            "grant_type": "refresh_token",
        })
        self._save(result)

    def _access_token(self):
        if not self.tokens.get("access_token"):
            raise TraktError("Not signed in to Trakt; run: python -m lbtrakt auth")
        if self.tokens.get("expires_at", 0) - time.time() < 24 * 3600:
            self.refresh()
        return self.tokens["access_token"]

    # --- data ---------------------------------------------------------------
    def movie_history(self, start_at=None):
        """All movie plays (newest first), optionally only since an ISO timestamp."""
        plays, page = [], 1
        while True:
            params = {"page": page, "limit": 1000}
            if start_at:
                params["start_at"] = start_at
            items, headers = self._request("GET", "/sync/history/movies", params=params)
            plays += items or []
            if page >= int(headers.get("X-Pagination-Page-Count", "1")):
                return plays
            page += 1

    def find_movie(self, title, year):
        """Trakt ids for a title whose exact name didn't match, allowing the year to be off by one."""
        items, _ = self._request("GET", "/search/movie", params={"query": title, "fields": "title", "limit": 10})
        for item in items or []:
            m = item["movie"]
            if norm(m["title"]) == norm(title) and (year is None or abs((m.get("year") or 0) - year) <= 1):
                return m["ids"]
        return None

    def movie_ratings(self):
        items, _ = self._request("GET", "/sync/ratings/movies")
        return items or []

    def _post_batches(self, path, key, items):
        totals = {"added": 0, "not_found": []}
        for i in range(0, len(items), POST_BATCH):
            result, _ = self._request("POST", path, {key: items[i:i + POST_BATCH]})
            totals["added"] += (result.get("added") or {}).get(key, 0)
            totals["not_found"] += (result.get("not_found") or {}).get(key, [])
            time.sleep(1)  # Trakt allows about one write per second
        return totals

    def add_history(self, movies):
        return self._post_batches("/sync/history", "movies", movies)

    def add_ratings(self, movies):
        return self._post_batches("/sync/ratings", "movies", movies)
