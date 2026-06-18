"""Small throttled + retrying HTTP helper shared by V1/V2. Polite by default so we
don't trip rate limits on IEM/NCEI/Open-Meteo."""
from __future__ import annotations

import time

import requests

UA = "kalshi-weather-edge/0.0 (research-validation)"


class Http:
    def __init__(self, min_interval: float = 0.2, max_retries: int = 4, timeout: int = 60):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last = 0.0

    def _throttle(self) -> None:
        gap = time.time() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)

    def get(self, url: str, **params) -> requests.Response:
        last = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                r = self.s.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                last = e
                self._last = time.time()
                time.sleep(min(2 ** attempt, 8))
                continue
            self._last = time.time()
            if r.status_code == 429 or r.status_code >= 500:
                last = requests.HTTPError(f"{r.status_code} {url}")
                time.sleep(min(2 ** attempt, 8))
                continue
            r.raise_for_status()
            return r
        raise last or requests.HTTPError(f"exhausted retries {url}")

    def json(self, url: str, **params):
        return self.get(url, **params).json()

    def text(self, url: str, **params) -> str:
        return self.get(url, **params).text
