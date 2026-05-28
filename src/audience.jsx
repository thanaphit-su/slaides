/* ============ SLAIDES — audience view (mobile-leaning) ============ */

const Audience = ({ deck, session, user, onExit }) => {
  const [dark, setDark] = useState(false);
  const [liveSlides, setLiveSlides] = useState(() => deck.slides.map(s => ({ ...s, source: 'deck' })));
  const [activeIdx, setActiveIdx] = useState(1); // follow presenter at slide 2
  const [raiseDialog, setRaiseDialog] = useState(false);
  const [submitted, setSubmitted] = useState(null);

  const slides = liveSlides;
  const active = slides[activeIdx];

  // Simulate: ~1.4s after landing, the presenter inserts a live poll slide and the audience follows
  const insertedRef = useRef(false);
  useEffect(() => {
    if (insertedRef.current) return;
    const t = setTimeout(() => {
      insertedRef.current = true;
      const parent = slides[activeIdx];
      const pollSlide = makeInteractionSlide({ kind: 'poll', parentSlide: parent, inverted: !dark });
      setLiveSlides(prev => [
        ...prev.slice(0, activeIdx + 1),
        pollSlide,
        ...prev.slice(activeIdx + 1),
      ]);
      // Auto-advance after a beat
      setTimeout(() => setActiveIdx(i => i + 1), 350);
    }, 1400);
    return () => clearTimeout(t);
  }, []);

  const next = () => setActiveIdx(i => Math.min(slides.length-1, i+1));
  const prev = () => setActiveIdx(i => Math.max(0, i-1));

  // Theme inversion for interaction slide
  const slideEffectiveDark = active?.invertTheme ? !dark : dark;
  const slideThemeClass = slideEffectiveDark ? 'dark' : 'light';

  return (
    <div style={{ minHeight:'100vh', background:'#111417', padding:'24px 0', display:'flex', flexDirection:'column', alignItems:'center' }}>
      <div style={{ textAlign:'center', color:'#bcbfc4', marginBottom:18, fontFamily:'var(--sans)', fontSize:12 }}>
        <Wordmark size={12} style={{ color:'#fff' }}/>
        <div style={{ marginTop:6, fontFamily:'var(--mono)', fontSize:11, opacity:.65 }}>audience view · {user?.anon ? 'anonymous' : user?.name || 'guest'}</div>
      </div>

      {/* Phone frame */}
      <div style={{
        width:380, height:760, background:'var(--paper)', borderRadius:36, border:'10px solid #0b0d10',
        boxShadow:'0 30px 60px rgba(0,0,0,.5)', overflow:'hidden', position:'relative', display:'flex', flexDirection:'column'
      }}>

        {/* Status bar */}
        <div className="light" style={{
          height:32, display:'flex', justifyContent:'space-between', alignItems:'center',
          padding:'0 18px', fontSize:11, fontFamily:'var(--mono)', color:'var(--ink)', flexShrink:0,
          background:'var(--paper)'
        }}>
          <span>9:41</span>
          <span style={{ display:'inline-flex', gap:8, alignItems:'center', fontSize:10 }}>
            <span>●●●</span><span>5G</span>
            <svg width="20" height="10" viewBox="0 0 20 10"><rect x="1" y="2" width="16" height="6" rx="1.5" fill="none" stroke="currentColor"/><rect x="2" y="3" width="14" height="4" rx="1" fill="currentColor"/><rect x="17.5" y="4" width="1.5" height="2" fill="currentColor"/></svg>
          </span>
        </div>

        {/* Top app bar (always light theme — chrome) */}
        <header className="light" style={{
          padding:'8px 18px 12px', borderBottom:'1px solid var(--rule)',
          display:'flex', justifyContent:'space-between', alignItems:'center', flexShrink:0,
          background:'var(--paper)'
        }}>
          <button onClick={onExit} className="btn btn-ghost btn-sm" style={{ padding:'4px 6px' }}>
            <Icon name="x" size={14}/>
          </button>
          <div style={{ textAlign:'center', flex:1 }}>
            <div style={{ fontFamily:'var(--serif)', fontSize:14, letterSpacing:'-0.01em' }}>{deck.title}</div>
            <div style={{ fontFamily:'var(--mono)', fontSize:10, color:'var(--ink-soft)' }}>
              <LiveDot size={6}/> &nbsp;LIVE · {session.audienceCount} in room
            </div>
          </div>
          <div style={{ width:24 }}/>
        </header>

        {/* Slide content — theme switches with the slide */}
        <main className={slideThemeClass} style={{ flex:1, overflowY:'auto', background:'var(--paper)', color:'var(--ink)', transition:'background .25s ease, color .25s ease' }}>
          <div style={{ padding:'20px 22px 24px' }}>
            {active && (active.isInteraction
              ? <AudienceInteractionSlide slide={active} user={user}/>
              : <AudienceRegularSlide slide={active}/>
            )}
          </div>
        </main>

        {/* Bottom action: raise question, prev/next (chrome always light) */}
        <footer className="light" style={{
          borderTop:'1px solid var(--rule)', padding:'10px 14px',
          display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0,
          background:'var(--paper)'
        }}>
          <button onClick={prev} className="btn btn-ghost btn-sm">
            <Icon name="chev_left" size={14}/>
          </button>
          <button onClick={() => setRaiseDialog(true)} className="btn btn-accent" style={{ flex:1, margin:'0 8px', justifyContent:'center' }}>
            <Icon name="hand" size={14}/> Raise a question
          </button>
          <button onClick={next} className="btn btn-ghost btn-sm">
            <Icon name="chev_right" size={14}/>
          </button>
        </footer>

        {/* Raise question modal */}
        {raiseDialog && (
          <div onClick={() => setRaiseDialog(false)} className="fade-in" style={{
            position:'absolute', inset:0, background:'rgba(11,13,16,.6)', display:'flex', alignItems:'flex-end', zIndex:10
          }}>
            <div onClick={e => e.stopPropagation()} className="light slide-up" style={{
              width:'100%', background:'var(--paper)', borderRadius:'16px 16px 0 0', padding:'18px 18px 24px',
              borderTop:'1px solid var(--rule)', color:'var(--ink)'
            }}>
              <div style={{ width:36, height:4, borderRadius:2, background:'var(--rule-strong)', margin:'0 auto 14px' }}/>
              {submitted ? (
                <div className="scale-in" style={{ textAlign:'center', padding:'24px 0' }}>
                  <div style={{
                    width:42, height:42, borderRadius:'50%', background:'var(--accent-soft)', color:'var(--accent)',
                    margin:'0 auto 14px', display:'inline-flex', alignItems:'center', justifyContent:'center'
                  }}>
                    <Icon name="check" size={20}/>
                  </div>
                  <div style={{ fontFamily:'var(--serif)', fontSize:20, marginBottom:6 }}>Question sent.</div>
                  <p style={{ fontFamily:'var(--serif)', fontSize:13, color:'var(--ink-soft)', margin:0 }}>
                    {submitted.anon ? 'Sent anonymously.' : `Sent as ${submitted.name}.`} The instructor will see it in the side rail.
                  </p>
                  <button onClick={() => { setRaiseDialog(false); setSubmitted(null); }} className="btn btn-sm" style={{ marginTop:18 }}>
                    Done
                  </button>
                </div>
              ) : (
                <RaiseQuestionForm user={user} onSubmit={(payload) => setSubmitted(payload)}/>
              )}
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop:18, color:'#bcbfc4', fontFamily:'var(--mono)', fontSize:11, textAlign:'center', maxWidth:380, lineHeight:1.5 }}>
        Your interactions are logged for the instructor's transcript.<br/>
        Anonymous joins are stored as a salted hash — your identity isn't kept on the record.
      </div>
    </div>
  );
};

/* ---------- Regular slide (audience compact) ---------- */
const AudienceRegularSlide = ({ slide }) => (
  <div className="fade-in" key={slide.id}>
    {slide.kicker && <div className="t-kicker" style={{ marginBottom:10, fontSize:10 }}>{slide.kicker}</div>}
    {renderMarkdown(slide.markdown, { widgetSpecs: slide.widgets, slim:true, audienceMode:true })}
  </div>
);

/* ---------- Interaction slide on audience: vote / answer interface ---------- */
const AudienceInteractionSlide = ({ slide, user }) => {
  if (slide.kind === 'poll') return <AudiencePollSlide slide={slide} user={user}/>;
  if (slide.kind === 'question') return <AudienceQuestionSlide slide={slide} user={user}/>;
  return null;
};

const AudiencePollSlide = ({ slide, user }) => {
  const [voted, setVoted] = useState(null);
  // Simulate live total ticking up
  const [results, setResults] = useState(slide.results || [3, 5, 2, 1]);
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
  const total = results.reduce((a,b) => a+b, 0);
  return (
    <div className="fade-in" key={slide.id} style={{ display:'flex', flexDirection:'column', gap:14 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <span style={{
          display:'inline-flex', alignItems:'center', gap:6,
          padding:'3px 9px', borderRadius:'var(--r-pill)',
          background:'var(--accent-soft)', color:'var(--accent)',
          fontFamily:'var(--sans)', fontSize:10, fontWeight:600, letterSpacing:'.06em'
        }}>LIVE POLL</span>
        <span style={{ display:'inline-flex', alignItems:'center', gap:5, fontFamily:'var(--mono)', fontSize:10, color:'var(--ink-soft)' }}>
          <LiveDot size={5}/> {total} votes
        </span>
      </div>
      <div style={{ fontFamily:'var(--serif)', fontSize:22, lineHeight:1.18, letterSpacing:'-0.015em' }}>
        {renderInline(slide.question)}
      </div>
      <p style={{ fontFamily:'var(--serif)', fontSize:13, color:'var(--ink-soft)', margin:0, lineHeight:1.5 }}>
        {slide.lede}
      </p>
      <div style={{ display:'flex', flexDirection:'column', gap:8, marginTop:6 }}>
        {slide.options.map((opt, i) => {
          const pct = total ? Math.round((results[i] / total) * 100) : 0;
          const isVoted = voted === i;
          const showResults = voted != null;
          return (
            <button
              key={i}
              onClick={() => voted == null && setVoted(i)}
              disabled={voted != null && !isVoted}
              style={{
                position:'relative', overflow:'hidden', textAlign:'left',
                border: isVoted ? '2px solid var(--accent)' : '1px solid var(--rule)',
                borderRadius:'var(--r-md)', padding:'12px 14px',
                background: isVoted ? 'var(--accent-soft)' : 'var(--paper)',
                color:'var(--ink)', cursor: voted == null ? 'pointer' : 'default',
                fontFamily:'var(--sans)', fontSize:14,
                display:'flex', alignItems:'center', justifyContent:'space-between', gap:10,
                opacity: voted != null && !isVoted ? .7 : 1,
                transition:'all .2s ease'
              }}
            >
              {showResults && (
                <span style={{
                  position:'absolute', inset:0, background:'var(--accent-soft)',
                  width:`${pct}%`, transition:'width .6s cubic-bezier(.2,.7,.2,1)', pointerEvents:'none'
                }}/>
              )}
              <span style={{ position:'relative', display:'inline-flex', alignItems:'center', gap:10 }}>
                <span style={{ fontFamily:'var(--mono)', fontSize:11, color:'var(--ink-soft)' }}>{String.fromCharCode(65+i)}</span>
                {opt}
              </span>
              {showResults && <span style={{ position:'relative', fontFamily:'var(--mono)', fontSize:11, color:'var(--ink-soft)' }}>{pct}%</span>}
            </button>
          );
        })}
      </div>
      {voted != null && (
        <div className="fade-in" style={{ textAlign:'center', marginTop:6, fontSize:12, color:'var(--meadow)' }}>
          <Icon name="check" size={13}/> Vote in. Updates live.
        </div>
      )}
      <div style={{ marginTop:8, paddingTop:10, borderTop:'1px solid var(--rule-soft)', display:'flex', justifyContent:'space-between' }}>
        <span className="t-mono" style={{ fontSize:9 }}>session-only slide</span>
        <span className="t-mono" style={{ fontSize:9 }}>{user?.anon ? 'anonymous · hashed' : 'attributed'}</span>
      </div>
    </div>
  );
};

const AudienceQuestionSlide = ({ slide, user }) => {
  const [text, setText] = useState('');
  const [submitted, setSubmitted] = useState(false);
  return (
    <div className="fade-in" key={slide.id} style={{ display:'flex', flexDirection:'column', gap:14 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <span style={{
          display:'inline-flex', alignItems:'center', gap:6,
          padding:'3px 9px', borderRadius:'var(--r-pill)',
          background:'var(--accent-soft)', color:'var(--accent)',
          fontFamily:'var(--sans)', fontSize:10, fontWeight:600, letterSpacing:'.06em'
        }}>LIVE QUESTION</span>
      </div>
      <div style={{ fontFamily:'var(--serif)', fontSize:22, lineHeight:1.18, letterSpacing:'-0.015em' }}>
        {renderInline(slide.question)}
      </div>
      <p style={{ fontFamily:'var(--serif)', fontSize:13, color:'var(--ink-soft)', margin:0, lineHeight:1.5 }}>
        {slide.lede}
      </p>
      {submitted ? (
        <div className="scale-in" style={{
          padding:16, borderRadius:'var(--r-md)', background:'var(--accent-soft)',
          color:'var(--accent)', textAlign:'center'
        }}>
          <Icon name="check" size={18}/>
          <div style={{ fontFamily:'var(--serif)', fontSize:16, marginTop:6 }}>Sent — "{text}"</div>
          <div className="t-mono" style={{ fontSize:9, marginTop:6, color:'var(--ink-soft)' }}>
            Your reply appears in the live cloud.
          </div>
        </div>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) setSubmitted(true); }}>
          <input
            autoFocus
            className="input"
            placeholder="one word…"
            value={text}
            onChange={e => setText(e.target.value)}
            style={{ fontFamily:'var(--serif)', fontSize:18, padding:'12px 14px' }}
          />
          <button type="submit" disabled={!text.trim()} className="btn btn-primary" style={{ width:'100%', justifyContent:'center', marginTop:10 }}>
            Send <Icon name="arrow_right" size={14}/>
          </button>
        </form>
      )}
      <div style={{ marginTop:8, paddingTop:10, borderTop:'1px solid var(--rule-soft)', display:'flex', justifyContent:'space-between' }}>
        <span className="t-mono" style={{ fontSize:9 }}>session-only slide</span>
        <span className="t-mono" style={{ fontSize:9 }}>{user?.anon ? 'anonymous · hashed' : 'attributed'}</span>
      </div>
    </div>
  );
};

const RaiseQuestionForm = ({ user, onSubmit }) => {
  const [text, setText] = useState('');
  const [anon, setAnon] = useState(!!user?.anon);
  const submit = (e) => {
    e.preventDefault();
    onSubmit({ text, anon, name: user?.name });
  };
  return (
    <form onSubmit={submit}>
      <div className="t-kicker" style={{ marginBottom:10 }}>Raise a question</div>
      <textarea
        className="input"
        rows={3}
        value={text} onChange={e => setText(e.target.value)}
        placeholder="What's on your mind?"
        required autoFocus
        style={{ marginBottom:12, fontFamily:'var(--sans)', fontSize:14 }}
      />
      <div style={{
        display:'flex', alignItems:'center', justifyContent:'space-between',
        padding:'10px 12px', border:'1px solid var(--rule)', borderRadius:'var(--r-md)',
        background:'var(--paper-2)', marginBottom:14
      }}>
        <div>
          <div style={{ fontSize:13, fontWeight:600 }}>Ask anonymously</div>
          <div style={{ fontSize:11, color:'var(--ink-soft)' }}>{user?.anon ? 'You are joined anonymously.' : 'Hide your name on this question.'}</div>
        </div>
        <Toggle on={anon} onChange={setAnon}/>
      </div>
      <button type="submit" className="btn btn-primary" style={{ width:'100%', justifyContent:'center' }} disabled={!text}>
        Send question <Icon name="arrow_right" size={14}/>
      </button>
    </form>
  );
};

window.Audience = Audience;
