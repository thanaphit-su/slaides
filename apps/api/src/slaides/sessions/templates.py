"""Convert a live interaction's spec into a deck widget payload.

Used by `POST /widgets/from-interaction` so an instructor can keep a poll or
open-question they authored mid-presentation and reuse it on a future deck
slide. The generated widget bodies follow the current iframe runtime and
bridge contract used by deck widgets.
"""
from __future__ import annotations

import html as _html


def _esc(s: str) -> str:
    return _html.escape(str(s or ""), quote=True)


_POLL_HTML = """\
<section class="poll" aria-live="polite">
  <header>
    <span class="kicker">POLL</span>
    <h2 id="q"></h2>
  </header>
  <ul id="options" role="listbox" aria-label="poll options"></ul>
  <footer><span id="status">— pick one to vote</span></footer>
</section>
"""

_POLL_CSS = """\
body { margin: 0; padding: 18px 0px; font-family: var(--font-sans); color: var(--foreground); background: var(--background); }
.kicker { font-family: var(--font-sans); font-size: 11px; font-weight: 600; letter-spacing: .18em; color: var(--accent); text-transform: uppercase; }
h2 { font-family: var(--font-serif); font-size: 22px; margin: 6px 0 14px; font-weight: 500; letter-spacing: -.015em; }
ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }
li button { width: 100%; text-align: left; border: 1px solid var(--border); background: var(--card); padding: 10px 12px; border-radius: var(--radius); font-family: var(--font-sans); font-size: 13px; color: var(--foreground); cursor: pointer; display: flex; align-items: center; gap: 10px; transition: border-color .15s ease, background .15s ease; }
li button:hover { border-color: var(--border-strong); }
li button[aria-pressed='true'] { border-color: var(--accent); background: var(--accent-soft); }
.bar { height: 4px; flex: 1; background: var(--muted); border-radius: 4px; overflow: hidden; }
.fill { display: block; height: 100%; background: var(--accent); width: 0%; transition: width .5s ease; }
.count { font-family: var(--font-mono); font-size: 11px; color: var(--muted-foreground); min-width: 28px; text-align: right; }
footer { margin-top: 14px; font-family: var(--font-sans); font-size: 11px; color: var(--muted-foreground); }
"""

_POLL_JS = """\
(function () {
  var bridge = window.slaides;
  var p = (bridge && bridge.props) || {};
  var question = p.question || 'Untitled poll';
  var options = Array.isArray(p.options) ? p.options : ['A', 'B'];
  var qEl = document.getElementById('q');
  var listEl = document.getElementById('options');
  var statusEl = document.getElementById('status');
  qEl.textContent = question;
  var counts = options.map(function () { return 0; });
  var picked = null;
  function render() {
    var total = counts.reduce(function (a, b) { return a + b; }, 0) || 1;
    listEl.innerHTML = '';
    options.forEach(function (opt, i) {
      var li = document.createElement('li');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('aria-pressed', picked === i ? 'true' : 'false');
      btn.innerHTML =
        '<span style="font-weight:600"></span>' +
        '<span class="bar"><span class="fill"></span></span>' +
        '<span class="count"></span>';
      btn.children[0].textContent = opt;
      btn.children[1].firstChild.style.width = (counts[i] / total * 100).toFixed(0) + '%';
      btn.children[2].textContent = counts[i];
      btn.onclick = function () {
        picked = i;
        render();
        statusEl.textContent = 'Voted ' + opt + ' — waiting for tallies…';
        if (bridge && bridge.emit) bridge.emit('vote', { choice: opt });
      };
      li.appendChild(btn);
      listEl.appendChild(li);
    });
  }
  if (bridge && bridge.on) {
    bridge.on('vote.broadcast', function (payload) {
      var idx = options.indexOf(payload && payload.choice);
      if (idx >= 0) { counts[idx]++; render(); }
    });
  }
  render();
})();
"""

_QUESTION_HTML = """\
<section class="question">
  <header>
    <span class="kicker">QUESTION</span>
    <h2 id="q"></h2>
  </header>
  <form id="form">
    <textarea id="reply" rows="3" placeholder="Type a response…"></textarea>
    <button id="send" type="submit">Send</button>
  </form>
  <ul id="replies" aria-live="polite"></ul>
</section>
"""

_QUESTION_CSS = """\
body { margin: 0; padding: 18px 0px; font-family: var(--font-sans); color: var(--foreground); background: var(--background); }
.kicker { font-family: var(--font-sans); font-size: 11px; font-weight: 600; letter-spacing: .18em; color: var(--accent); text-transform: uppercase; }
h2 { font-family: var(--font-serif); font-size: 22px; margin: 6px 0 14px; font-weight: 500; letter-spacing: -.015em; }
form { display: flex; gap: 8px; align-items: flex-start; }
textarea { flex: 1; border: 1px solid var(--border); background: var(--card); border-radius: var(--radius); padding: 10px 12px; font: inherit; color: var(--foreground); resize: vertical; min-height: 56px; }
button { background: var(--primary); color: var(--primary-foreground); border: none; border-radius: var(--radius); padding: 10px 14px; font: inherit; cursor: pointer; }
ul { list-style: none; padding: 0; margin: 14px 0 0; display: grid; gap: 6px; }
li { font-family: var(--font-serif); font-size: 15px; color: var(--foreground); padding: 8px 10px; background: var(--muted); border-radius: var(--radius-sm); }
"""

_QUESTION_JS = """\
(function () {
  var bridge = window.slaides;
  var p = (bridge && bridge.props) || {};
  var prompt = p.prompt || 'What did you take away?';
  var qEl = document.getElementById('q');
  var form = document.getElementById('form');
  var reply = document.getElementById('reply');
  var list = document.getElementById('replies');
  qEl.textContent = prompt;
  form.onsubmit = function (e) {
    e.preventDefault();
    var text = (reply.value || '').trim();
    if (!text) return;
    if (bridge && bridge.emit) bridge.emit('text', { text: text });
    reply.value = '';
  };
  if (bridge && bridge.on) {
    bridge.on('text.broadcast', function (payload) {
      if (!payload || !payload.text) return;
      var li = document.createElement('li');
      li.textContent = payload.text;
      list.appendChild(li);
    });
  }
})();
"""


def build_widget_from_interaction(kind: str, spec: dict) -> dict:
    """Return a dict suitable for `Widget(**payload)` based on the spec."""
    spec = spec or {}
    if kind == "poll":
        question = spec.get("question") or "Untitled poll"
        options = [c.get("label") for c in (spec.get("choices") or []) if c.get("label")]
        if not options:
            raise ValueError("poll has no choices to save")
        return {
            "name": (question or "Untitled poll")[:80],
            "kind": "poll",
            "description": "Saved from a live session.",
            "html": _POLL_HTML,
            "css": _POLL_CSS,
            "js": _POLL_JS,
            "props_schema": {
                "question": {"type": "string", "default": question},
                "options": {"type": "array", "default": options},
            },
            "tags": ["live-saved", "poll"],
        }
    if kind == "question":
        prompt = spec.get("prompt") or "Untitled question"
        return {
            "name": prompt[:80],
            "kind": "question",
            "description": "Saved from a live session.",
            "html": _QUESTION_HTML,
            "css": _QUESTION_CSS,
            "js": _QUESTION_JS,
            "props_schema": {
                "prompt": {"type": "string", "default": prompt},
            },
            "tags": ["live-saved", "question"],
        }
    raise ValueError(f"cannot save interaction of kind '{kind}' to library")
