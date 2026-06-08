from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EdgarClient:
    base_data_url = "https://data.sec.gov"

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        max_requests_per_second: float = 8,
    ) -> None:
        self.cache_dir = cache_dir
        self.user_agent = user_agent
        self.min_interval = 1.0 / max_requests_per_second
        self._last_request_at = 0.0
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def cik10(cik: str | int) -> str:
        digits = "".join(ch for ch in str(cik) if ch.isdigit())
        if not digits:
            raise ValueError(f"Invalid CIK: {cik!r}")
        return digits.zfill(10)

    @staticmethod
    def compact_cik(cik: str | int) -> str:
        return str(int("".join(ch for ch in str(cik) if ch.isdigit())))

    def company_tickers(self, refresh: bool = False) -> Dict[str, Any]:
        return self.get_json("https://www.sec.gov/files/company_tickers.json", refresh=refresh)

    def submissions(self, cik: str | int, refresh: bool = False) -> Dict[str, Any]:
        return self.get_json(
            f"{self.base_data_url}/submissions/CIK{self.cik10(cik)}.json",
            refresh=refresh,
        )

    def companyfacts(self, cik: str | int, refresh: bool = False) -> Dict[str, Any]:
        return self.get_json(
            f"{self.base_data_url}/api/xbrl/companyfacts/CIK{self.cik10(cik)}.json",
            refresh=refresh,
        )

    def get_json(self, url: str, refresh: bool = False) -> Dict[str, Any]:
        cache_path = self._cache_path(url, "json")
        if cache_path.exists() and not refresh:
            return json.loads(cache_path.read_text())

        payload = self._request_json(url)
        cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return payload

    def get_text(self, url: str, refresh: bool = False) -> str:
        cache_path = self._cache_path(url, "txt")
        if cache_path.exists() and not refresh:
            return cache_path.read_text(errors="replace")

        payload = self._request_text(url, accept="text/html,application/xhtml+xml,text/plain")
        cache_path.write_text(payload)
        return payload

    def _request_json(self, url: str) -> Dict[str, Any]:
        return json.loads(self._request_text(url, accept="application/json"))

    def _request_text(self, url: str, accept: str) -> str:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": accept,
                "Accept-Encoding": "identity",
            },
        )
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                with urlopen(request, timeout=30) as response:
                    self._last_request_at = time.monotonic()
                    return response.read().decode("utf-8", errors="replace")
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504}:
                    raise
            except URLError as exc:
                last_error = exc
            time.sleep(2**attempt)
        if last_error:
            raise last_error
        raise RuntimeError(f"Failed to fetch {url}")

    def _cache_path(self, url: str, suffix: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.{suffix}"
