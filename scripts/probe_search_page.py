#!/usr/bin/env python3
"""Probe what this environment can read from a Best Buy search page.

This is intentionally small and dependency-free.
"""

from __future__ import annotations

import http.client
import json
import socket
import sys
import time
from typing import Any
from urllib.parse import urlparse

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def timed(label: str, fn):
    started = time.time()
    try:
        value = fn()
        return {
            "ok": True,
            "elapsed_s": round(time.time() - started, 3),
            label: value,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "elapsed_s": round(time.time() - started, 3),
            "error": repr(exc),
        }


def resolve_host(host: str) -> dict[str, Any]:
    def _resolve():
        cname, aliases, addresses = socket.gethostbyname_ex(host)
        return {
            "cname": cname,
            "aliases": aliases,
            "addresses": addresses,
        }

    return timed("result", _resolve)


def tcp_connect(host: str, port: int = 443, timeout: float = 5.0) -> dict[str, Any]:
    def _connect():
        with socket.create_connection((host, port), timeout=timeout) as sock:
            return {"peer": list(sock.getpeername())}

    return timed("result", _connect)


def request_once(method: str, host: str, path: str, timeout: float = 10.0) -> dict[str, Any]:
    def _request():
        conn = http.client.HTTPSConnection(host, timeout=timeout)
        try:
            conn.request(
                method,
                path,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Connection": "close",
                },
            )
            resp = conn.getresponse()
            payload = {
                "status": resp.status,
                "reason": resp.reason,
                "headers": dict(resp.getheaders()),
            }
            if method != "HEAD":
                body = resp.read(512)
                payload["body_preview"] = body.decode("utf-8", errors="replace")
                payload["body_preview_len"] = len(body)
            return payload
        finally:
            conn.close()

    return timed("result", _request)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <bestbuy-url>", file=sys.stderr)
        return 2

    url = sys.argv[1]
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        print("expected an https URL", file=sys.stderr)
        return 2

    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    report = {
        "url": url,
        "host": parsed.netloc,
        "dns": resolve_host(parsed.netloc),
        "tcp_443": tcp_connect(parsed.netloc, 443),
        "head": request_once("HEAD", parsed.netloc, path),
        "get": request_once("GET", parsed.netloc, path),
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
