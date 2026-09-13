"""Small optional client for SolveGate's Cloudflare WAF API.

The normal pipeline does not import this module's network path unless a
location explicitly configures ``scrape.challenge``.  WAF clearance is
short-lived session material and is intentionally never persisted.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Mapping


SOLVE_URL = "https://api.solvegate.io/v1/solve"


class SolveGateError(Exception):
    """A safe, user-facing SolveGate failure (never includes the API key)."""


@dataclass(frozen=True)
class WafClearance:
    """The session material returned by a solved WAF challenge."""

    cookies: dict[str, str]
    headers: dict[str, str]


def _error_message(status: int, body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
        error = payload.get("error", {})
        code = error.get("code", "unknown_error")
        message = error.get("message", "request failed")
        return f"SolveGate returned HTTP {status} ({code}): {message}"
    except (ValueError, AttributeError):
        return f"SolveGate returned HTTP {status}"


def _parse_cookie_header(value: str) -> dict[str, str]:
    cookie = SimpleCookie()
    cookie.load(value)
    return {key: morsel.value for key, morsel in cookie.items()}


def _cookies_from_payload(payload: Mapping) -> dict[str, str]:
    cookies: dict[str, str] = {}
    raw = payload.get("cookies", {})
    if isinstance(raw, str):
        cookies.update(_parse_cookie_header(raw))
    elif isinstance(raw, Mapping):
        cookies.update({str(k): str(v) for k, v in raw.items()})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                cookies.update(_parse_cookie_header(item))
            elif isinstance(item, Mapping) and item.get("name") is not None:
                cookies[str(item["name"])] = str(item.get("value", ""))

    raw_set = payload.get("set_cookies", [])
    if isinstance(raw_set, str):
        raw_set = [raw_set]
    if isinstance(raw_set, Mapping):
        # Accept either one cookie object or a simple name -> value mapping.
        if raw_set.get("name") is not None:
            raw_set = [raw_set]
        else:
            cookies.update({str(k): str(v) for k, v in raw_set.items()})
            raw_set = []
    if isinstance(raw_set, list):
        for item in raw_set:
            if isinstance(item, str):
                cookies.update(_parse_cookie_header(item))
            elif isinstance(item, Mapping) and item.get("name") is not None:
                cookies[str(item["name"])] = str(item.get("value", ""))
    return cookies


def _safe_headers(payload: Mapping) -> dict[str, str]:
    raw = payload.get("headers", {})
    if not isinstance(raw, Mapping):
        return {}
    # These are response/proxy framing headers and must not be copied onto a
    # new Scrapy request.  SolveGate's clearance headers are otherwise passed
    # through unchanged.
    excluded = {
        "content-length", "content-encoding", "connection", "host",
        "set-cookie", "transfer-encoding",
    }
    return {
        str(key): str(value)
        for key, value in raw.items()
        if str(key).lower() not in excluded
    }


def _idempotency_key(url: str) -> str:
    return "solvegate-waf-" + hashlib.sha256(url.encode("utf-8")).hexdigest()


def solve_waf(
    url: str,
    *,
    api_key_env: str = "SOLVEGATE_API_KEY",
    sitekey: str = "waf",
    timeout: float = 90,
    opener=urllib.request.urlopen,
) -> WafClearance:
    """Solve a WAF challenge and return cookies/headers for one session.

    ``opener`` is injectable so unit tests never contact SolveGate.  A sandbox
    response is intentionally rejected: SolveGate documents that test tokens
    never clear a real WAF, though they are useful for testing the API client.
    """
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise SolveGateError(
            f"Cloudflare WAF challenge encountered, but {api_key_env} is not set"
        )

    request_body = json.dumps({
        "gate": "waf",
        "sitekey": sitekey,
        "url": url,
    }).encode("utf-8")
    request = urllib.request.Request(
        SOLVE_URL,
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": _idempotency_key(url),
        },
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            body = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        raise SolveGateError(_error_message(exc.code, body)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SolveGateError(f"SolveGate request failed: {exc}") from exc

    if status < 200 or status >= 300:
        raise SolveGateError(_error_message(status, body))
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SolveGateError("SolveGate returned invalid JSON") from exc

    if result.get("status") != "solved" or not result.get("token"):
        code = result.get("error_code") or result.get("status", "unknown")
        raise SolveGateError(f"SolveGate did not solve the WAF challenge ({code})")
    if result.get("mode") == "sandbox" or result.get("meter") == "sandbox":
        raise SolveGateError(
            "SolveGate returned a sandbox result; a test key cannot clear a live WAF"
        )
    try:
        payload = json.loads(result["token"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise SolveGateError("SolveGate returned an invalid WAF clearance payload") from exc
    if not isinstance(payload, Mapping):
        raise SolveGateError("SolveGate returned an invalid WAF clearance payload")
    return WafClearance(
        cookies=_cookies_from_payload(payload),
        headers=_safe_headers(payload),
    )
