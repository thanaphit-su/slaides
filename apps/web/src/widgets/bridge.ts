/**
 * The bridge script that runs INSIDE each widget iframe (sandboxed).
 * It defines `window.slaides` per SPEC §9 and routes calls back to the host
 * via `postMessage`. The host injects this as a string into the iframe's
 * srcdoc before the widget's own script tags execute.
 *
 * The host also injects `window.__slaides_boot = {props, role, participant}`
 * IMMEDIATELY before this script runs, so widgets can read props *synchronously*
 * at script-evaluation time. No handshake required for the props read.
 *
 * Anything in this string must be self-contained — no imports, no external
 * references. It runs in a clean window.
 */

export const WIDGET_BRIDGE_SOURCE = String.raw`
(function () {
  var boot = window.__slaides_boot || {};
  var subs = Object.create(null);
  // Per-viewer scratch state. Seeded from boot.state so it survives an iframe
  // remount (e.g. the audience navigates away from the slide and back): the
  // host persists every setState to its own sessionStorage and replays the map
  // here at mount. The sandbox=allow-scripts iframe has a null origin and
  // cannot use sessionStorage itself, so the host must mediate.
  var pendingState =
    boot.state && typeof boot.state === 'object' ? boot.state : Object.create(null);

  function emit(type, payload) {
    // sandbox="allow-scripts" (no allow-same-origin) gives this iframe an
    // opaque "null" origin, so targeting a real host origin here is not
    // possible — the wildcard is mandatory, not a TODO. The host filters by
    // event.source identity and a type allowlist in WidgetFrame.onMessage.
    parent.postMessage({ slaides: true, type: type, payload: payload || {} }, '*');
  }

  function on(type, cb) {
    if (!subs[type]) subs[type] = [];
    subs[type].push(cb);
  }

  function setState(key, value) {
    pendingState[key] = value;
    emit('state.set', { key: key, value: value });
  }
  function getState(key) {
    return pendingState[key];
  }

  function uid() { return 'h_' + Math.random().toString(36).slice(2, 10); }

  function llm(prompt) {
    var id = uid();
    return new Promise(function (resolve, reject) {
      var handler = function (ev) {
        var msg = ev.data;
        if (!msg || !msg.slaides || msg.type !== 'llm.reply' || msg.payload.id !== id) return;
        window.removeEventListener('message', handler);
        if (msg.payload.error) reject(new Error(msg.payload.error));
        else resolve(msg.payload.text || '');
      };
      window.addEventListener('message', handler);
      emit('llm.request', { id: id, prompt: prompt });
    });
  }

  window.addEventListener('message', function (ev) {
    var msg = ev.data;
    if (!msg || !msg.slaides) return;
    if (msg.type === 'props.update') {
      if (msg.payload && msg.payload.props) {
        window.slaides.props = msg.payload.props;
        (subs['props'] || []).forEach(function (cb) { try { cb(msg.payload.props); } catch (_) {} });
      }
      return;
    }
    (subs[msg.type] || []).forEach(function (cb) { try { cb(msg.payload); } catch (_) {} });
  });

  // Widgets v2 Step 4 — Loud-widget bridge surface.
  //
  //   slaides.contribute(value)        // audience -> host -> server aggregator
  //   slaides.on('state', function(m)) // subscribe to the aggregated state
  //
  // m is { placement_id, state, state_version, closed }. The widget should
  // re-render whenever this fires; never optimistically mutate state from
  // the contribute side.
  function contribute(value) {
    emit('widget.contribute', { value: value });
  }

  // window.slaides.participant carries the audience member's identity
  //   { id: null, display_name: string | null, anon: boolean }
  // - display_name is the name the user typed at session join — prefer it
  //   over asking the user to type their name again inside the widget
  // - anon is true if the user opted out of name display; respect it in UI
  // - presenter / preview / instructor roles get the default null/false
  window.slaides = {
    emit: emit,
    on: on,
    setState: setState,
    getState: getState,
    contribute: contribute,
    role: boot.role || 'preview',
    participant: boot.participant || { id: null, display_name: null, anon: false },
    props: boot.props || {},
    behavior: boot.behavior || { kind: 'quiet' },
    api: { llm: llm },
  };

  // Auto-report content height so the host iframe can fit content tightly.
  // We coalesce reports through rAF to avoid postMessage storms.
  var lastH = -1;
  var pending = false;
  function reportSize() {
    pending = false;
    var doc = document.documentElement;
    var body = document.body;
    if (!body) return;
    // Measure content, not the iframe viewport. documentElement.scrollHeight
    // and body.offsetHeight can reflect the host-assigned iframe height, which
    // feeds back into resize and makes the frame grow forever.
    var rect = body.getBoundingClientRect ? body.getBoundingClientRect() : null;
    var h = Math.max(
      body.scrollHeight || 0,
      rect ? Math.ceil(rect.height) : 0
    );
    if (h !== lastH && h > 0) {
      lastH = h;
      emit('resize', { height: h });
    }
  }
  function schedule() {
    if (pending) return;
    pending = true;
    (window.requestAnimationFrame || function (cb) { setTimeout(cb, 16); })(reportSize);
  }
  function bootObservers() {
    schedule();
    setTimeout(schedule, 80);
    setTimeout(schedule, 320);
    if (typeof ResizeObserver !== 'undefined' && document.body) {
      try { new ResizeObserver(schedule).observe(document.body); } catch (_) {}
    }
    if (typeof MutationObserver !== 'undefined' && document.body) {
      try { new MutationObserver(schedule).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true }); } catch (_) {}
    }
    window.addEventListener('load', schedule);
    window.addEventListener('resize', schedule);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootObservers);
  } else {
    bootObservers();
  }
})();
`;
