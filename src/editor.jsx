/* ============ SLAIDES — editor (instructor view) ============ */

/* Markdown → React renderer. Used by editor (for non-editable preview rendering of widgets),
   presenter, and audience. The editor canvas itself uses an editable HTML view backed by this
   same renderer.
*/
function renderInline(text) {
  const out = [];
  let rest = text;
  let key = 0;
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/;
  while (rest.length) {
    const m = rest.match(re);
    if (!m) {out.push(rest);break;}
    if (m.index > 0) out.push(rest.slice(0, m.index));
    const tok = m[0];
    if (tok.startsWith('**')) out.push(<strong key={key++}>{tok.slice(2, -2)}</strong>);else
    if (tok.startsWith('*')) out.push(<em key={key++}>{tok.slice(1, -1)}</em>);else
    if (tok.startsWith('`')) out.push(<code key={key++} style={{ fontFamily: 'var(--mono)', fontSize: '.92em', background: 'var(--paper-2)', padding: '1px 6px', borderRadius: 4 }}>{tok.slice(1, -1)}</code>);else
    if (tok.startsWith('[')) {
      const lm = tok.match(/\[([^\]]+)\]\(([^)]+)\)/);
      out.push(<a key={key++} href={lm[2]} style={{ color: 'var(--accent)', textDecoration: 'underline', textDecorationThickness: '1px', textUnderlineOffset: '3px' }}>{lm[1]}</a>);
    }
    rest = rest.slice(m.index + tok.length);
  }
  return out;
}

function renderMarkdown(md, opts = {}) {
  const lines = md.split(/\n/);
  const blocks = [];
  let para = [];
  const flush = () => {if (para.length) {blocks.push({ type: 'p', text: para.join(' ') });para = [];}};
  for (const line of lines) {
    if (!line.trim()) {flush();continue;}
    if (line.startsWith('# ')) {flush();blocks.push({ type: 'h1', text: line.slice(2) });continue;}
    if (line.startsWith('## ')) {flush();blocks.push({ type: 'h2', text: line.slice(3) });continue;}
    if (line.startsWith('### ')) {flush();blocks.push({ type: 'h3', text: line.slice(4) });continue;}
    if (line.startsWith('> ')) {flush();blocks.push({ type: 'quote', text: line.slice(2) });continue;}
    if (/^[-_]{3,}\s*$/.test(line)) {flush();blocks.push({ type: 'rule' });continue;}
    const widget = line.match(/^\{\{widget:([^}]+)\}\}\s*$/);
    if (widget) {flush();blocks.push({ type: 'widget', id: widget[1] });continue;}
    para.push(line);
  }
  flush();

  const { showWidgetChrome = false, onWidgetAdjust, widgetSpecs = [], audienceMode = false, live = false, slim = false } = opts;
  return blocks.map((b, i) => {
    switch (b.type) {
      case 'h1':
        return <h1 key={i} className={slim ? 't-h2' : 't-display'} style={{ margin: slim ? '0 0 12px' : '0 0 18px' }}>{renderInline(b.text)}</h1>;
      case 'h2':
        return <h2 key={i} className="t-h2" style={{ margin: '24px 0 12px' }}>{renderInline(b.text)}</h2>;
      case 'h3':
        return <h3 key={i} className="t-h3" style={{ margin: '24px 0 10px' }}>{renderInline(b.text)}</h3>;
      case 'rule':
        return <hr key={i} style={{ border: 'none', borderTop: '1px solid var(--ink)', width: 48, margin: '24px 0' }} />;
      case 'quote':
        return <blockquote key={i} style={{ margin: '18px 0', paddingLeft: 18, borderLeft: '2px solid var(--accent)', fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: slim ? 18 : 22, color: 'var(--ink-soft)', lineHeight: 1.55 }}>{renderInline(b.text)}</blockquote>;
      case 'widget':{
          const spec = widgetSpecs.find((w) => w.id === b.id) || { id: b.id, kind: 'unknown' };
          return (
            <div key={i} contentEditable={false} style={{ margin: '24px 0', position: 'relative' }}>
            {showWidgetChrome &&
              <div style={{ position: 'absolute', top: -12, left: 14, right: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', pointerEvents: 'none' }}>
                <span className="t-mono-up" style={{ background: 'var(--paper)', padding: '2px 8px', border: '1px solid var(--rule)', borderRadius: 'var(--r-xs)', pointerEvents: 'auto' }}>
                  WIDGET · {spec.kind} · #{spec.id}
                </span>
                {onWidgetAdjust &&
                <button onClick={(e) => {e.preventDefault();e.stopPropagation();onWidgetAdjust(spec);}} className="btn btn-sm" style={{ background: 'var(--paper)', pointerEvents: 'auto' }}>
                    <Icon name="settings" size={12} /> Adjust
                  </button>
                }
              </div>
              }
            <Widget spec={spec} audienceMode={audienceMode} live={live} />
          </div>);

        }
      case 'p':
      default:
        return <p key={i} className={slim ? 't-body-sans' : 't-body'} style={{ margin: '0 0 18px', color: 'var(--ink)' }}>{renderInline(b.text)}</p>;
    }
  });
}

window.renderMarkdown = renderMarkdown;

/* ---------- Editor screen ---------- */
const Editor = ({ deck, onBack, onStartSession, onOpenSettings }) => {
  const [activeId, setActiveId] = useState(deck.slides[0]?.id || null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState('sections');
  const [widgetPanel, setWidgetPanel] = useState(false);
  const [interpretPopover, setInterpretPopover] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [inlineChat, setInlineChat] = useState(null);
  const [widgetAdjust, setWidgetAdjust] = useState(null); // adjust panel for a widget
  const [hoverTop, setHoverTop] = useState(false);
  const [hoverBottom, setHoverBottom] = useState(false);

  const slides = deck.slides;
  const active = slides.find((s) => s.id === activeId) || slides[0];
  const hasWidget = (active?.widgets?.length || 0) > 0;
  const activeWidget = hasWidget ? active.widgets[0] : null;

  const closeMenus = () => setContextMenu(null);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {closeMenus();setInterpretPopover(null);setInlineChat(null);setWidgetAdjust(null);}
      if (e.metaKey && e.key === 'k') e.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handleContextMenu = (e) => {
    e.preventDefault();
    const sel = window.getSelection();
    const text = sel ? sel.toString() : '';
    setContextMenu({ x: e.clientX, y: e.clientY, kind: text ? 'text' : 'canvas', selection: text, hasWidget });
  };

  const onInterpret = () => {
    if (!contextMenu) return;
    const sel = contextMenu.selection;
    setInterpretPopover({ x: contextMenu.x, y: contextMenu.y, text: sel, response: null });
    setContextMenu(null);
    setTimeout(() => {
      setInterpretPopover((prev) => prev ? {
        ...prev,
        response: `"${sel.slice(0, 60)}" — in plain English, a function is a rule that pairs every input with exactly one output. Like a vending machine: press a button, get one specific snack.`
      } : null);
    }, 900);
  };

  const onGenerateWidget = () => {
    if (!contextMenu) return;
    if (hasWidget) { setContextMenu(null); return; }
    setInlineChat({ x: contextMenu.x, y: contextMenu.y, prompt: '', response: null });
    setContextMenu(null);
  };

  // Triggered from the WYSIWYG sparkles button — invoke Interpret using the live selection.
  const setInterpretPopoverFromSelection = ({ x, y, text }) => {
    setInterpretPopover({ x, y, text, response: null });
    setTimeout(() => {
      setInterpretPopover((prev) => prev ? {
        ...prev,
        response: `"${text.slice(0, 60)}" — in plain English, a function is a rule that pairs every input with exactly one output. Like a vending machine: press a button, get one specific snack.`
      } : null);
    }, 900);
  };

  const onOpenWidgetTab = () => {
    if (hasWidget) setWidgetAdjust(activeWidget);else
    setWidgetPanel(true);
  };

  // Track mouse position to show top "Add slide" / bottom "Add widget" CTAs
  const onCanvasMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const y = e.clientY - rect.top;
    setHoverTop(y >= 0 && y < 90);
    // Bottom pill: anywhere below the top "Add slide" zone
    setHoverBottom(y >= 90);
  };
  const onCanvasLeave = () => {setHoverTop(false);setHoverBottom(false);};

  return (
    <div style={{ height: '100vh', overflow: 'hidden', background: 'var(--paper)', display: 'flex', flexDirection: 'column' }} onClick={closeMenus}>

      {/* Top bar */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 20, height: 56, borderBottom: '1px solid var(--rule)', background: 'var(--paper)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button className="btn btn-ghost btn-sm" onClick={onBack} title="Back to library"><Icon name="arrow_left" size={16} /></button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Wordmark size={14} />
            <span className="t-meta">·</span>
            <span style={{ fontFamily: 'var(--serif)', fontSize: 17, letterSpacing: '-0.01em' }}>{deck.title}</span>
            <span style={{ background: 'var(--paper-2)', padding: '2px 7px', borderRadius: 'var(--r-xs)', fontSize: 11, color: 'var(--ink-soft)', fontFamily: 'var(--mono)' }}>draft</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn btn-sm"><Icon name="eye" size={14} /> Preview</button>
          <button className="btn btn-sm"><Icon name="download" size={14} /> Export</button>
          <button className="btn btn-ghost btn-sm" onClick={onOpenSettings}><Icon name="gear" size={16} /></button>
          <button className="btn btn-primary btn-sm" onClick={onStartSession}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--live)' }} />
            Start session
          </button>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: sidebarOpen ? '260px 1fr' : '44px 1fr', flex: 1, minHeight: 0, transition: 'grid-template-columns .2s ease' }}>

        <aside style={{ borderRight: '1px solid var(--rule)', background: 'var(--paper-2)', display: 'flex', flexDirection: 'column' }}>
          {sidebarOpen ?
          <SidebarOpen deck={deck} activeId={active?.id} setActiveId={setActiveId} tab={sidebarTab} setTab={setSidebarTab} onCollapse={() => setSidebarOpen(false)} onNewSlide={() => {}} /> :
          <SidebarCollapsed onExpand={() => setSidebarOpen(true)} onSelect={(t) => {setSidebarTab(t);setSidebarOpen(true);}} />
          }
        </aside>

        <main style={{ position: 'relative', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }} onContextMenu={handleContextMenu}>

          {/* Scrollable canvas */}
          <section
            onMouseMove={onCanvasMove}
            onMouseLeave={onCanvasLeave}
            style={{ flex: 1, overflowY: 'auto', width: '100%', position: 'relative' }}>
            
            {/* Top "Add slide" hover area */}
            <AddSlideRibbon visible={hoverTop} />

            <div style={{ maxWidth: 920, margin: '0 auto', padding: '56px 64px 96px' }} data-comment-anchor="07942c934a-div-232-13">
              {active &&
              <div className="fade-in">
                  <div className="t-kicker" style={{ marginBottom: 18 }}>{active.kicker || 'Untitled section'}</div>
                  <EditableSlide
                  key={active.id}
                  slide={active}
                  onWidgetAdjust={(w) => setWidgetAdjust(w)}
                  onInterpretSelection={(payload) => setInterpretPopoverFromSelection(payload)} />
                
                  <div style={{ marginTop: 48, paddingTop: 24, borderTop: '1px solid var(--rule-soft)', color: 'var(--ink-mute)', display: 'flex', justifyContent: 'space-between', fontSize: 12 }} data-comment-anchor="88723f0610-div-243-17">
                    <span className="t-mono">slide id · {active.id}</span>
                    <span className="t-mono">{hasWidget ? `widget · ${activeWidget.kind}` : 'no widget · 1 max per slide'}</span>
                  </div>

                  {/* Inline "Add widget" pill — sits right below the meta row, fades in on canvas hover */}
                  {!hasWidget && (
                    <AddWidgetRibbon
                      visible={hoverBottom}
                      onPick={() => setWidgetPanel(true)}
                      onGenerate={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        setInlineChat({ x: rect.left, y: rect.top - 8, prompt: '', response: null });
                      }}
                    />
                  )}
                </div>
              }
            </div>
          </section>

          <SlideStepper slides={slides} activeId={active?.id} onSelect={setActiveId} />
        </main>
      </div>

      {/* Right edge tab — adapts to "Add" / "Adjust" depending on whether slide has a widget */}
      <button
        onClick={onOpenWidgetTab}
        style={{
          position: 'fixed', right: 0, top: '50%', transform: 'translateY(-50%)',
          background: hasWidget ? 'var(--accent)' : 'var(--paper)',
          color: hasWidget ? '#fff' : 'var(--ink-soft)',
          border: '1px solid', borderColor: hasWidget ? 'var(--accent)' : 'var(--rule)',
          borderRight: 'none',
          borderRadius: 'var(--r-md) 0 0 var(--r-md)', padding: '14px 8px',
          cursor: 'pointer', writingMode: 'vertical-rl', textOrientation: 'mixed',
          fontFamily: 'var(--sans)', fontSize: 11, letterSpacing: '.15em', textTransform: 'uppercase', fontWeight: 600,
          display: 'flex', alignItems: 'center', gap: 8, boxShadow: 'var(--shadow-1)'
        }}
        title={hasWidget ? `Adjust widget · ${activeWidget.kind}` : 'Open widget collection'}>
        <Icon name={hasWidget ? 'settings' : 'widget'} size={14} /> {hasWidget ? 'Adjust widget' : 'Widgets'}
      </button>

      {/* Widget drawer (collection) */}
      <Drawer open={widgetPanel} onClose={() => setWidgetPanel(false)} width={420}>
        <WidgetCollection
          widgets={SEED.widgets}
          slideHasWidget={hasWidget}
          onClose={() => setWidgetPanel(false)}
          onInsert={() => setWidgetPanel(false)} />
        
      </Drawer>

      {/* Widget adjust panel */}
      {widgetAdjust &&
      <WidgetAdjustPanel
        widget={widgetAdjust}
        onClose={() => setWidgetAdjust(null)} />

      }

      {contextMenu &&
      <ContextMenu menu={contextMenu} onClose={() => setContextMenu(null)} onInterpret={onInterpret} onGenerateWidget={onGenerateWidget} onAdjustWidget={() => {setContextMenu(null);if (activeWidget) setWidgetAdjust(activeWidget);}} />
      }
      {interpretPopover && <InterpretPopover popover={interpretPopover} onClose={() => setInterpretPopover(null)} />}
      {inlineChat && <InlineChat state={inlineChat} setState={setInlineChat} onInsert={() => setInlineChat(null)} />}
    </div>);

};

/* ---------- Editable slide content + floating WYSIWYG toolbar ---------- */
const EditableSlide = ({ slide, onWidgetAdjust, onInterpretSelection }) => {
  const ref = useRef();
  const [toolbar, setToolbar] = useState(null); // { x, y } or null

  // Render markdown into the editable host on slide change ONLY (don't fight contenteditable on every keystroke).
  // We render React markdown nodes into a hidden container, then copy innerHTML into our editable host.
  const seedRef = useRef();
  useLayoutEffect(() => {
    if (!ref.current || !seedRef.current) return;
    ref.current.innerHTML = seedRef.current.innerHTML;
  }, [slide.id]);

  // Track selection → position floating toolbar
  useEffect(() => {
    const onSel = () => {
      const sel = document.getSelection();
      if (!sel || sel.rangeCount === 0) {setToolbar(null);return;}
      if (sel.isCollapsed) {setToolbar(null);return;}
      // Only show if selection is within the editable host
      const range = sel.getRangeAt(0);
      const container = range.commonAncestorContainer;
      const within = ref.current && (ref.current === container || ref.current.contains(container));
      if (!within) {setToolbar(null);return;}
      const rect = range.getBoundingClientRect();
      if (!rect.width && !rect.height) {setToolbar(null);return;}
      setToolbar({ x: rect.left + rect.width / 2, y: rect.top });
    };
    document.addEventListener('selectionchange', onSel);
    return () => document.removeEventListener('selectionchange', onSel);
  }, []);

  const exec = (cmd, val) => {
    // execCommand is deprecated but perfect for prototype-level WYSIWYG.
    document.execCommand(cmd, false, val);
    ref.current && ref.current.focus();
  };

  return (
    <>
      {/* Hidden seed — React renders the markdown here so we can copy innerHTML into the editable host */}
      <div ref={seedRef} style={{ display: 'none' }} aria-hidden="true">
        {renderMarkdown(slide.markdown, {
          showWidgetChrome: true,
          onWidgetAdjust,
          widgetSpecs: slide.widgets
        })}
      </div>

      {/* The real editable host */}
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        spellCheck={false}
        style={{
          fontFamily: 'var(--serif)', color: 'var(--ink)',
          outline: 'none', caretColor: 'var(--accent)',
          minHeight: 240, position: 'relative'
        }} />
      

      {toolbar &&
      <FloatingWysiwyg x={toolbar.x} y={toolbar.y} exec={exec} onInterpret={() => {
        const sel = document.getSelection();
        if (!sel || !sel.rangeCount) return;
        const range = sel.getRangeAt(0);
        const r = range.getBoundingClientRect();
        const text = sel.toString();
        // collapse the selection so the toolbar goes away once we hand off
        sel.removeAllRanges();
        onInterpretSelection && onInterpretSelection({ x: r.left + r.width/2 - 190, y: r.bottom, text });
      }} />
      }
    </>);

};

/* ---------- Floating WYSIWYG toolbar ---------- */
const FloatingWysiwyg = ({ x, y, exec, onInterpret }) => {
  // position above selection; clamp to viewport
  const HEIGHT = 40;
  const top = Math.max(8, y - HEIGHT - 8);
  return (
    <div
      onMouseDown={(e) => e.preventDefault()} // don't blur the selection
      className="scale-in"
      style={{
        position: 'fixed', top, left: x, transform: 'translateX(-50%)',
        zIndex: 70,
        background: 'var(--ink)', color: 'var(--paper)',
        borderRadius: 'var(--r-md)', padding: 4,
        boxShadow: 'var(--shadow-3)',
        display: 'inline-flex', alignItems: 'center', gap: 2,
        fontFamily: 'var(--sans)', fontSize: 13
      }}>
      
      <WysBtn label="B" onClick={() => exec('bold')} style={{ fontWeight: 700 }} />
      <WysBtn label={<i>I</i>} onClick={() => exec('italic')} style={{ fontStyle: 'italic' }} />
      <WysBtn label={<u>U</u>} onClick={() => exec('underline')} />
      <WysSep />
      <WysBtn label="H1" onClick={() => exec('formatBlock', 'H1')} />
      <WysBtn label="H2" onClick={() => exec('formatBlock', 'H2')} />
      <WysBtn label="¶" onClick={() => exec('formatBlock', 'P')} />
      <WysBtn label="“ ”" onClick={() => exec('formatBlock', 'BLOCKQUOTE')} />
      <WysSep />
      <WysIcon icon="code" onClick={() => {
        const sel = document.getSelection();
        if (!sel || !sel.rangeCount) return;
        const range = sel.getRangeAt(0);
        const code = document.createElement('code');
        code.style.cssText = "font-family:var(--mono);font-size:.92em;background:var(--paper-2);padding:1px 6px;border-radius:4px;color:var(--ink)";
        code.textContent = range.toString();
        range.deleteContents();
        range.insertNode(code);
      }} />
      <WysIcon icon="link" onClick={() => {
        const url = window.prompt('Link URL', 'https://');
        if (url) exec('createLink', url);
      }} />
      <WysSep />
      <WysIcon icon="sparkles" accent tooltip="Interpret with AI" onClick={() => onInterpret && onInterpret()} />
    </div>);

};
const WysBtn = ({ label, onClick, style }) =>
<button onMouseDown={(e) => e.preventDefault()} onClick={onClick}
style={{
  background: 'transparent', border: 'none', color: 'var(--paper)',
  padding: '6px 9px', borderRadius: 'var(--r-sm)', cursor: 'pointer',
  minWidth: 28, fontFamily: 'var(--sans)', fontSize: 13, ...style
}}
onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,.12)'}
onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
    {label}
  </button>;

const WysIcon = ({ icon, onClick, accent, tooltip }) => {
  const [hov, setHov] = useState(false);
  return (
    <span style={{ position:'relative', display:'inline-flex' }} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
      <button onMouseDown={(e) => e.preventDefault()} onClick={onClick}
        style={{
          background: 'transparent', border: 'none', color: accent ? '#8bb0ff' : 'var(--paper)',
          padding: '6px 8px', borderRadius: 'var(--r-sm)', cursor: 'pointer',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center'
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,.12)'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
        <Icon name={icon} size={14} />
      </button>
      {tooltip && hov && (
        <span style={{
          position:'absolute', bottom:'calc(100% + 6px)', left:'50%', transform:'translateX(-50%)',
          background:'var(--paper)', color:'var(--ink)',
          border:'1px solid var(--rule)', boxShadow:'var(--shadow-2)',
          padding:'4px 8px', borderRadius:'var(--r-sm)',
          fontFamily:'var(--sans)', fontSize:11, whiteSpace:'nowrap', pointerEvents:'none', zIndex: 80
        }}>{tooltip}</span>
      )}
    </span>
  );
};
const WysSep = () => <span style={{ width: 1, height: 18, background: 'rgba(255,255,255,.18)', margin: '0 2px' }} />;

/* ---------- Bottom "Add widget" hover ribbon — inline pill below the slide meta ---------- */
const AddWidgetRibbon = ({ visible, onPick, onGenerate }) =>
<div style={{
    display:'flex', justifyContent:'center',
    marginTop: 16,
    opacity: visible ? 1 : 0,
    transform: `translateY(${visible ? 0 : -4}px)`,
    transition: 'opacity .15s ease, transform .15s ease',
    pointerEvents: visible ? 'auto' : 'none'
  }}>
    <div
      style={{
        display:'inline-flex', alignItems:'center', gap:6,
        background:'var(--paper)', border:'1px solid var(--rule)',
        borderRadius:'var(--r-pill)', padding:4,
        boxShadow:'var(--shadow-2)',
        whiteSpace:'nowrap'
      }}>
      <button onClick={onPick} className="btn btn-sm" style={{ border:'none', background:'transparent', padding:'5px 10px' }}>
        <Icon name="plus" size={12}/> Add widget
      </button>
      <span style={{ width:1, height:18, background:'var(--rule)' }}/>
      <button onClick={onGenerate} className="btn btn-sm" style={{ border:'none', background:'transparent', padding:'5px 10px', color:'var(--accent)' }}>
        <Icon name="sparkles" size={12}/> Generate with AI
      </button>
    </div>
  </div>;


/* ---------- Sidebar open ---------- */
const SidebarOpen = ({ deck, activeId, setActiveId, tab, setTab, onCollapse, onNewSlide }) =>
<>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 14px 8px' }}>
      <div style={{ display: 'flex', gap: 4 }}>
        <button onClick={() => setTab('sections')} title="Sections" style={{
        border: 'none', background: tab === 'sections' ? 'var(--paper)' : 'transparent',
        color: tab === 'sections' ? 'var(--ink)' : 'var(--ink-soft)', borderRadius: 'var(--r-sm)',
        padding: '5px 8px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 12
      }}><Icon name="section" size={14} /> Sections</button>
        <button onClick={() => setTab('theme')} title="Theme & style" style={{
        border: 'none', background: tab === 'theme' ? 'var(--paper)' : 'transparent',
        color: tab === 'theme' ? 'var(--ink)' : 'var(--ink-soft)', borderRadius: 'var(--r-sm)',
        padding: '5px 8px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 12
      }}><Icon name="palette" size={14} /> Theme</button>
      </div>
      <button onClick={onCollapse} className="btn btn-ghost btn-sm" title="Collapse sidebar"><Icon name="chev_left" size={14} /></button>
    </div>

    <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px 14px' }}>
      {tab === 'sections' &&
    <>
          {deck.sections.map((sec) =>
      <div key={sec.id} style={{ marginBottom: 14 }}>
              <div className="t-mono-up" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px' }}>
                <Icon name="chev_down" size={12} /> {sec.title}
              </div>
              {sec.slideIds.map((sid) => {
          const s = deck.slides.find((x) => x.id === sid);
          if (!s) return null;
          const active = activeId === sid;
          return (
            <button key={sid} onClick={() => setActiveId(sid)} style={{
              width: '100%', textAlign: 'left', border: 'none',
              background: active ? 'var(--paper)' : 'transparent',
              borderLeft: active ? '2px solid var(--ink)' : '2px solid transparent',
              padding: '6px 10px 6px 22px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8
            }}>
                    <span style={{
                fontFamily: 'var(--serif)', fontSize: 13, color: active ? 'var(--ink)' : 'var(--ink-soft)',
                fontWeight: active ? 500 : 400, letterSpacing: '-0.005em', flex: 1, lineHeight: 1.3,
                overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box',
                WebkitLineClamp: 2, WebkitBoxOrient: 'vertical'
              }}>{s.title}</span>
                    {s.widgets?.length > 0 && <Icon name="widget" size={11} stroke="var(--accent)" />}
                  </button>);

        })}
            </div>
      )}
          <button onClick={onNewSlide} className="btn btn-ghost btn-sm" style={{ width: '100%', justifyContent: 'flex-start', color: 'var(--ink-soft)' }}>
            <Icon name="plus" size={13} /> New slide
          </button>
        </>
    }
      {tab === 'theme' &&
    <div style={{ padding: '4px 10px' }}>
          <div className="t-mono-up" style={{ marginBottom: 10 }}>Theme</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
        { name: 'Editorial Press', dot: '#1f3a8a', active: true },
        { name: 'Field Notes', dot: '#b4502b', active: false },
        { name: 'Riso Studio', dot: '#d34a2a', active: false }].
        map((t) =>
        <button key={t.name} style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
          border: t.active ? '1px solid var(--ink)' : '1px solid var(--rule)',
          background: t.active ? 'var(--paper)' : 'transparent',
          borderRadius: 'var(--r-sm)', cursor: 'pointer', textAlign: 'left'
        }}>
                <span style={{ width: 14, height: 14, borderRadius: 4, background: t.dot, flexShrink: 0 }} />
                <span style={{ fontSize: 13, fontWeight: t.active ? 600 : 400 }}>{t.name}</span>
                {t.active && <Icon name="check" size={14} style={{ marginLeft: 'auto' }} />}
              </button>
        )}
          </div>
          <div className="t-mono-up" style={{ marginTop: 24, marginBottom: 10 }}>Layout</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, color: 'var(--ink-soft)' }}>
            <label style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>Wide margins <Toggle on={true} /></label>
            <label style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>Drop caps <Toggle on={false} /></label>
            <label style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>Section marks <Toggle on={true} /></label>
          </div>
        </div>
    }
    </div>

    <div style={{ borderTop: '1px solid var(--rule)', padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span className="t-mono">v 0.1</span>
      <button className="btn btn-ghost btn-sm" title="Dark mode"><Icon name="moon" size={14} /></button>
    </div>
  </>;


const SidebarCollapsed = ({ onExpand, onSelect }) =>
<div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '14px 0', gap: 4 }}>
    <button onClick={onExpand} className="btn btn-ghost btn-sm" title="Expand sidebar"><Icon name="chev_right" size={14} /></button>
    <div style={{ height: 8 }} />
    <button onClick={() => onSelect('sections')} className="btn btn-ghost btn-sm" title="Sections"><Icon name="section" size={16} /></button>
    <button onClick={() => onSelect('theme')} className="btn btn-ghost btn-sm" title="Theme"><Icon name="palette" size={16} /></button>
    <div style={{ flex: 1 }} />
    <button className="btn btn-ghost btn-sm" title="Settings"><Icon name="gear" size={16} /></button>
  </div>;


/* ---------- Add-slide ribbon — only triggers near top ---------- */
const AddSlideRibbon = ({ visible }) =>
<div
  style={{
    position: 'sticky', top: 0, left: 0, right: 0, height: 0, zIndex: 8
  }}>
    <button
    data-comment-anchor="0c63b8a943-button-421-5"
    className="btn btn-sm"
    style={{
      position: 'absolute', top: 18, left: '50%', transform: 'translateX(-50%)',
      background: 'var(--paper)', boxShadow: 'var(--shadow-2)',
      opacity: visible ? 0.95 : 0,
      transform: `translateX(-50%) translateY(${visible ? 0 : -6}px)`,
      transition: 'opacity .15s ease, transform .15s ease',
      pointerEvents: visible ? 'auto' : 'none'
    }}>
      <Icon name="plus" size={12} /> Add slide above
    </button>
  </div>;


/* ---------- Stepper ---------- */
const SlideStepper = ({ slides, activeId, onSelect }) => {
  const idx = slides.findIndex((s) => s.id === activeId);
  const prev = idx > 0 ? slides[idx - 1] : null;
  const next = idx < slides.length - 1 ? slides[idx + 1] : null;
  return (
    <footer style={{
      position: 'sticky', bottom: 0, background: 'var(--paper)', borderTop: '1px solid var(--rule)',
      height: 48, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', zIndex: 5
    }}>
      <button onClick={() => prev && onSelect(prev.id)} disabled={!prev} className="btn btn-ghost btn-sm"><Icon name="chev_left" size={14} /> Prev</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {slides.map((s) =>
        <button key={s.id} onClick={() => onSelect(s.id)} title={s.title} style={{
          width: 24, height: 4, borderRadius: 2, border: 'none', padding: 0,
          background: s.id === activeId ? 'var(--ink)' : 'var(--rule-strong)',
          cursor: 'pointer', transition: 'background .15s'
        }} />
        )}
        <span className="t-mono" style={{ marginLeft: 10 }}>{idx + 1} / {slides.length}</span>
      </div>
      <button onClick={() => next && onSelect(next.id)} disabled={!next} className="btn btn-ghost btn-sm">Next <Icon name="chev_right" size={14} /></button>
    </footer>);

};

/* ---------- Context menu ---------- */
const ContextMenu = ({ menu, onClose, onInterpret, onGenerateWidget, onAdjustWidget }) => {
  const hasText = menu.kind === 'text' && menu.selection.trim().length > 0;
  const widgetTaken = !!menu.hasWidget;
  return (
    <div
      onClick={(e) => e.stopPropagation()}
      className="scale-in"
      style={{
        position: 'fixed', top: menu.y + 4, left: menu.x + 4, zIndex: 60,
        background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 'var(--r-md)',
        boxShadow: 'var(--shadow-3)', padding: 6, minWidth: 240, fontFamily: 'var(--sans)', fontSize: 13
      }}>
      
      {hasText && <MenuLabel>"{menu.selection.slice(0, 32)}{menu.selection.length > 32 ? '…' : ''}"</MenuLabel>}
      <MenuItem icon="copy" onClick={onClose}>Copy <Kbd>⌘C</Kbd></MenuItem>
      {hasText && <MenuItem icon="sparkles" onClick={onInterpret} accent>Interpret with AI</MenuItem>}
      <MenuItem icon="edit" onClick={onClose}>Cut <Kbd>⌘X</Kbd></MenuItem>
      <MenuItem icon="copy" onClick={onClose}>Paste <Kbd>⌘V</Kbd></MenuItem>
      <Divider />
      {widgetTaken ?
      <MenuItem icon="settings" onClick={onAdjustWidget}>Adjust widget…</MenuItem> :

      <>
          <MenuItem icon="sparkles" onClick={onGenerateWidget}>Generate widget…</MenuItem>
          <MenuItem icon="widget" onClick={onClose}>Insert from collection…</MenuItem>
        </>
      }
      {widgetTaken && <div style={{ padding: '4px 10px', fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--ink-mute)' }}>1 widget per slide · max reached</div>}
      <Divider />
      <MenuItem icon="md" onClick={onClose}>Edit as Markdown</MenuItem>
    </div>);

};
const MenuItem = ({ icon, onClick, children, accent, disabled }) =>
<button onClick={disabled ? undefined : onClick}
style={{
  width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', border: 'none', borderRadius: 'var(--r-sm)',
  background: 'transparent', color: disabled ? 'var(--ink-disabled)' : accent ? 'var(--accent)' : 'var(--ink)',
  textAlign: 'left', cursor: disabled ? 'not-allowed' : 'pointer', fontSize: 13
}}
onMouseEnter={(e) => {if (!disabled) e.currentTarget.style.background = 'var(--paper-2)';}}
onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
    <Icon name={icon} size={14} /> <span style={{ flex: 1 }}>{children}</span>
  </button>;

const MenuLabel = ({ children }) => <div style={{ padding: '4px 10px 8px', fontSize: 11, color: 'var(--ink-mute)', fontFamily: 'var(--mono)', borderBottom: '1px solid var(--rule-soft)', marginBottom: 4 }}>{children}</div>;
const Divider = () => <div style={{ height: 1, background: 'var(--rule-soft)', margin: '4px 0' }} />;
const Kbd = ({ children }) => <span className="kbd" style={{ marginLeft: 'auto' }}>{children}</span>;

/* ---------- Interpret popover ---------- */
const InterpretPopover = ({ popover, onClose }) => {
  const ref = useRef();
  useEffect(() => {ref.current && ref.current.focus();}, []);
  return (
    <div onClick={(e) => e.stopPropagation()} className="scale-in" style={{
      position: 'fixed', top: popover.y + 8, left: popover.x + 8, zIndex: 60,
      width: 380, background: 'var(--paper)', border: '1px solid var(--rule)',
      borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-3)', padding: 16
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--accent)', fontSize: 12, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' }}>
          <Icon name="sparkles" size={14} /> Interpret
        </span>
        <button onClick={onClose} className="btn btn-ghost btn-sm"><Icon name="x" size={14} /></button>
      </div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-soft)', padding: '8px 10px', background: 'var(--paper-2)', borderRadius: 'var(--r-sm)', marginBottom: 10 }}>
        "{popover.text}"
      </div>
      <input ref={ref} className="input" placeholder="how to interpret — e.g. 'in plain english', 'translate to Thai'" defaultValue="in plain English" style={{ marginBottom: 12 }} />
      {popover.response ?
      <div style={{ fontFamily: 'var(--serif)', fontSize: 15, lineHeight: 1.55, color: 'var(--ink)' }}>{popover.response}</div> :
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '92%' }} />
          <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '80%' }} />
          <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '60%' }} />
        </div>
      }
      <div style={{ marginTop: 14, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button className="btn btn-sm">Copy</button>
        <button className="btn btn-primary btn-sm">Insert below</button>
      </div>
    </div>);

};

/* ---------- Inline AI chat — anchored popover, not a modal ---------- */
const InlineChat = ({ state, setState, onInsert }) => {
  const [prompt, setPrompt] = useState(state.prompt || '');
  const [response, setResponse] = useState(state.response);
  const [busy, setBusy] = useState(false);
  const ref = useRef();
  // close on outside click
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setState(null); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const onRun = () => {
    setBusy(true);
    setResponse(null);
    setTimeout(() => {
      setResponse('A confidence slider from 0–100. Live median streams to the presenter. Median updates every 250ms; presenter view shows distribution.');
      setBusy(false);
    }, 900);
  };
  // Clamp position to viewport
  const W = 460;
  const left = Math.min(Math.max(8, state.x), window.innerWidth - W - 8);
  const top  = Math.min(Math.max(8, state.y + 8), window.innerHeight - 200);
  return (
    <div ref={ref} onClick={(e) => e.stopPropagation()} className="scale-in" style={{
      position:'fixed', top, left, width: W, zIndex: 65,
      background:'var(--paper)', border:'1px solid var(--rule)', borderRadius:'var(--r-md)',
      boxShadow:'var(--shadow-3)', padding: 14
    }} data-comment-anchor="ece65a3efc-div-712-7">
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom: 10 }}>
        <span style={{ display:'inline-flex', alignItems:'center', gap: 6, color:'var(--accent)', fontSize: 11, fontWeight: 700, letterSpacing:'.1em', textTransform:'uppercase' }}>
          <Icon name="sparkles" size={13} stroke="var(--accent)"/> Inline · generate widget
        </span>
        <button onClick={() => setState(null)} className="btn btn-ghost btn-sm" style={{ padding:'2px 4px' }}><Icon name="x" size={12}/></button>
      </div>
      <textarea
        autoFocus
        rows={2}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onRun(); } if (e.key === 'Escape') setState(null); }}
        className="input"
        placeholder="describe the interaction you want…  ⏎ to send"
        style={{ fontFamily:'var(--sans)', fontSize: 13, resize:'none' }}
      />
      <div style={{ display:'flex', justifyContent:'space-between', marginTop: 10 }}>
        <span className="t-mono" style={{ color:'var(--ink-mute)' }}>inserts a single widget on this slide</span>
        <button onClick={onRun} disabled={!prompt || busy} className="btn btn-primary btn-sm">
          <Icon name="sparkles" size={13} /> {busy ? 'Drafting…' : 'Draft'}
        </button>
      </div>
      {busy && (
        <div style={{ marginTop: 12, display:'flex', flexDirection:'column', gap: 6 }}>
          <span className="pulse" style={{ height: 6, borderRadius: 3, background:'var(--accent-tint)', width:'92%' }}/>
          <span className="pulse" style={{ height: 6, borderRadius: 3, background:'var(--accent-tint)', width:'78%' }}/>
          <span className="pulse" style={{ height: 6, borderRadius: 3, background:'var(--accent-tint)', width:'60%' }}/>
        </div>
      )}
      {response && (
        <div className="scale-in" style={{ marginTop: 12, padding: 12, border:'1px solid var(--rule)', borderRadius:'var(--r-md)' }}>
          <div className="t-kicker" style={{ marginBottom: 6 }}>Draft</div>
          <p style={{ fontFamily:'var(--serif)', fontSize: 14, lineHeight: 1.5, margin: 0 }}>{response}</p>
          <div style={{ marginTop: 10, display:'flex', gap: 6 }}>
            <button className="btn btn-primary btn-sm" onClick={onInsert}><Icon name="plus" size={12}/> Insert</button>
            <button className="btn btn-sm"><Icon name="code" size={12}/> Edit code</button>
          </div>
        </div>
      )}
    </div>
  );
};

window.Editor = Editor;