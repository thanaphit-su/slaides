from __future__ import annotations

from scripts.load_rehearsal import RehearsalResult, build_urls, percentile, summarize


def test_percentile_uses_nearest_rank():
    assert percentile([100, 20, 50, 10], 95) == 100
    assert percentile([100, 20, 50, 10], 50) == 20
    assert percentile([], 95) == 0


def test_summarize_marks_success_only_when_errors_and_budgets_pass():
    result = RehearsalResult(
        join_ms=[100, 200, 300],
        ws_connect_ms=[80, 90, 100],
        contribution_ack_ms=[250, 300],
        errors=[],
    )

    summary = summarize(result, max_join_p95_ms=500, max_ws_p95_ms=500, max_ack_p95_ms=700)

    assert summary["ok"] is True
    assert summary["participants_joined"] == 3
    assert summary["join_p95_ms"] == 300
    assert summary["ws_connect_p95_ms"] == 100
    assert summary["contribution_ack_p95_ms"] == 300


def test_summarize_fails_when_any_budget_is_exceeded():
    result = RehearsalResult(
        join_ms=[1000],
        ws_connect_ms=[100],
        contribution_ack_ms=[],
        errors=[],
    )

    summary = summarize(result, max_join_p95_ms=500, max_ws_p95_ms=500, max_ack_p95_ms=700)

    assert summary["ok"] is False


def test_build_urls_derives_websocket_root_from_api_url():
    api_base, ws_base = build_urls("https://slaides.example.com/api/v1")

    assert api_base == "https://slaides.example.com/api/v1"
    assert ws_base == "wss://slaides.example.com"
