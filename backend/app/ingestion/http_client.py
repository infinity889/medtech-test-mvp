"""Polite async HTTP client with robots.txt enforcement, rate limiting, and retries."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

DEFAULT_USER_AGENT = (
    "MedServicePriceBot/0.1 (+https://medserviceprice.kz; public-price-aggregator)"
)
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class RobotsDisallowedError(Exception):
    """Raised when robots.txt forbids fetching the target URL."""

    def __init__(self, url: str, message: str | None = None) -> None:
        self.url = url
        super().__init__(message or f"Blocked by robots.txt: {url}")


class HttpFetchError(Exception):
    """Raised when an HTTP request fails permanently after retries."""

    def __init__(
        self,
        url: str,
        message: str,
        status_code: int | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        super().__init__(message)


class PoliteHttpClient:
    """Async HTTP client that respects robots.txt, per-domain rate limits, and TLS."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        min_delay_sec: float = 1.5,
        max_jitter_sec: float = 0.5,
        timeout_sec: float = 20.0,
        max_retries: int = 3,
        backoff_base_sec: float = 1.0,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_delay_sec < 1.5:
            raise ValueError("min_delay_sec must be >= 1.5 seconds to protect target sites")
        if max_jitter_sec < 0:
            raise ValueError("max_jitter_sec must be >= 0")

        self.user_agent = user_agent
        self.min_delay_sec = min_delay_sec
        self.max_jitter_sec = max_jitter_sec
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.backoff_base_sec = backoff_base_sec
        self._sleep = sleep_fn
        self._clock = clock_fn

        self._client: httpx.AsyncClient | None = None
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._last_request_at: dict[str, float] = {}
        self._robots_cache: dict[str, RobotFileParser | None] = {}

    async def __aenter__(self) -> PoliteHttpClient:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=httpx.Timeout(self.timeout_sec),
            follow_redirects=True,
            verify=True,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("PoliteHttpClient must be used inside an 'async with' block")
        return self._client

    def _get_domain_lock(self, domain: str) -> asyncio.Lock:
        lock = self._domain_locks.get(domain)
        if lock is None:
            lock = asyncio.Lock()
            self._domain_locks[domain] = lock
        return lock

    async def _ensure_robots_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self._robots_cache:
            robots_url = f"{origin}/robots.txt"
            client = self._require_client()
            try:
                response = await client.get(robots_url)
            except httpx.HTTPError as exc:
                raise HttpFetchError(
                    robots_url, f"Failed to fetch robots.txt: {exc}"
                ) from exc

            if response.status_code == 404:
                self._robots_cache[origin] = None
            elif 200 <= response.status_code < 300:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
                self._robots_cache[origin] = parser
            elif response.status_code >= 500:
                raise HttpFetchError(
                    robots_url,
                    f"robots.txt returned server error {response.status_code}",
                    status_code=response.status_code,
                )
            else:
                # 401/403 on robots.txt: conservatively treat as disallowed
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(["User-agent: *", "Disallow: /"])
                self._robots_cache[origin] = parser

        cached_parser = self._robots_cache[origin]
        if cached_parser is not None and not cached_parser.can_fetch(self.user_agent, url):
            raise RobotsDisallowedError(url)

    async def _wait_for_rate_limit(self, domain: str) -> None:
        last_ts = self._last_request_at.get(domain)
        if last_ts is None:
            return
        jitter = random.uniform(0.0, self.max_jitter_sec) if self.max_jitter_sec > 0 else 0.0
        required_wait = (self.min_delay_sec + jitter) - (self._clock() - last_ts)
        if required_wait > 0:
            await self._sleep(required_wait)

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Fetch a public URL respecting robots.txt, rate limits, and retries."""
        parsed = urlparse(url)
        domain = parsed.netloc
        lock = self._get_domain_lock(domain)

        async with lock:
            await self._ensure_robots_allowed(url)
            client = self._require_client()

            last_exc: Exception | None = None
            last_status: int | None = None

            for attempt in range(self.max_retries + 1):
                await self._wait_for_rate_limit(domain)
                try:
                    response = await client.get(url, params=params, headers=headers)
                    self._last_request_at[domain] = self._clock()
                except httpx.HTTPError as exc:
                    self._last_request_at[domain] = self._clock()
                    last_exc = exc
                    if attempt < self.max_retries:
                        await self._sleep(self.backoff_base_sec * (2**attempt))
                        continue
                    raise HttpFetchError(url, f"Network error fetching {url}: {exc}") from exc

                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_status = response.status_code
                    if attempt < self.max_retries:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            delay = float(retry_after)
                        else:
                            base = (
                                max(self.backoff_base_sec, 5.0)
                                if response.status_code == 429
                                else self.backoff_base_sec
                            )
                            delay = base * (2**attempt)
                        await self._sleep(delay)
                        continue
                    raise HttpFetchError(
                        url,
                        f"HTTP {response.status_code} after {self.max_retries + 1} attempts",
                        status_code=response.status_code,
                    )

                if response.status_code >= 400:
                    raise HttpFetchError(
                        url,
                        f"HTTP {response.status_code} fetching {url}",
                        status_code=response.status_code,
                    )

                return response

            raise HttpFetchError(
                url,
                f"Failed to fetch {url}: {last_exc or last_status}",
                status_code=last_status,
            )

    async def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        """Fetch URL and return decoded text."""
        response = await self.get(url, params=params, headers=headers)
        return response.text

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Fetch URL and return parsed JSON."""
        response = await self.get(url, params=params, headers=headers)
        return response.json()

    async def get_bytes(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        """Fetch URL and return raw bytes (for PDF/DOCX/XLSX)."""
        response = await self.get(url, params=params, headers=headers)
        return response.content
