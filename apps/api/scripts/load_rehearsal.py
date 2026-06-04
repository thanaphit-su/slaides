from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets


@dataclass
class RehearsalResult:
    join_ms: list[int] = field(default_factory=list)
    ws_connect_ms: list[int] = field(default_factory=list)
    contribution_ack_ms: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil((pct / 100) * len(ordered)))
    return ordered[rank - 1]


def summarize(
    result: RehearsalResult,
    *,
    max_join_p95_ms: int,
    max_ws_p95_ms: int,
    max_ack_p95_ms: int,
) -> dict[str, Any]:
    join_p95 = percentile(result.join_ms, 95)
    ws_p95 = percentile(result.ws_connect_ms, 95)
    ack_p95 = percentile(result.contribution_ack_ms, 95)
    ok = (
        not result.errors
        and join_p95 <= max_join_p95_ms
        and ws_p95 <= max_ws_p95_ms
        and (not result.contribution_ack_ms or ack_p95 <= max_ack_p95_ms)
    )
    return {
        "ok": ok,
        "participants_joined": len(result.join_ms),
        "websockets_connected": len(result.ws_connect_ms),
        "contributions_acknowledged": len(result.contribution_ack_ms),
        "join_p95_ms": join_p95,
        "ws_connect_p95_ms": ws_p95,
        "contribution_ack_p95_ms": ack_p95,
        "errors": result.errors[:20],
        "error_count": len(result.errors),
    }


def build_urls(api_url: str) -> tuple[str, str]:
    api_base = api_url.rstrip("/")
    root = api_base.removesuffix("/api/v1")
    parsed = urlparse(root)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("api URL must be absolute, e.g. https://slaides.example.com/api/v1")
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_base = f"{ws_scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    return api_base, ws_base


async def _wait_for_event(ws: Any, event_type: str, predicate, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for {event_type}")
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = json.loads(raw)
        if event.get("type") == event_type and predicate(event.get("payload") or {}):
            return event


async def _heartbeat(ws: Any, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.sleep(10)
        if stop.is_set():
            break
        await ws.send(json.dumps({"type": "heartbeat"}))


async def _participant(
    index: int,
    *,
    api_base: str,
    ws_base: str,
    code: str,
    placement_id: str | None,
    contribution_value: str,
    hold_seconds: float,
    timeout_seconds: float,
    result: RehearsalResult,
) -> None:
    email = f"load-{index:05d}@slaides.invalid"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            start = time.perf_counter()
            join = await client.post(
                f"{api_base}/auth/guest",
                json={"code": code, "email": email, "anonymous": True},
            )
            join.raise_for_status()
            join_ms = int((time.perf_counter() - start) * 1000)
            result.join_ms.append(join_ms)
            guest = join.json()

            snapshot = await client.get(
                f"{api_base}/sessions/{guest['session_id']}/audience",
                headers={"Authorization": f"Bearer {guest['token']}"},
            )
            snapshot.raise_for_status()

            ws_url = f"{ws_base}/ws/sessions/{guest['session_id']}?token={guest['token']}"
            start = time.perf_counter()
            async with websockets.connect(ws_url, open_timeout=timeout_seconds) as ws:
                result.ws_connect_ms.append(int((time.perf_counter() - start) * 1000))
                await _wait_for_event(ws, "session.state", lambda _p: True, timeout_seconds)

                stop = asyncio.Event()
                heartbeat_task = asyncio.create_task(_heartbeat(ws, stop))
                try:
                    if placement_id:
                        start = time.perf_counter()
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "widget.contribute",
                                    "payload": {
                                        "placement_id": placement_id,
                                        "value": contribution_value,
                                    },
                                }
                            )
                        )
                        await _wait_for_event(
                            ws,
                            "widget.state",
                            lambda p: p.get("placement_id") == placement_id,
                            timeout_seconds,
                        )
                        result.contribution_ack_ms.append(
                            int((time.perf_counter() - start) * 1000)
                        )
                    if hold_seconds > 0:
                        await asyncio.sleep(hold_seconds)
                finally:
                    stop.set()
                    heartbeat_task.cancel()
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"participant {index}: {exc}")


async def run_rehearsal(args: argparse.Namespace) -> dict[str, Any]:
    api_base, ws_base = build_urls(args.api_url)
    result = RehearsalResult()
    sem = asyncio.Semaphore(args.concurrency)

    async def guarded(index: int) -> None:
        async with sem:
            await _participant(
                index,
                api_base=api_base,
                ws_base=ws_base,
                code=args.code,
                placement_id=args.placement_id,
                contribution_value=args.value,
                hold_seconds=args.hold_seconds,
                timeout_seconds=args.timeout_seconds,
                result=result,
            )

    await asyncio.gather(*(guarded(i) for i in range(args.audience)))
    return summarize(
        result,
        max_join_p95_ms=args.max_join_p95_ms,
        max_ws_p95_ms=args.max_ws_p95_ms,
        max_ack_p95_ms=args.max_ack_p95_ms,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a SLAIDES audience load rehearsal against an existing live session."
    )
    parser.add_argument("--api-url", required=True, help="Absolute API URL, e.g. https://host/api/v1")
    parser.add_argument("--code", required=True, help="Live session code, e.g. SLD-ABCD-EF")
    parser.add_argument("--audience", type=int, default=150)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--placement-id", help="Optional loud-widget placement_id to contribute to")
    parser.add_argument("--value", default="yes", help="Contribution value when --placement-id is set")
    parser.add_argument("--hold-seconds", type=float, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument("--max-join-p95-ms", type=int, default=500)
    parser.add_argument("--max-ws-p95-ms", type=int, default=500)
    parser.add_argument("--max-ack-p95-ms", type=int, default=700)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = asyncio.run(run_rehearsal(args))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
