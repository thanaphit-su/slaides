/* ============ SLAIDES — presenter view (live) ============ */

/* Session-only interaction slides:
   - Inserted right after the current original slide
   - Use the inverted theme of the current page (light↔dark)
   - Never mutate the source deck. Kept in `liveSlides` and serialized into the session transcript.
*/

const Presenter = ({ deck, session, onExit, onOpenSettings }) => {
  const [dark, setDark] = useState(false);
  const [liveSlides, setLiveSlides] = useState(() => deck.slides.map(s => ({ ...s, source: 'deck' })));
  const [activeIdx, setActiveIdx] = useState(0);
  const [questionsOpen, setQuestionsOpen] = useState(false);
  const [actionMenu, setActionMenu] = useState(false);
  const [shareTip, setShareTip] = useState(false);
  const [interpretPopover, setInterpretPopover] = useState(null);
  const [sessionHistory, setSessionHistory] = useState([]); // append-only log of inserted interaction slides

  const slides = liveSlides;
  const active = slides[activeIdx];
  const questions = session.pendingQuestions || [];

  const next = () => setActiveIdx(i => Math.min(slides.length-1, i+1));
  const prev = () => setActiveIdx(i => Math.max(0, i-1));

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'ArrowRight') setActiveIdx(i => Math.min(slides.length-1, i+1));
      if (e.key === 'ArrowLeft')  setActiveIdx(i => Math.max(0, i-1));
      if (e.key === 'Escape') { setActionMenu(false); setInterpretPopover(null); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [slides.length]);

  const insertInteraction = (kind) => {
    const insertAfter = activeIdx;
    const parent = slides[insertAfter];
    const interactionSlide = makeInteractionSlide({ kind, parentSlide: parent, inverted: !dark });
    setLiveSlides(prev => [
      ...prev.slice(0, insertAfter + 1),
      interactionSlide,
      ...prev.slice(insertAfter + 1),
    ]);
    setSessionHistory(h => [...h, {
      id: interactionSlide.id,
      kind,
      atIdx: insertAfter + 1,
      parentSlideId: parent?.id,
      openedAt: new Date().toISOString(),
    }]);
    setActionMenu(false);
    // navigate after react state flush
    setTimeout(() => setActiveIdx(insertAfter + 1), 0);
  };

  const copyShare = () => {
    setShareTip(true);
    setTimeout(() => setShareTip(false), 1500);
  };

  const onContextSlide = (e) => {
    e.preventDefault();
    const sel = window.getSelection();
    const text = sel ? sel.toString() : '';
    if (text) {
      setInterpretPopover({ x: e.clientX, y: e.clientY, text, response: null });
      setTimeout(() => setInterpretPopover(prev => prev ? {
        ...prev,
        response: `"${text.slice(0,60)}" — a quick definition: a function is a deterministic rule, one input ⟶ one output. Think of it as a vending machine that never gets confused about your order.`
      } : null), 850);
    }
  };

  // Compute the theme class for the slide stage (interaction slides invert)
  const slideEffectiveDark = active?.invertTheme ? !dark : dark;
  const slideThemeClass = slideEffectiveDark ? 'dark' : 'light';

  return (
    <div className={dark ? 'dark' : 'light'} style={{ height:'100vh', overflow:'hidden', background:'var(--paper)', display:'flex', flexDirection:'column' }}>

      {/* Top bar */}
      <header style={{
        position:'sticky', top:0, zIndex:20, height:52, borderBottom:'1px solid var(--rule)', background:'var(--paper)',
        display:'flex', alignItems:'center', justifyContent:'space-between', padding:'0 18px'
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:14 }}>
          <button className="btn btn-ghost btn-sm" onClick={onExit} title="Exit session"><Icon name="x" size={14}/></button>
          <Wordmark size={13}/>
          <span className="t-meta">·</span>
          <span style={{ fontFamily:'var(--serif)', fontSize:15 }}>{deck.title}</span>
          <span className="badge badge-live"><LiveDot color="#fff" size={6}/> LIVE</span>
          <span className="t-meta" style={{ whiteSpace:'nowrap' }}>{session.startedAt}</span>
          {sessionHistory.length > 0 && (
            <span className="badge badge-accent" title={`${sessionHistory.length} interaction slide${sessionHistory.length===1?'':'s'} this session`}>
              <Icon name="sparkles" size={10}/> {sessionHistory.length} interaction{sessionHistory.length===1?'':'s'}
            </span>
          )}
        </div>

        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          {/* Audience count */}
          <Tooltip text={`${session.audienceCount} attending`}>
            <span style={{
              display:'inline-flex', alignItems:'center', gap:6, padding:'4px 10px',
              border:'1px solid var(--rule)', borderRadius:'var(--r-pill)',
              fontFamily:'var(--mono)', fontSize:12
            }}>
              <Icon name="user" size={12}/> {session.audienceCount}
            </span>
          </Tooltip>

          <button onClick={() => setQuestionsOpen(true)} className="btn btn-sm" style={{ position:'relative' }} title="Pending questions">
            <Icon name="question" size={14}/> {questions.length}
            {questions.length > 0 && (
              <span style={{
                position:'absolute', top:-4, right:-4, width:10, height:10, borderRadius:'50%',
                background:'var(--live)', border:'2px solid var(--paper)'
              }}/>
            )}
          </button>

          <div style={{ position:'relative' }}>
            <button onClick={copyShare} className="btn btn-sm">
              <Icon name="link" size={14}/> <span style={{ fontFamily:'var(--mono)', fontSize:12 }}>{session.shareCode}</span>
            </button>
            {shareTip && (
              <div className="scale-in" style={{
                position:'absolute', top:'calc(100% + 6px)', right:0, background:'var(--ink)', color:'var(--paper)',
                padding:'6px 10px', borderRadius:'var(--r-sm)', fontSize:11, whiteSpace:'nowrap', zIndex:30
              }}>Link copied · {session.shareUrl}</div>
            )}
          </div>

          <button onClick={() => setDark(d => !d)} className="btn btn-ghost btn-sm" title="Dark mode">
            <Icon name={dark ? 'sun' : 'moon'} size={15}/>
          </button>

          <button onClick={onOpenSettings} className="btn btn-ghost btn-sm"><Icon name="gear" size={16}/></button>
        </div>
      </header>

      <div style={{ display:'grid', gridTemplateColumns: questionsOpen ? '1fr 360px' : '1fr', flex:1, minHeight:0, transition:'grid-template-columns .2s ease' }}>

        {/* Slide stage */}
        <main onContextMenu={onContextSlide} style={{ position:'relative', display:'flex', flexDirection:'column', overflow:'hidden', minHeight:0 }}>
          <section className={slideThemeClass} style={{ flex:1, overflowY:'auto', width:'100%', background:'var(--paper)', color:'var(--ink)', transition:'background .25s ease, color .25s ease' }}>
            <div style={{ maxWidth:1100, margin:'0 auto', padding:'72px 88px 96px', minHeight:'100%', boxSizing:'border-box' }}>
              {active && (active.isInteraction
                ? <InteractionSlide slide={active} onUpdate={(patch) => {
                    setLiveSlides(prev => prev.map(s => s.id === active.id ? { ...s, ...patch } : s));
                  }}/>
                : <RegularSlide slide={active}/>
              )}
            </div>
          </section>

          {/* Bottom bar */}
          <footer style={{
            borderTop:'1px solid var(--rule)', height:56, padding:'0 24px',
            display:'flex', alignItems:'center', justifyContent:'space-between', background:'var(--paper)'
          }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setDark(d => !d)}>
              <Icon name={dark ? 'sun' : 'moon'} size={14}/> {dark ? 'Light' : 'Dark'} mode
            </button>

            <div style={{ display:'flex', alignItems:'center', gap:14 }}>
              <button className="btn btn-ghost btn-sm" onClick={prev} disabled={activeIdx === 0}>
                <Icon name="chev_left" size={14}/> Prev
              </button>
              <span style={{ display:'inline-flex', gap:4, alignItems:'center' }}>
                {slides.map((s,i) => (
                  <span key={s.id} title={s.title} style={{
                    width: i === activeIdx ? 16 : 6, height:4, borderRadius:2,
                    background: i === activeIdx
                      ? (s.isInteraction ? 'var(--accent)' : 'var(--ink)')
                      : (s.isInteraction ? 'var(--accent-tint)' : 'var(--rule-strong)'),
                    transition:'all .2s'
                  }}/>
                ))}
              </span>
              <span className="t-mono">{activeIdx+1} / {slides.length}</span>
              <button className="btn btn-ghost btn-sm" onClick={next} disabled={activeIdx === slides.length-1}>
                Next <Icon name="chev_right" size={14}/>
              </button>
            </div>
          </footer>

          {/* Floating FAB */}
          <div style={{ position:'absolute', right:24, bottom:76, zIndex:15 }}>
            {actionMenu && (
              <div className="scale-in" style={{
                position:'absolute', bottom:'calc(100% + 10px)', right:0,
                background:'var(--paper)', border:'1px solid var(--rule)', borderRadius:'var(--r-md)',
                boxShadow:'var(--shadow-3)', padding:6, minWidth:240
              }}>
                <MenuItem icon="poll"     onClick={() => insertInteraction('poll')}>Open poll as new slide</MenuItem>
                <MenuItem icon="question" onClick={() => insertInteraction('question')}>Open question as new slide</MenuItem>
                <Divider/>
                <MenuItem icon="widget" onClick={() => setActionMenu(false)}>From widget library…</MenuItem>
                <div style={{ padding:'6px 10px', fontFamily:'var(--mono)', fontSize:10, color:'var(--ink-soft)', borderTop:'1px solid var(--rule-soft)', marginTop:4 }}>
                  Inserted as a session-only slide.<br/>
                  Original deck stays untouched.
                </div>
              </div>
            )}
            <FabInteraction open={actionMenu} onClick={() => setActionMenu(m => !m)}/>
          </div>
        </main>

        {questionsOpen && (
          <QuestionsRail
            questions={questions}
            session={session}
            onClose={() => setQuestionsOpen(false)}
          />
        )}
      </div>

      {interpretPopover && (
        <InterpretPopover popover={interpretPopover} onClose={() => setInterpretPopover(null)}/>
      )}
    </div>
  );
};

/* ---------- Regular slide ---------- */
const RegularSlide = ({ slide }) => (
  <div className="fade-in" key={slide.id}>
    <div className="t-kicker" style={{ marginBottom:18 }}>{slide.kicker || ''}</div>
    {renderMarkdown(slide.markdown, { widgetSpecs: slide.widgets, live: true })}
  </div>
);

/* ---------- Interaction slide (poll or open question, full-bleed) ---------- */
const InteractionSlide = ({ slide, onUpdate }) => {
  if (slide.kind === 'poll') {
    return <PollInteractionSlide slide={slide} onUpdate={onUpdate}/>;
  }
  if (slide.kind === 'question') {
    return <QuestionInteractionSlide slide={slide} onUpdate={onUpdate}/>;
  }
  return null;
};

const PollInteractionSlide = ({ slide, onUpdate }) => {
  // Live-vote simulation
  const [results, setResults] = useState(slide.results || [3, 5, 2, 1]);
  const total = results.reduce((a,b) => a+b, 0);
  useEffect(() => {
    const t = setInterval(() => {
      setResults(r => {
        const idx = Math.floor(Math.random() * r.length);
        const updated = r.slice();
        updated[idx] += 1;
        return updated;
      });
    }, 2400);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="fade-in" key={slide.id} style={{ display:'flex', flexDirection:'column', gap:24 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div className="t-kicker">{slide.kicker}</div>
        <span style={{ display:'inline-flex', alignItems:'center', gap:8, fontFamily:'var(--mono)', fontSize:11, color:'var(--ink-soft)' }}>
          <LiveDot/> {total} votes
        </span>
      </div>
      <h1 className="t-h1" style={{ margin:0 }}>{renderInline(slide.question)}</h1>
      <p className="t-lede" style={{ margin:0 }}>{slide.lede}</p>
      <div style={{ display:'flex', flexDirection:'column', gap:14, marginTop:8 }}>
        {slide.options.map((opt, i) => {
          const pct = total ? Math.round((results[i] / total) * 100) : 0;
          return (
            <div key={i} style={{
              position:'relative', overflow:'hidden',
              border:'1.5px solid var(--rule)',
              borderRadius:'var(--r-lg)',
              padding:'18px 22px', background:'var(--paper)',
              display:'flex', alignItems:'center', justifyContent:'space-between', gap:18,
            }}>
              <span style={{
                position:'absolute', inset:0,
                background:'var(--accent-soft)', width:`${pct}%`,
                transition:'width .6s cubic-bezier(.2,.7,.2,1)', pointerEvents:'none'
              }}/>
              <span style={{ position:'relative', display:'inline-flex', alignItems:'center', gap:18 }}>
                <span style={{
                  width:32, height:32, borderRadius:'50%', background:'var(--paper-2)', color:'var(--ink)',
                  display:'inline-flex', alignItems:'center', justifyContent:'center',
                  fontFamily:'var(--mono)', fontSize:13, fontWeight:600, flexShrink:0
                }}>{String.fromCharCode(65+i)}</span>
                <span style={{ fontFamily:'var(--serif)', fontSize:22, letterSpacing:'-0.015em' }}>{opt}</span>
              </span>
              <span style={{ position:'relative', fontFamily:'var(--mono)', fontSize:14, color:'var(--ink-soft)', flexShrink:0 }}>
                {results[i]} <span style={{ color:'var(--ink-mute)' }}>· {pct}%</span>
              </span>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop:12, paddingTop:14, borderTop:'1px solid var(--rule-soft)', display:'flex', justifyContent:'space-between' }}>
        <span className="t-mono">interaction slide · session-only · #{slide.id.slice(-6)}</span>
        <span className="t-mono">closes when you advance →</span>
      </div>
    </div>
  );
};

const QuestionInteractionSlide = ({ slide }) => {
  // Live answers stream
  const seed = ['mapping', 'rule', 'box', 'transform', 'input → output', 'function', 'a graph', 'one-to-one', 'recipe', 'machine'];
  const [answers, setAnswers] = useState(seed.slice(0, 3).map((t, i) => ({ id: `a-${i}`, text: t, at: `${i+1}m ago` })));
  useEffect(() => {
    let idx = 3;
    const t = setInterval(() => {
      if (idx >= seed.length) return;
      const text = seed[idx++];
      setAnswers(a => [{ id: `a-${Date.now()}`, text, at: 'just now' }, ...a]);
    }, 2400);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="fade-in" key={slide.id} style={{ display:'flex', flexDirection:'column', gap:20 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div className="t-kicker">{slide.kicker}</div>
        <span style={{ display:'inline-flex', alignItems:'center', gap:8, fontFamily:'var(--mono)', fontSize:11, color:'var(--ink-soft)' }}>
          <LiveDot/> {answers.length} answers
        </span>
      </div>
      <h1 className="t-h1" style={{ margin:0 }}>{renderInline(slide.question)}</h1>
      <p className="t-lede" style={{ margin:0 }}>{slide.lede}</p>
      <div style={{ display:'flex', flexWrap:'wrap', gap:12, marginTop:18 }}>
        {answers.map((a, i) => (
          <span key={a.id} className={i === 0 ? 'scale-in' : ''} style={{
            padding:'10px 18px', borderRadius:'var(--r-pill)',
            border:'1px solid var(--rule)', background:'var(--paper)',
            fontFamily:'var(--serif)', fontSize: 16 + (10 - i) * 1, letterSpacing:'-0.005em',
            color:'var(--ink)'
          }}>
            "{a.text}" <span className="t-mono" style={{ marginLeft:8, fontSize:10 }}>{a.at}</span>
          </span>
        ))}
      </div>
      <div style={{ marginTop:12, paddingTop:14, borderTop:'1px solid var(--rule-soft)', display:'flex', justifyContent:'space-between' }}>
        <span className="t-mono">interaction slide · session-only · #{slide.id.slice(-6)}</span>
        <span className="t-mono">replies stream live →</span>
      </div>
    </div>
  );
};

/* ---------- Build an interaction slide spec ---------- */
function makeInteractionSlide({ kind, parentSlide, inverted }) {
  const id = `live-${kind}-${Date.now().toString(36)}`;
  if (kind === 'poll') {
    return {
      id, source:'session', isInteraction:true, invertTheme: inverted, kind,
      kicker: `LIVE POLL — after § ${parentSlide?.kicker || ''}`.replace('LIVE POLL — after § §', 'LIVE POLL — after').slice(0, 80),
      title: 'Live poll',
      question: 'Which describes a *function* best?',
      lede: 'Pick the one that maps closest to how you\'d explain it to a friend. Results stream as they come in.',
      options: [
        'A box that maps inputs to outputs',
        'A rule with one answer per input',
        'A formula like y = mx + b',
        'A graph drawn on paper',
      ],
      results: [3, 5, 2, 1],
    };
  }
  if (kind === 'question') {
    return {
      id, source:'session', isInteraction:true, invertTheme: inverted, kind,
      kicker: `LIVE QUESTION — after § ${parentSlide?.kicker || ''}`.slice(0, 80),
      title: 'Live question',
      question: 'In *one word* — what is a function?',
      lede: 'Type the first word that comes to mind. Submissions appear here in realtime.',
    };
  }
  return null;
}

/* ---------- Right rail: questions ---------- */
const QuestionsRail = ({ questions, session, onClose }) => (
  <aside className="slide-in-right" style={{ borderLeft:'1px solid var(--rule)', background:'var(--paper-2)', display:'flex', flexDirection:'column', minHeight:0 }}>
    <header style={{ padding:'14px 18px', borderBottom:'1px solid var(--rule)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
      <div>
        <div className="t-kicker">Live questions</div>
        <div style={{ fontFamily:'var(--serif)', fontSize:18 }}>From the room</div>
      </div>
      <button className="btn btn-ghost btn-sm" onClick={onClose}><Icon name="x" size={14}/></button>
    </header>
    <div style={{ flex:1, overflowY:'auto', padding:'10px 12px' }}>
      {questions.length === 0 && (
        <div style={{ textAlign:'center', padding:36, color:'var(--ink-soft)' }}>
          <Icon name="question" size={28}/>
          <p style={{ fontFamily:'var(--serif)', fontSize:14, marginTop:10 }}>No questions yet.<br/>The room is reading.</p>
        </div>
      )}
      {questions.map(q => (
        <article key={q.id} style={{
          background:'var(--paper)', border:'1px solid var(--rule)', borderRadius:'var(--r-md)',
          padding:'12px 14px', marginBottom:10
        }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
            <span style={{ display:'inline-flex', alignItems:'center', gap:6 }}>
              {q.anon ? (
                <span className="badge" style={{ background:'var(--paper-3)' }}>anon</span>
              ) : (
                <span style={{
                  width:22, height:22, borderRadius:'50%', background:'var(--accent-soft)', color:'var(--accent)',
                  display:'inline-flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:700
                }}>{q.from.slice(0,1)}</span>
              )}
              <span style={{ fontSize:12, fontWeight:600 }}>{q.anon ? 'Anonymous' : q.from}</span>
            </span>
            <span className="t-mono">{q.at}</span>
          </div>
          <p style={{ fontFamily:'var(--serif)', fontSize:15, lineHeight:1.5, margin:'0 0 10px', color:'var(--ink)' }}>{q.text}</p>
          <div style={{ display:'flex', gap:6 }}>
            <button className="btn btn-sm"><Icon name="check" size={13}/> Mark answered</button>
            <button className="btn btn-sm"><Icon name="arrow_right" size={13}/> Jump to slide</button>
          </div>
        </article>
      ))}
    </div>
    <footer style={{ padding:'10px 14px', borderTop:'1px solid var(--rule)', fontFamily:'var(--mono)', fontSize:11, color:'var(--ink-soft)' }}>
      {session.audienceCount} attending · {questions.length} pending
    </footer>
  </aside>
);

window.Presenter = Presenter;

/* ---------- FAB: circle that expands to pill on hover/open ---------- */
const FabInteraction = ({ open, onClick }) => {
  const [hover, setHover] = useState(false);
  const expanded = open || hover;
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title="Open interaction"
      style={{
        height: 56,
        width: expanded ? 200 : 56,
        background: 'var(--accent)',
        color: '#fff',
        border: 'none',
        borderRadius: 9999,
        boxShadow: 'var(--shadow-3)',
        cursor: 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: expanded ? 'flex-start' : 'center',
        gap: 10,
        padding: expanded ? '0 22px' : 0,
        overflow: 'hidden',
        whiteSpace: 'nowrap',
        fontFamily: 'var(--sans)',
        fontWeight: 600,
        fontSize: 14,
        transition: 'width .25s cubic-bezier(.2,.7,.2,1), padding .25s cubic-bezier(.2,.7,.2,1), background .15s ease, transform .15s ease',
      }}
    >
      <span style={{
        display:'inline-flex', flexShrink:0,
        transition:'transform .3s cubic-bezier(.2,.7,.2,1)',
        transform: open ? 'rotate(45deg)' : 'rotate(0deg)'
      }}>
        <Icon name={open ? 'plus' : 'sparkles'} size={22} strokeWidth={1.6}/>
      </span>
      <span style={{
        opacity: expanded ? 1 : 0,
        width: expanded ? 'auto' : 0,
        overflow: 'hidden',
        transition: 'opacity .15s ease ' + (expanded ? '.1s' : '0s'),
      }}>Open interaction</span>
    </button>
  );
};
