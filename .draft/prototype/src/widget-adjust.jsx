/* ============ SLAIDES — Widget Adjust panel ============ */

/* Opens when the instructor clicks "Adjust" on an existing slide widget.
   Three regions:
   - Live preview (top)
   - Code view (HTML/JS/CSS — read-only in prototype)
   - AI chat panel for natural-language adjustments
*/

const WidgetAdjustPanel = ({ widget, onClose, modelSupportsImage = true }) => {
  const [tab, setTab] = useState('code'); // 'code' | 'props' | 'preview'
  const [codeTab, setCodeTab] = useState('html');
  const [codeCollapsed, setCodeCollapsed] = useState(false);
  const [attachments, setAttachments] = useState([]); // images attached to next message
  const fileInputRef = useRef();
  const [chatLog, setChatLog] = useState([
  { role: 'assistant', text: `Adjustments for **${widget.kind}** widget. Tell me what to change — colors, copy, options, layout. I'll edit the code and re-mount the preview.` }]
  );
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const chatRef = useRef();

  // Mock code per widget kind (a real implementation reads from the widget record).
  const sourceFor = (kind) => {
    if (kind === 'poll' || kind === 'function-plotter' || kind === 'plotter') {
      return {
        html: `<div class="widget poll">
  <div class="poll__head">
    <span class="badge">POLL</span>
    <span class="badge--live"><span class="dot"></span> LIVE</span>
  </div>
  <h3 class="poll__q">Which line is the 'best fit'?</h3>
  <ul class="poll__opts">
    <li data-key="A">The flattest one</li>
    <li data-key="B">Smallest total distance</li>
    <li data-key="C">Passing through the most points</li>
    <li data-key="D">Smallest squared error</li>
  </ul>
</div>`,
        js: `// SLAIDES widget contract:
//   slaides.emit(event, payload)
//   slaides.on(event, cb)
//   slaides.setState(k, v) / .getState(k)

const opts = document.querySelectorAll('.poll__opts li');
opts.forEach(el => el.addEventListener('click', () => {
  const key = el.dataset.key;
  slaides.emit('vote', { choice: key });
  el.classList.add('is-voted');
  opts.forEach(o => o !== el && o.classList.add('is-dim'));
}));

slaides.on('host:results', ({ counts }) => {
  // counts = { A: 4, B: 18, C: 7, D: 3 }
  // render fill bars...
});`,
        css: `.widget.poll {
  font-family: var(--sans, Inter, sans-serif);
  border: 1px solid var(--rule, #e3e1dc);
  border-radius: 12px;
  padding: 18px 0px;
  background: var(--paper, #fff);
}
.poll__q {
  font-family: var(--serif, Newsreader, serif);
  font-size: 22px; line-height: 1.2; letter-spacing: -0.015em;
  margin: 10px 0 14px;
}
.poll__opts { list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 8px; }
.poll__opts li {
  position: relative; overflow: hidden;
  border: 1px solid var(--rule); border-radius: 8px;
  padding: 10px 14px; cursor: pointer;
}
.is-voted { border-color: var(--accent, #1f3a8a); background: var(--accent-soft, rgba(31,58,138,.08)); }
.is-dim { opacity: .65; }`
      };
    }
    return {
      html: `<div class="widget"><h3>${widget.kind}</h3></div>`,
      js: `// hand-written widget`,
      css: `.widget { font-family: var(--sans); }`
    };
  };
  const src = sourceFor(widget.kind);

  const onSendChat = (e) => {
    e?.preventDefault?.();
    if (!draft.trim() && attachments.length === 0) return;
    const userMsg = draft.trim();
    const sentAttachments = attachments;
    setChatLog((log) => [...log, { role: 'user', text: userMsg, attachments: sentAttachments }]);
    setDraft('');
    setAttachments([]);
    setBusy(true);
    setTimeout(() => {
      // mocked AI response
      let reply = '';
      const m = userMsg.toLowerCase();
      if (sentAttachments.length > 0 && !userMsg) {
        reply = `Looked at your reference image(s). I matched the palette — a warm clay accent on options + a pale cream surface — and tightened option spacing to feel closer to your screenshot.`;
      } else if (sentAttachments.length > 0) {
        reply = `Matched the screenshot you sent and applied your instructions — ${userMsg.slice(0, 50)}… Diff is in \`.poll__opts\` and the active state.`;
      } else if (m.includes('color') || m.includes('colour')) {
        reply = "Switched the active option highlight from the default accent to a softer amber, and bumped option borders to 1.5px. Updated `.is-voted` and `.poll__opts li`.";
      } else if (m.includes('add') && m.includes('option')) {
        reply = "Added a fifth option \"None of the above\" with key `E`. Vote handler already iterates over `data-key` so it picks up the new entry without changes to the JS.";
      } else if (m.includes('bigger') || m.includes('larger') || m.includes('font')) {
        reply = "Increased `.poll__q` to 26px and `.poll__opts li` font-size to 16px. Also tightened line-height by 0.04em to keep the rhythm.";
      } else {
        reply = "Applied your change. Diff summary: tweaked the markup in the relevant region and re-mounted the preview. Tell me what to do next.";
      }
      setChatLog((log) => [...log, { role: 'assistant', text: reply }]);
      setBusy(false);
      setTimeout(() => chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' }), 50);
    }, 900);
  };

  const onPickFiles = (e) => {
    const files = [...(e.target.files || [])];
    const reads = files.slice(0, 4).map(f => new Promise((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve({ name: f.name, dataUrl: r.result });
      r.readAsDataURL(f);
    }));
    Promise.all(reads).then(items => setAttachments(prev => [...prev, ...items].slice(0, 4)));
    e.target.value = '';
  };

  return (
    <Backdrop onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="slide-up" data-comment-anchor="393e801939-div-33-5" style={{
        width: 'min(1180px, 96vw)', height: 'min(720px, 92vh)',
        background: 'var(--paper)', borderRadius: 'var(--r-lg)',
        border: '1px solid var(--rule)', boxShadow: 'var(--shadow-3)',
        overflow: 'hidden', display: 'flex', flexDirection: 'column'
      }}>
        {/* Header */}
        <header style={{
          padding: '14px 20px', borderBottom: '1px solid var(--rule)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{
              width: 32, height: 32, borderRadius: 'var(--r-sm)', background: 'var(--accent-soft)', color: 'var(--accent)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Icon name="widget" size={16} />
            </span>
            <div>
              <div className="t-kicker" style={{ marginBottom: 2 }}>Adjust widget</div>
              <div style={{ fontFamily: 'var(--serif)', fontSize: 20, letterSpacing: '-0.015em' }}>
                {widget.kind} · <span style={{ color: 'var(--ink-soft)', fontStyle: 'italic' }}>#{widget.id}</span>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button className="btn btn-sm"><Icon name="download" size={13} /> Export .swidget</button>
            <button className="btn btn-sm"><Icon name="book" size={13} /> Save to library</button>
            <button className="btn btn-ghost btn-sm" onClick={onClose}><Icon name="x" size={14} /></button>
          </div>
        </header>

        {/* Body — split: left = preview + code, right = AI chat */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', flex: 1, minHeight: 0 }}>

          {/* Left: preview + code */}
          <section style={{ display: 'flex', flexDirection: 'column', minHeight: 0, borderRight: '1px solid var(--rule)' }}>

            {/* Preview pane — height grows to fill when code is collapsed */}
            <div style={{
              padding: '18px 22px', background: 'var(--paper-2)',
              borderBottom: codeCollapsed ? 'none' : '1px solid var(--rule)',
              display:'flex', flexDirection:'column', minHeight: 0,
              flex: codeCollapsed ? 1 : 'none'
            }}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom: 10 }}>
                <div className="t-mono-up">Live preview</div>
                <button
                  onClick={() => setCodeCollapsed(c => !c)}
                  className="btn btn-ghost btn-sm"
                  title={codeCollapsed ? 'Show code' : 'Hide code · expand preview'}
                  style={{ padding:'4px 8px', display:'inline-flex', alignItems:'center', gap:6, color:'var(--ink-soft)' }}
                >
                  <Icon name={codeCollapsed ? 'chev_up' : 'chev_down'} size={12}/>
                  {codeCollapsed ? 'Show code' : 'Hide code'}
                </button>
              </div>
              <div style={{
                background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 'var(--r-md)',
                padding: 14, overflow: 'auto',
                flex: codeCollapsed ? 1 : 'none',
                maxHeight: codeCollapsed ? 'none' : 220,
                minHeight: 0,
                transition: 'max-height .2s ease'
              }}>
                <Widget spec={widget} live={false} />
              </div>
              {!codeCollapsed && (
                <div className="t-mono" style={{ marginTop: 8, color: 'var(--ink-mute)' }}>
                  Preview re-mounts whenever the code changes. Sandbox bridge events are mocked.
                </div>
              )}
            </div>

            {/* Tab bar + code (hidden when collapsed) */}
            {!codeCollapsed && (<>
            <div style={{ borderBottom: '1px solid var(--rule)', padding: '0 14px', display: 'flex', alignItems: 'center', gap: 4 }}>
              {[
              ['code', 'Code', 'code'],
              ['props', 'Props', 'settings']].
              map(([k, label, icon]) =>
              <button key={k} onClick={() => setTab(k)} style={{
                background: tab === k ? 'var(--paper)' : 'transparent',
                borderBottom: tab === k ? '2px solid var(--ink)' : '2px solid transparent',
                border: 'none', borderRadius: 0,
                padding: '10px 12px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
                fontFamily: 'var(--sans)', fontWeight: tab === k ? 600 : 500, fontSize: 13,
                color: tab === k ? 'var(--ink)' : 'var(--ink-soft)'
              }}>
                  <Icon name={icon} size={13} /> {label}
                </button>
              )}
              <div style={{ flex: 1 }} />
              {tab === 'code' &&
              <div style={{ display: 'inline-flex', gap: 4 }}>
                  {['html', 'js', 'css'].map((t) =>
                <button key={t} onClick={() => setCodeTab(t)} style={{
                  background: codeTab === t ? 'var(--paper-2)' : 'transparent',
                  border: '1px solid', borderColor: codeTab === t ? 'var(--rule)' : 'transparent',
                  padding: '4px 9px', borderRadius: 'var(--r-xs)', cursor: 'pointer',
                  fontFamily: 'var(--mono)', fontSize: 11,
                  color: codeTab === t ? 'var(--ink)' : 'var(--ink-soft)', fontWeight: 600,
                  textTransform: 'uppercase', letterSpacing: '.06em'
                }}>{t}</button>
                )}
                </div>
              }
            </div>

            {/* Content */}
            <div style={{ flex: 1, minHeight: 0, overflow: 'auto', background: 'var(--paper-3)' }}>
              {tab === 'code' && <CodeView code={src[codeTab]} lang={codeTab} />}
              {tab === 'props' && <PropsView kind={widget.kind} />}
            </div>
            </>)}
          </section>

          {/* Right: AI chat */}
          <aside style={{ display: 'flex', flexDirection: 'column', minHeight: 0, background: 'var(--paper)' }}>
            <header style={{ padding: '14px 18px', borderBottom: '1px solid var(--rule)' }}>
              <div className="t-kicker" style={{ marginBottom: 2 }}>AI · ADJUST</div>
              <div style={{ fontFamily: 'var(--serif)', fontSize: 17 }}>Tell me what to change.</div>
              <div className="t-meta" style={{ marginTop: 4 }}>Edits run on the code, not the slide.</div>
            </header>
            <div ref={chatRef} style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {chatLog.map((m, i) => <ChatBubble key={i} role={m.role} text={m.text} attachments={m.attachments || []} />)}
              {busy &&
              <ChatBubble role="assistant">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '92%' }} />
                    <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '78%' }} />
                    <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '60%' }} />
                  </div>
                </ChatBubble>
              }
            </div>

            {/* Quick chips */}
            <div style={{ padding: '8px 14px 0', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {[
              'Change colors to amber',
              'Add a 5th option',
              'Make text bigger',
              'Make it dark-theme friendly'].
              map((s) =>
              <button key={s} onClick={() => setDraft(s)} style={{
                padding: '4px 9px', borderRadius: 'var(--r-pill)',
                border: '1px solid var(--rule)', background: 'var(--paper)',
                color: 'var(--ink-soft)', fontFamily: 'var(--sans)', fontSize: 11, cursor: 'pointer'
              }}>{s}</button>
              )}
            </div>

            <form onSubmit={onSendChat} style={{ padding: '10px 14px 14px', borderTop: '1px solid var(--rule)', marginTop: 8 }}>
              {/* Attached images preview */}
              {attachments.length > 0 && (
                <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginBottom: 8 }}>
                  {attachments.map((a, i) => (
                    <span key={i} className="scale-in" style={{
                      position:'relative', display:'inline-flex', alignItems:'center', gap:6,
                      padding:4, borderRadius:'var(--r-sm)',
                      border:'1px solid var(--rule)', background:'var(--paper-2)',
                      fontFamily:'var(--sans)', fontSize:11, color:'var(--ink)'
                    }}>
                      <img src={a.dataUrl} alt="" style={{ width:32, height:32, objectFit:'cover', borderRadius:'var(--r-xs)', display:'block' }}/>
                      <span style={{ maxWidth:120, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{a.name}</span>
                      <button type="button" onClick={() => setAttachments(prev => prev.filter((_, j) => j !== i))} style={{ background:'transparent', border:'none', color:'var(--ink-mute)', cursor:'pointer', padding:0, display:'inline-flex' }}><Icon name="x" size={11}/></button>
                    </span>
                  ))}
                </div>
              )}
              <div style={{ position: 'relative' }}>
                <textarea
                  rows={2}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {if (e.key === 'Enter' && !e.shiftKey) onSendChat(e);}}
                  className="input"
                  placeholder='e.g. "Change colors to amber" · ⏎ to send'
                  style={{ fontFamily: 'var(--sans)', fontSize: 13, resize: 'none', paddingRight: 76, paddingBottom: 30 }} data-comment-anchor="157aef2348-textarea-244-17" />

                {/* Attach image button — gated on model image support */}
                <input ref={fileInputRef} type="file" accept="image/*" multiple onChange={onPickFiles} style={{ display:'none' }}/>
                <Tooltip text={modelSupportsImage ? 'Attach image · model supports vision' : 'Current model does not support image input · enable in Settings → Advanced'}>
                  <button
                    type="button"
                    disabled={!modelSupportsImage}
                    onClick={() => fileInputRef.current?.click()}
                    style={{
                      position:'absolute', left: 6, bottom: 6, padding:'6px 8px',
                      background:'transparent', border:'1px solid var(--rule)',
                      borderRadius:'var(--r-sm)',
                      color: modelSupportsImage ? 'var(--ink-soft)' : 'var(--ink-disabled)',
                      cursor: modelSupportsImage ? 'pointer' : 'not-allowed',
                      display:'inline-flex', alignItems:'center', gap:4, fontSize:11, fontFamily:'var(--mono)'
                    }}
                  >
                    <Icon name="upload" size={12}/> Image
                  </button>
                </Tooltip>

                <button type="submit" disabled={(!draft.trim() && attachments.length === 0) || busy} className="btn btn-primary"
                style={{ position: 'absolute', right: 6, bottom: 6, padding: '6px 8px' }}>
                  <Icon name="arrow_right" size={13} />
                </button>
              </div>
              {modelSupportsImage && (
                <div className="t-mono" style={{ marginTop: 6, color:'var(--ink-mute)', fontSize:10 }}>
                  Drop a screenshot or click <em>Image</em> to send a visual reference.
                </div>
              )}
            </form>
          </aside>
        </div>
      </div>
    </Backdrop>);

};

/* ---------- Code view with light syntax tint ---------- */
const CodeView = ({ code, lang }) => {
  return (
    <pre style={{
      margin: 0, padding: '16px 20px',
      fontFamily: 'var(--mono)', fontSize: 12, lineHeight: 1.55,
      color: 'var(--ink)', whiteSpace: 'pre',
      background: 'var(--paper-3)'
    }} data-comment-anchor="f40e3cbe9a-pre-269-5">
      <code dangerouslySetInnerHTML={{ __html: tintCode(code, lang) }} />
    </pre>);

};
// minimal, safe tinting — strings, comments, keywords
function tintCode(code, lang) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  let s = esc(code);
  if (lang === 'js') {
    s = s.replace(/(\/\/[^\n]*)/g, '<span style="color:var(--ink-mute)">$1</span>');
    s = s.replace(/('[^']*'|"[^"]*"|`[^`]*`)/g, '<span style="color:var(--amber)">$1</span>');
    s = s.replace(/\b(const|let|var|function|return|if|else|for|of|in|new|class|export|import|from|async|await|=&gt;)\b/g, '<span style="color:var(--accent)">$1</span>');
  }
  if (lang === 'html') {
    s = s.replace(/(&lt;[\/!]?[a-zA-Z][^&]*?&gt;)/g, '<span style="color:var(--accent)">$1</span>');
    s = s.replace(/(class|data-[a-z-]+|id|href|src)=("[^"]*")/g, '<span style="color:var(--amber)">$1</span>=<span style="color:var(--meadow)">$2</span>');
  }
  if (lang === 'css') {
    s = s.replace(/(\/\*[^]*?\*\/)/g, '<span style="color:var(--ink-mute)">$1</span>');
    s = s.replace(/([.#:][a-zA-Z_-]+)/g, '<span style="color:var(--accent)">$1</span>');
    s = s.replace(/\b(\d+(?:px|em|rem|%)?)\b/g, '<span style="color:var(--amber)">$1</span>');
  }
  return s;
}

/* ---------- Props view ---------- */
const PropsView = ({ kind }) =>
<div style={{ padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 14, background: 'var(--paper)' }}>
    <div className="t-mono-up">Bound props</div>
    {kind === 'poll' || kind === 'plotter' || kind === 'function-plotter' ?
  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <PropRow label="Question" value="Which line is the 'best fit'?" />
        <PropRow label="Options" value="4 items" />
        <PropRow label="Anonymous votes" value="Allowed" />
        <PropRow label="Show results to audience" value="On submit" />
        <PropRow label="Close on advance" value="Yes" />
      </div> :

  <div className="t-meta">No bound props for this widget kind.</div>
  }
  </div>;

const PropRow = ({ label, value }) =>
<div style={{
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  padding: '10px 12px', border: '1px solid var(--rule)', borderRadius: 'var(--r-md)'
}}>
    <span style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)' }}>{label}</span>
    <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-soft)' }}>{value}</span>
  </div>;


/* ---------- Chat bubble ---------- */
const ChatBubble = ({ role, text, children, attachments = [] }) =>
<div style={{ display: 'flex', flexDirection: 'column', alignItems: role === 'user' ? 'flex-end' : 'flex-start' }}>
    {role === 'assistant' &&
  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 4, color: 'var(--accent)', fontFamily: 'var(--sans)', fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase' }}>
        <Icon name="sparkles" size={11} /> Assistant
      </div>
  }
    {attachments.length > 0 && (
      <div style={{ display:'flex', flexWrap:'wrap', gap:4, marginBottom:6 }}>
        {attachments.map((a, i) => (
          <img key={i} src={a.dataUrl} alt={a.name} style={{ width:60, height:60, objectFit:'cover', borderRadius:'var(--r-sm)', border:'1px solid var(--rule)' }}/>
        ))}
      </div>
    )}
    {text && (
      <div style={{
      maxWidth: '90%',
      background: role === 'user' ? 'var(--ink)' : 'var(--paper-2)',
      color: role === 'user' ? 'var(--paper)' : 'var(--ink)',
      padding: '10px 12px', borderRadius: 'var(--r-md)',
      border: role === 'user' ? 'none' : '1px solid var(--rule)',
      fontFamily: 'var(--serif)', fontSize: 14, lineHeight: 1.5,
      whiteSpace: 'pre-wrap'
      }}>
        {children ?? renderChatMarkdown(text)}
      </div>
    )}
    {children && !text && (
      <div style={{
      maxWidth: '90%',
      background: role === 'user' ? 'var(--ink)' : 'var(--paper-2)',
      color: role === 'user' ? 'var(--paper)' : 'var(--ink)',
      padding: '10px 12px', borderRadius: 'var(--r-md)',
      border: role === 'user' ? 'none' : '1px solid var(--rule)',
      fontFamily: 'var(--serif)', fontSize: 14, lineHeight: 1.5,
      whiteSpace: 'pre-wrap'
      }}>
        {children}
      </div>
    )}
  </div>;

const renderChatMarkdown = (text) => {
  // Render **bold** and `code` only.
  const parts = [];
  let key = 0;
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith('**')) parts.push(<strong key={key++}>{tok.slice(2, -2)}</strong>);else
    if (tok.startsWith('`')) parts.push(<code key={key++} style={{ fontFamily: 'var(--mono)', fontSize: '.92em', background: 'rgba(0,0,0,.06)', padding: '1px 5px', borderRadius: 4 }}>{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
};

window.WidgetAdjustPanel = WidgetAdjustPanel;