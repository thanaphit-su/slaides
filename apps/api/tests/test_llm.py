from __future__ import annotations

from sqlalchemy import select

from slaides.db.base import get_session_factory
from slaides.db.models import LlmCall, Workspace
from slaides.llm import service as llm_service


async def test_workspace_patch_updates_llm_settings_without_echoing_key(client, auth_headers, seeded_user):
    res = await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={
            "llm_base_url": "https://llm.example.test/v1/",
            "llm_api_key": "sk-test-secret",
            "llm_model": "gpt-test",
            "llm_caps": {"interpret": False, "widget_generate": True},
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["llm_base_url"] == "https://llm.example.test/v1"
    assert body["llm_model"] == "gpt-test"
    assert body["llm_key_configured"] is True
    assert "llm_api_key" not in body
    assert body["llm_caps"]["interpret"] is False

    factory = get_session_factory()
    async with factory() as session:
        ws = await session.get(Workspace, seeded_user["workspace_id"])
        assert ws is not None
        assert ws.llm_key_enc
        assert b"sk-test-secret" not in ws.llm_key_enc


async def test_workspace_model_library_routes_capability_with_parameters(client, auth_headers, monkeypatch):
    async def fake_stream_openai_chunks(**kwargs):
        assert kwargs["model"] == "widget-vision"
        assert kwargs["parameters"]["temperature"] == 0.35
        assert kwargs["parameters"]["max_tokens"] == 2048
        yield "{}", {"prompt_tokens": 4, "completion_tokens": 1}

    monkeypatch.setattr(llm_service, "_stream_openai_chunks", fake_stream_openai_chunks)

    res = await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={
            "llm_api_key": "sk-test-secret",
            "llm_models": [
                {"id": "text-fast"},
                {
                    "id": "widget-vision",
                    "supports_image_input": True,
                    "temperature": 0.35,
                    "max_output_tokens": 2048,
                },
            ],
            "llm_capability_models": {
                "inline_write": "text-fast",
                "interpret": "text-fast",
                "widget_generate": "widget-vision",
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert [m["id"] for m in body["llm_models"]] == ["text-fast", "widget-vision"]
    assert body["llm_capability_models"]["widget_generate"] == "widget-vision"
    assert body["llm_caps"]["widget_generate"] is True
    assert "summarise" not in body["llm_caps"]

    complete = await client.post(
        "/api/v1/llm/complete",
        headers=auth_headers,
        json={"purpose": "widget_generate", "prompt": "Make a poll"},
    )
    assert complete.status_code == 200, complete.text

    factory = get_session_factory()
    async with factory() as session:
        row = (await session.execute(select(LlmCall))).scalars().one()
        assert row.model == "widget-vision"


async def test_workspace_patch_updates_interpret_quick_options(client, auth_headers):
    res = await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={
            "interpret_quick_options": [
                {"label": "Define", "instruction": "show a simple definition"},
                {"label": "Why", "instruction": "explain why this matters"},
                {"label": "Translate", "instruction": "translate this into Thai"},
            ],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["interpret_quick_options"] == [
        {"label": "Define", "instruction": "show a simple definition"},
        {"label": "Why", "instruction": "explain why this matters"},
        {"label": "Translate", "instruction": "translate this into Thai"},
    ]

    get_res = await client.get("/api/v1/workspace", headers=auth_headers)
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["interpret_quick_options"][0]["label"] == "Define"


async def test_workspace_rejects_more_than_three_interpret_quick_options(client, auth_headers):
    res = await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={
            "interpret_quick_options": [
                {"label": "One", "instruction": "one"},
                {"label": "Two", "instruction": "two"},
                {"label": "Three", "instruction": "three"},
                {"label": "Four", "instruction": "four"},
            ],
        },
    )
    assert res.status_code == 422, res.text


def test_widget_workflow_accepts_clarification_question_envelope():
    raw = '{"type":"question","question":"Should this be private or shared?","options":[{"id":"quiet","label":"Private"},{"id":"loud","label":"Shared"}]}'
    parsed = llm_service._parse_widget_workflow(raw)
    assert parsed["type"] == "question"
    assert parsed["options"][1]["id"] == "loud"


def test_widget_workflow_rejects_plain_prose():
    try:
        llm_service._parse_widget_workflow("I think this should be a poll.")
    except ValueError as exc:
        assert "workflow" in str(exc) or "JSON" in str(exc)
    else:
        raise AssertionError("plain prose must not become a fallback widget draft")


def test_widget_workflow_draft_still_gets_behavior_warnings():
    raw = (
        '{"type":"draft","widget":{'
        '"html":"<section>x</section>",'
        '"js":"",'
        '"props_schema":{},'
        '"behavior":{"kind":"loud","aggregator":"tally","contribution_schema":{"type":"string"}}'
        "}}"
    )
    warnings = llm_service._scan_behavior_violations(raw)
    assert any("never calls slaides.contribute" in warning for warning in warnings)


async def test_llm_complete_streams_sse_and_logs_call(client, auth_headers, monkeypatch):
    async def fake_stream_openai_chunks(**kwargs):
        assert kwargs["api_key"] == "sk-test-secret"
        assert kwargs["model"] == "gpt-test"
        yield "Plain ", {"prompt_tokens": 7, "completion_tokens": 2}
        yield "English.", {"prompt_tokens": 7, "completion_tokens": 4}

    monkeypatch.setattr(llm_service, "_stream_openai_chunks", fake_stream_openai_chunks)

    settings = await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={"llm_api_key": "sk-test-secret", "llm_model": "gpt-test"},
    )
    assert settings.status_code == 200, settings.text

    res = await client.post(
        "/api/v1/llm/complete",
        headers=auth_headers,
        json={"purpose": "interpret", "prompt": "Explain a residual."},
    )
    assert res.status_code == 200, res.text
    assert "event: token" in res.text
    assert '"delta": "Plain "' in res.text
    assert 'event: done' in res.text
    assert '"text": "Plain English."' in res.text

    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(select(LlmCall))).scalars().all()
        assert len(rows) == 1
        assert rows[0].purpose == "interpret"
        assert rows[0].model == "gpt-test"
        assert rows[0].prompt_text is None
        assert rows[0].tokens_in == 7
        assert rows[0].tokens_out == 4


async def test_guest_can_interpret_live_slide_text_only(client, auth_headers, monkeypatch):
    async def fake_stream_openai_chunks(**kwargs):
        assert kwargs["api_key"] == "sk-test-secret"
        assert kwargs["model"] == "gpt-test"
        assert kwargs["body"].purpose == "interpret"
        yield "A simple definition.", {"prompt_tokens": 5, "completion_tokens": 4}

    monkeypatch.setattr(llm_service, "_stream_openai_chunks", fake_stream_openai_chunks)

    settings = await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={"llm_api_key": "sk-test-secret", "llm_model": "gpt-test"},
    )
    assert settings.status_code == 200, settings.text

    deck = (
        await client.post("/api/v1/decks", json={"title": "Live interpret"}, headers=auth_headers)
    ).json()
    live = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()
    guest = await client.post(
        "/api/v1/auth/guest",
        json={"code": live["code"], "email": "audience@example.com", "anonymous": True},
    )
    assert guest.status_code == 200, guest.text
    guest_headers = {"Authorization": f"Bearer {guest.json()['token']}"}

    res = await client.post(
        "/api/v1/llm/complete",
        headers=guest_headers,
        json={
            "purpose": "interpret",
            "prompt": "show a simple definition",
            "context": {"selection": "residual", "session_id": live["id"]},
        },
    )
    assert res.status_code == 200, res.text
    assert '"text": "A simple definition."' in res.text

    blocked = await client.post(
        "/api/v1/llm/complete",
        headers=guest_headers,
        json={"purpose": "widget_generate", "prompt": "make a poll"},
    )
    assert blocked.status_code == 403

    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(select(LlmCall))).scalars().all()
        assert len(rows) == 1
        assert rows[0].purpose == "interpret"
        assert rows[0].user_id is None
        assert str(rows[0].session_id) == live["id"]


def test_scan_theme_violations_flags_hex_and_rgb():
    text = "<style>body{background:#0f172a;color:rgb(255,255,255);}</style><div style=\"border:1px solid #fff;background:rgba(0,0,0,0.5)\"></div>"
    warnings = llm_service._scan_theme_violations(text)
    color_warning = next((w for w in warnings if w.startswith("Hardcoded color literals")), None)
    assert color_warning is not None
    assert "#0f172a" in color_warning
    assert "#fff" in color_warning
    assert "rgb" in color_warning
    assert "rgba" in color_warning


def test_scan_theme_violations_passes_clean_theme_tokens():
    text = "<div style=\"background:var(--background);color:var(--foreground);border:1px solid var(--border)\"></div>"
    assert llm_service._scan_theme_violations(text) == []



def test_scan_theme_violations_flags_font_imports_and_links():
    css = "@import url('https://fonts.googleapis.com/css2?family=Inter');\n.poll{font-family:'Inter',sans-serif;}"
    warnings = llm_service._scan_theme_violations(css)
    assert any("Hardcoded font-family" in w and "Inter" in w for w in warnings)
    assert any("@import" in w for w in warnings)


def test_scan_theme_violations_flags_remote_resources():
    html = "<link rel=\"stylesheet\" href=\"https://example.com/x.css\"><script src=\"https://cdn/y.js\"></script>"
    warnings = llm_service._scan_theme_violations(html)
    assert any("<link rel=stylesheet>" in w for w in warnings)
    assert any("<script src=https://" in w for w in warnings)


def test_scan_theme_violations_passes_clean_widget():
    css = ".p{background:var(--card);color:var(--card-foreground);font-family:var(--font-sans);}"
    assert llm_service._scan_theme_violations(css) == []


def test_scan_theme_violations_flags_named_color_values():
    css = "body{color:white;}\n.box{background:red;}\n.btn{border:1px solid Black;}"
    warnings = llm_service._scan_theme_violations(css)
    color_warning = next((w for w in warnings if w.startswith("Hardcoded color literals")), None)
    assert color_warning is not None
    assert "white" in color_warning
    assert "red" in color_warning
    assert "black" in color_warning


def test_scan_layout_violations_flags_fixed_pixel_max_width():
    css = ".poll{max-width: 600px;margin: 0 auto;padding: 1rem;}"
    warnings = llm_service._scan_layout_violations(css)
    assert len(warnings) == 1
    assert "600px" in warnings[0]
    assert "max-width" in warnings[0].lower()


def test_scan_layout_violations_flags_rem_em_ch_units():
    css = (
        ".a{max-width: 32rem;}\n"
        ".b{max-width: 40em;}\n"
        ".c{max-width: 60ch;}"
    )
    warnings = llm_service._scan_layout_violations(css)
    assert len(warnings) == 1
    assert "32rem" in warnings[0]
    assert "40em" in warnings[0]
    assert "60ch" in warnings[0]


def test_scan_layout_violations_passes_percentage_and_viewport_caps():
    css = (
        ".root{max-width: 100%;}\n"
        ".col{max-width: 100vw;}\n"
        ".other{max-width:none;}"
    )
    assert llm_service._scan_layout_violations(css) == []


def test_scan_layout_violations_passes_when_no_max_width():
    css = ".poll{display:flex;flex-direction:column;gap:1rem;padding:1rem;}"
    assert llm_service._scan_layout_violations(css) == []


def test_scan_layout_violations_dedupes_repeated_values():
    css = ".a{max-width:600px;}\n.b{max-width:600px;}\n.c{max-width:600px;}"
    warnings = llm_service._scan_layout_violations(css)
    assert len(warnings) == 1
    # Only one "600px" sample, not three.
    assert warnings[0].count("600px") == 1


def test_scan_layout_violations_caps_at_max_samples():
    css = "".join(f".a{i}{{max-width:{100 + i}px;}}\n" for i in range(10))
    warnings = llm_service._scan_layout_violations(css, max_samples=3)
    assert len(warnings) == 1
    # The warning lists exactly three samples.
    listed = warnings[0].split("Found: ", 1)[1]
    assert listed.count(",") == 2  # 3 items → 2 commas


def test_props_contract_warns_when_schema_declared_but_not_read():
    draft = (
        '{"name":"Poll","kind":"poll",'
        '"html":"<section><h2>Pick one</h2><ul><li>A</li><li>B</li></ul></section>",'
        '"js":"console.log(\'hi\');",'
        '"css":"",'
        '"props_schema":{"properties":{"question":{"type":"string","default":"Pick"},'
        '"choices":{"type":"array","default":[]}}},'
        '"tags":[]}'
    )
    warnings = llm_service._scan_props_contract_violations(draft)
    assert any("never reads window.slaides.props" in w for w in warnings)


def test_props_contract_passes_when_props_are_read():
    draft = (
        '{"name":"Poll","kind":"poll",'
        '"html":"<section id=\\"q\\"></section>",'
        '"js":"var p = window.slaides.props; document.getElementById(\'q\').textContent = p.question;",'
        '"css":"",'
        '"props_schema":{"properties":{"question":{"type":"string","default":"Pick"}}},'
        '"tags":[]}'
    )
    warnings = llm_service._scan_props_contract_violations(draft)
    assert warnings == []


def test_props_contract_warns_about_individual_unused_keys():
    # Reads `question` but never references the `choices` key — partial usage
    # is still worth flagging.
    draft = (
        '{"name":"Poll","kind":"poll",'
        '"html":"","js":"var p = window.slaides.props; console.log(p.question);",'
        '"css":"",'
        '"props_schema":{"properties":{"question":{"type":"string"},"choices":{"type":"array"}}},'
        '"tags":[]}'
    )
    warnings = llm_service._scan_props_contract_violations(draft)
    assert any("Props declared but never read" in w and "choices" in w for w in warnings)


def test_props_contract_silent_when_no_schema():
    draft = '{"name":"x","kind":"custom","html":"<p>x</p>","js":"","css":"","props_schema":{},"tags":[]}'
    assert llm_service._scan_props_contract_violations(draft) == []


def test_behavior_quiet_with_contribute_call_is_flagged():
    draft = (
        '{"name":"q","kind":"custom","html":"<p>x</p>",'
        '"js":"window.slaides.contribute(\\"a\\");",'
        '"css":"","props_schema":{},"tags":[],'
        '"behavior":{"kind":"quiet"}}'
    )
    warnings = llm_service._scan_behavior_violations(draft)
    assert any("rejected at runtime" in w for w in warnings)


def test_behavior_loud_without_contribute_is_flagged():
    draft = (
        '{"name":"l","kind":"custom","html":"<p>x</p>","js":"","css":"",'
        '"props_schema":{},"tags":[],'
        '"behavior":{"kind":"loud","aggregator":"tally","contribution_schema":{"type":"string"}}}'
    )
    warnings = llm_service._scan_behavior_violations(draft)
    assert any("never calls slaides.contribute" in w for w in warnings)
    assert any("never subscribes to slaides.on('state'" in w for w in warnings)


def test_behavior_loud_with_unknown_aggregator_is_flagged():
    draft = (
        '{"name":"l","kind":"custom","html":"<p>x</p>",'
        '"js":"window.slaides.contribute(1); window.slaides.on(\\"state\\", function(){});",'
        '"css":"","props_schema":{},"tags":[],'
        '"behavior":{"kind":"loud","aggregator":"votecount","contribution_schema":{"type":"string"}}}'
    )
    warnings = llm_service._scan_behavior_violations(draft)
    assert any("aggregator 'votecount'" in w for w in warnings)


def test_behavior_loud_missing_contribution_schema_is_flagged():
    draft = (
        '{"name":"l","kind":"custom","html":"<p>x</p>",'
        '"js":"window.slaides.contribute(1); window.slaides.on(\\"state\\", function(){});",'
        '"css":"","props_schema":{},"tags":[],'
        '"behavior":{"kind":"loud","aggregator":"tally"}}'
    )
    warnings = llm_service._scan_behavior_violations(draft)
    assert any("contribution_schema" in w for w in warnings)


def test_behavior_well_formed_loud_widget_passes_validator():
    draft = (
        '{"name":"l","kind":"custom","html":"<p>x</p>",'
        '"js":"window.slaides.on(\\"state\\", function(m){}); window.slaides.contribute(\\"a\\");",'
        '"css":"","props_schema":{},"tags":[],'
        '"behavior":{"kind":"loud","aggregator":"tally","contribution_schema":{"type":"string"}}}'
    )
    assert llm_service._scan_behavior_violations(draft) == []


def test_behavior_quiet_widget_without_contribute_passes_validator():
    draft = (
        '{"name":"q","kind":"custom","html":"<p>x</p>","js":"console.log(1)",'
        '"css":"","props_schema":{},"tags":[],"behavior":{"kind":"quiet"}}'
    )
    assert llm_service._scan_behavior_violations(draft) == []


def test_behavior_adjust_mode_flags_loud_widget_when_js_drops_contribute():
    """Regression: AI Adjust returns a partial draft that rewrites JS but
    omits the contribute() call. The existing widget is Loud. Scanning the
    draft alone misses the dead-Loud state. With `current` passed, the
    merged-shape scan flags it."""
    draft = '{"js":"console.log(\\"rewritten without contribute\\");"}'
    current = {
        "behavior": {
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
        "js": 'window.slaides.contribute("a"); window.slaides.on("state", function(){});',
        "html": "<section>poll</section>",
    }
    warnings = llm_service._scan_behavior_violations(draft, current=current)
    assert any("never calls slaides.contribute" in w for w in warnings)


def test_behavior_adjust_mode_unchanged_js_passes_validator():
    """Adjust draft that only renames the widget — JS untouched — should not
    flag a behavior violation since the merged widget is still well-formed."""
    draft = '{"name":"renamed"}'
    current = {
        "behavior": {
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
        "js": 'window.slaides.contribute("a"); window.slaides.on("state", function(){});',
        "html": "<section>poll</section>",
    }
    assert llm_service._scan_behavior_violations(draft, current=current) == []


def test_behavior_create_mode_unchanged_when_current_is_none():
    """`current=None` (create mode) preserves the original scan-the-draft
    semantics. A Loud draft with no contribute() should still be flagged."""
    draft = (
        '{"name":"l","kind":"custom","html":"<p>x</p>","js":"","css":"",'
        '"props_schema":{},"tags":[],'
        '"behavior":{"kind":"loud","aggregator":"tally","contribution_schema":{"type":"string"}}}'
    )
    warnings = llm_service._scan_behavior_violations(draft, current=None)
    assert any("never calls slaides.contribute" in w for w in warnings)


def test_scan_theme_violations_ignores_named_color_in_non_css_context():
    # The word "red" appears as content / class name / JS string — not as a
    # CSS color value. The scanner should not flag any of these.
    text = (
        "<p class=\"red-banner\">Pick a color: red, blue, or green</p>\n"
        "<script>var label = \"red\";</script>"
    )
    assert llm_service._scan_theme_violations(text) == []


async def test_llm_rate_limit_uses_shared_redis_counter(client, auth_headers, monkeypatch, seeded_user):
    """Two clients sharing a workspace must share the per-minute counter even
    when each call goes through a separate request — i.e. the limiter must not
    rely on per-process in-memory dicts."""

    async def fake_stream_openai_chunks(**kwargs):
        yield "ok", {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(llm_service, "_stream_openai_chunks", fake_stream_openai_chunks)
    # Tighten the caps so we don't have to send 60+ requests.
    from slaides import settings as settings_module

    monkeypatch.setattr(
        settings_module.get_settings(), "llm_workspace_rate_limit", 3, raising=False
    )
    monkeypatch.setattr(
        settings_module.get_settings(), "llm_widget_user_rate_limit", 2, raising=False
    )

    await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={"llm_api_key": "sk-test-secret", "llm_model": "gpt-test"},
    )

    for _ in range(3):
        res = await client.post(
            "/api/v1/llm/complete",
            headers=auth_headers,
            json={"purpose": "interpret", "prompt": "hi"},
        )
        assert res.status_code == 200, res.text
        assert "event: token" in res.text

    over = await client.post(
        "/api/v1/llm/complete",
        headers=auth_headers,
        json={"purpose": "interpret", "prompt": "hi"},
    )
    assert over.status_code == 200, over.text
    assert "workspace LLM rate limit exceeded" in over.text


async def test_llm_widget_generate_rate_limit_per_user(client, auth_headers, monkeypatch):
    async def fake_stream_openai_chunks(**kwargs):
        yield "{}", {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(llm_service, "_stream_openai_chunks", fake_stream_openai_chunks)
    from slaides import settings as settings_module

    monkeypatch.setattr(
        settings_module.get_settings(), "llm_workspace_rate_limit", 100, raising=False
    )
    monkeypatch.setattr(
        settings_module.get_settings(), "llm_widget_user_rate_limit", 2, raising=False
    )

    await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={"llm_api_key": "sk-test-secret", "llm_model": "gpt-test"},
    )

    for _ in range(2):
        res = await client.post(
            "/api/v1/llm/complete",
            headers=auth_headers,
            json={"purpose": "widget_generate", "prompt": "poll"},
        )
        assert res.status_code == 200, res.text
        assert "event: token" in res.text

    blocked = await client.post(
        "/api/v1/llm/complete",
        headers=auth_headers,
        json={"purpose": "widget_generate", "prompt": "poll"},
    )
    assert blocked.status_code == 200
    assert "widget generation rate limit exceeded" in blocked.text
