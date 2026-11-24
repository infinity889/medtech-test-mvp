"""Offline unit tests for PoliteHttpClient (robots.txt, rate limit, retries)."""

import httpx
import pytest
import respx

from app.ingestion.http_client import (
    HttpFetchError,
    PoliteHttpClient,
    RobotsDisallowedError,
)


@respx.mock
async def test_robots_disallow_blocks_request_without_fetching_target() -> None:
    robots_route = respx.get("https://example.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
    )
    target_route = respx.get("https://example.kz/private/prices").mock(
        return_value=httpx.Response(200, text="secret")
    )

    async def no_sleep(_: float) -> None:
        return None

    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        with pytest.raises(RobotsDisallowedError) as exc_info:
            await client.get("https://example.kz/private/prices")

    assert exc_info.value.url == "https://example.kz/private/prices"
    assert robots_route.call_count == 1
    assert target_route.call_count == 0


@respx.mock
async def test_robots_cached_per_domain_and_sends_user_agent() -> None:
    robots_route = respx.get("https://clinic.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    page_a = respx.get("https://clinic.kz/a").mock(return_value=httpx.Response(200, text="A"))
    page_b = respx.get("https://clinic.kz/b").mock(return_value=httpx.Response(200, text="B"))

    async def no_sleep(_: float) -> None:
        return None

    ua = "MedServicePriceBot/0.1 (+https://medserviceprice.kz)"
    async with PoliteHttpClient(
        user_agent=ua, min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep
    ) as client:
        resp_a = await client.get("https://clinic.kz/a")
        resp_b = await client.get("https://clinic.kz/b")

    assert resp_a.text == "A"
    assert resp_b.text == "B"
    assert robots_route.call_count == 1
    assert page_a.calls[0].request.headers["User-Agent"] == ua
    assert page_b.calls[0].request.headers["User-Agent"] == ua


@respx.mock
async def test_robots_404_allows_crawling() -> None:
    respx.get("https://norobots.kz/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://norobots.kz/prices").mock(return_value=httpx.Response(200, text="ok"))

    async def no_sleep(_: float) -> None:
        return None

    async with PoliteHttpClient(min_delay_sec=1.5, max_jitter_sec=0.0, sleep_fn=no_sleep) as client:
        resp = await client.get("https://norobots.kz/prices")

    assert resp.status_code == 200
    assert resp.text == "ok"


@respx.mock
async def test_per_domain_rate_limit_sleeps_remaining_delay() -> None:
    respx.get("https://lab.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://lab.kz/p1").mock(return_value=httpx.Response(200, text="1"))
    respx.get("https://lab.kz/p2").mock(return_value=httpx.Response(200, text="2"))

    current_time = 100.0
    recorded_sleeps: list[float] = []

    def fake_clock() -> float:
        return current_time

    async def fake_sleep(seconds: float) -> None:
        nonlocal current_time
        recorded_sleeps.append(seconds)
        current_time += seconds

    async with PoliteHttpClient(
        min_delay_sec=1.5,
        max_jitter_sec=0.0,
        sleep_fn=fake_sleep,
        clock_fn=fake_clock,
    ) as client:
        await client.get("https://lab.kz/p1")
        # Advance only 0.4s before next request to same domain
        current_time += 0.4
        await client.get("https://lab.kz/p2")

    assert len(recorded_sleeps) == 1
    assert pytest.approx(recorded_sleeps[0], abs=1e-6) == 1.1


@respx.mock
async def test_retries_on_transient_429_and_503_then_succeeds() -> None:
    respx.get("https://flaky.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    route = respx.get("https://flaky.kz/prices").mock(
        side_effect=[
            httpx.Response(429, text="Too Many Requests"),
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, text="recovered"),
        ]
    )

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async with PoliteHttpClient(
        min_delay_sec=1.5,
        max_jitter_sec=0.0,
        max_retries=3,
        sleep_fn=fake_sleep,
    ) as client:
        resp = await client.get("https://flaky.kz/prices")

    assert resp.text == "recovered"
    assert route.call_count == 3
    assert len(sleeps) >= 2


@respx.mock
async def test_exhausted_retries_raises_http_fetch_error() -> None:
    respx.get("https://down.kz/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    route = respx.get("https://down.kz/prices").mock(return_value=httpx.Response(503))

    async def no_sleep(_: float) -> None:
        return None

    async with PoliteHttpClient(
        min_delay_sec=1.5,
        max_jitter_sec=0.0,
        max_retries=2,
        sleep_fn=no_sleep,
    ) as client:
        with pytest.raises(HttpFetchError) as exc_info:
            await client.get("https://down.kz/prices")

    assert route.call_count == 3
    assert exc_info.value.status_code == 503
    assert exc_info.value.url == "https://down.kz/prices"
