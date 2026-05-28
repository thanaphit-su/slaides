/* ============ SLAIDES — widgets (renderer + collection) ============ */

/* In production:
   - Each widget is HTML+JS+CSS stored as a record
   - Rendered inside <iframe sandbox="allow-scripts" srcdoc=...> with a postMessage bridge
   - The bridge exposes: slaides.emit(eventName, payload), slaides.onAudience(cb), slaides.setState(k,v)
   For the prototype, we render with React directly to keep the demo snappy.
*/

/* ---------- Function plotter (sample widget) ---------- */
const FunctionPlotterWidget = ({ live = false }) => {
  const [expr, setExpr] = useState('2x + 1');
  const w = 560,h = 280,pad = 30;
  const xs = useMemo(() => Array.from({ length: 80 }, (_, i) => -6 + 12 / 79 * i), []);
  const fn = useMemo(() => {
    // Tiny expression evaluator. Replace x with value, ^ with **.
    const safe = expr.replace(/\^/g, '**').replace(/[^\dxX+\-*/().\s*]/g, '');
    return (x) => {
      try {
        // eslint-disable-next-line no-new-func
        return new Function('x', `return (${safe || '0'});`)(x);
      } catch {return NaN;}
    };
  }, [expr]);
  const points = xs.map((x) => [x, fn(x)]).filter((p) => Number.isFinite(p[1]));

  const xToPx = (x) => pad + (x + 6) / 12 * (w - pad * 2);
  const yToPx = (y) => h - pad - (Math.max(-6, Math.min(6, y)) + 6) / 12 * (h - pad * 2);

  const path = points.length ? `M ${points.map((p) => `${xToPx(p[0])},${yToPx(p[1])}`).join(' L ')}` : '';

  return (
    <div style={{
      border: '1px solid var(--rule)', borderRadius: 'var(--r-lg)', padding: '18px 20px', background: 'var(--paper)',
      display: 'flex', flexDirection: 'column', gap: 14, fontFamily: 'var(--sans)'
    }} data-comment-anchor="393e801939-div-33-5">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="badge badge-accent">FUNCTION PLOTTER</span>
          <span className="t-meta">y = f(x), see the curve</span>
        </div>
        {live && <span className="badge badge-live"><LiveDot color="#fff" size={6} /> LIVE</span>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: 'var(--mono)', fontSize: 14 }}>
        <span style={{ color: 'var(--ink-soft)' }}>y =</span>
        <input
          value={expr} onChange={(e) => setExpr(e.target.value)}
          className="input"
          style={{ fontFamily: 'var(--mono)', fontSize: 14, padding: '6px 10px', maxWidth: 240 }} />
        
        <span className="t-meta">try: x^2, sin(x)*2, 0.5*x - 1</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
        {/* axes */}
        <line x1={pad} y1={h / 2} x2={w - pad} y2={h / 2} stroke="var(--rule-strong)" strokeWidth="1" />
        <line x1={w / 2} y1={pad} x2={w / 2} y2={h - pad} stroke="var(--rule-strong)" strokeWidth="1" />
        {/* ticks */}
        {Array.from({ length: 13 }, (_, i) => i - 6).map((t) =>
        <g key={t}>
            <line x1={xToPx(t)} y1={h / 2 - 3} x2={xToPx(t)} y2={h / 2 + 3} stroke="var(--rule-strong)" strokeWidth="1" />
            <line x1={w / 2 - 3} y1={yToPx(t)} x2={w / 2 + 3} y2={yToPx(t)} stroke="var(--rule-strong)" strokeWidth="1" />
          </g>
        )}
        <path d={path} fill="none" stroke="var(--amber)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <text x={w - pad} y={h / 2 - 6} textAnchor="end" fontFamily="var(--mono)" fontSize="10" fill="var(--ink-mute)">x</text>
        <text x={w / 2 + 6} y={pad + 10} fontFamily="var(--mono)" fontSize="10" fill="var(--ink-mute)">y</text>
      </svg>
    </div>);

};

/* ---------- Poll widget ---------- */
const PollWidget = ({ question, options, voted = null, results, onVote, live, slim = false }) => {
  const total = results ? results.reduce((a, b) => a + b, 0) : 0;
  return (
    <div style={{
      border: '1px solid var(--rule)', borderRadius: 'var(--r-lg)', padding: slim ? 14 : '18px 20px', background: 'var(--paper)',
      fontFamily: 'var(--sans)', display: 'flex', flexDirection: 'column', gap: 12
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span className="badge badge-accent">POLL</span>
        {live && <span className="badge badge-live"><LiveDot color="#fff" size={6} /> LIVE · {total} votes</span>}
      </div>
      <div style={{ fontFamily: 'var(--serif)', fontSize: slim ? 18 : 22, lineHeight: 1.2, letterSpacing: '-0.015em' }}>{question}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {options.map((opt, i) => {
          const pct = total ? Math.round(results[i] / total * 100) : 0;
          const isVoted = voted === i;
          return (
            <button
              key={i}
              onClick={() => onVote && onVote(i)}
              style={{
                position: 'relative', overflow: 'hidden', textAlign: 'left',
                border: isVoted ? '2px solid var(--accent)' : '1px solid var(--rule)',
                borderRadius: 'var(--r-md)', padding: '10px 12px',
                background: isVoted ? 'var(--accent-soft)' : 'var(--paper)',
                color: 'var(--ink)', cursor: onVote ? 'pointer' : 'default', fontFamily: 'var(--sans)', fontSize: 14,
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12
              }}>
              
              {results &&
              <span style={{
                position: 'absolute', inset: 0, background: 'var(--accent-soft)',
                width: `${pct}%`, transition: 'width .6s ease', pointerEvents: 'none'
              }} />
              }
              <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-soft)' }}>{String.fromCharCode(65 + i)}</span>
                {opt}
              </span>
              {results && <span style={{ position: 'relative', fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-soft)' }}>{pct}%</span>}
            </button>);

        })}
      </div>
    </div>);

};

/* ---------- Word cloud (mini) ---------- */
const WordcloudWidget = ({ words }) =>
<div style={{ border: '1px solid var(--rule)', borderRadius: 'var(--r-lg)', padding: 18, background: 'var(--paper)' }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
      <span className="badge badge-accent">WORD CLOUD</span>
      <span className="badge badge-live"><LiveDot color="#fff" size={6} /> LIVE</span>
    </div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 14px', alignItems: 'baseline', justifyContent: 'center', padding: '8px 0' }}>
      {words.map(([w, weight], i) =>
    <span key={i} style={{ fontFamily: 'var(--serif)', fontSize: 14 + weight * 14, color: i % 2 ? 'var(--accent)' : 'var(--ink)', fontStyle: i % 3 ? 'normal' : 'italic' }}>
          {w}
        </span>
    )}
    </div>
  </div>;


/* ---------- Generic widget renderer ---------- */
const Widget = ({ spec, audienceMode = false, live = false }) => {
  if (!spec) return null;
  switch (spec.kind) {
    case 'function-plotter':
      return <FunctionPlotterWidget live={live} />;
    case 'poll':{
        const [voted, setVoted] = useState(null);
        const baseResults = [4, 18, 7, 3];
        const results = voted == null ? baseResults : baseResults.map((v, i) => i === voted ? v + 1 : v);
        return (
          <PollWidget
            question="Which line is the 'best fit' through this cloud?"
            options={['The flattest one', 'The one with smallest total distance', 'The one passing through the most points', 'The one with smallest squared error']}
            voted={voted}
            results={voted != null || !audienceMode ? results : null}
            onVote={audienceMode ? (i) => setVoted(i) : null}
            live={live} />);


      }
    case 'wordcloud':
      return <WordcloudWidget words={[['function', 1.0], ['rule', 0.7], ['mapping', 0.6], ['math', 0.5], ['input', 0.8], ['output', 0.7], ['line', 0.9], ['box', 0.4], ['transform', 0.6]]} />;
    default:
      return (
        <div style={{ border: '1px dashed var(--rule-strong)', borderRadius: 'var(--r-lg)', padding: 18, color: 'var(--ink-soft)', textAlign: 'center' }}>
          <Icon name="widget" size={20} />
          <div style={{ marginTop: 6, fontSize: 13 }}>Widget · {spec.kind}</div>
        </div>);

  }
};

/* ---------- Widget collection panel ---------- */
const WidgetCollection = ({ widgets, onInsert, onClose, mode = 'browse' }) => {
  const [tab, setTab] = useState('library'); // 'library' | 'generate'
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState(null);

  const generate = () => {
    setGenerating(true);
    setGenerated(null);
    setTimeout(() => {
      setGenerated({
        id: 'w-gen-' + Math.random().toString(36).slice(2, 7),
        name: prompt.slice(0, 40) || 'New interactive',
        kind: 'custom',
        tags: ['ai-generated'],
        description: 'A custom HTML/JS widget generated from your prompt. Editable as code.',
        updatedAt: 'just now'
      });
      setGenerating(false);
    }, 1300);
  };

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <header style={{
        padding: '14px 20px', borderBottom: '1px solid var(--rule)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between'
      }}>
        <div>
          <div className="t-kicker" style={{ marginBottom: 4 }}>Widget collection</div>
          <div style={{ fontFamily: 'var(--serif)', fontSize: 20 }}>Add a moment of interaction.</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onClose}><Icon name="x" size={16} /></button>
      </header>

      <div style={{ display: 'flex', padding: '12px 20px 0', gap: 6 }}>
        {['library', 'generate'].map((t) =>
        <button key={t} onClick={() => setTab(t)} style={{
          background: tab === t ? 'var(--paper-2)' : 'transparent', border: 'none',
          color: tab === t ? 'var(--ink)' : 'var(--ink-soft)',
          padding: '6px 12px', borderRadius: 'var(--r-sm)', fontWeight: 600, fontSize: 13, cursor: 'pointer'
        }}>{t === 'library' ? 'My library' : 'Generate with AI'}</button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 20px' }}>
        {tab === 'library' &&
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {widgets.map((w) =>
          <article key={w.id} style={{
            border: '1px solid var(--rule)', borderRadius: 'var(--r-md)', padding: '12px 14px', background: 'var(--paper)',
            display: 'flex', alignItems: 'flex-start', gap: 12, cursor: onInsert ? 'pointer' : 'default'
          }}
          onMouseEnter={(e) => {e.currentTarget.style.borderColor = 'var(--ink)';}}
          onMouseLeave={(e) => {e.currentTarget.style.borderColor = 'var(--rule)';}}
          onClick={() => onInsert && onInsert(w)}>
            
                <span style={{
              width: 36, height: 36, borderRadius: 'var(--r-sm)', background: 'var(--paper-2)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)'
            }}>
                  <Icon name={{ poll: 'poll', question: 'question', plotter: 'sparkles', wordcloud: 'palette', rank: 'list', slider: 'sparkles' }[w.kind] || 'widget'} size={18} />
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: 14, fontWeight: 600 }}>{w.name}</div>
                    <div className="t-mono" style={{ flexShrink: 0 }}>{w.updatedAt}</div>
                  </div>
                  <p style={{ fontFamily: 'var(--serif)', fontSize: 13, color: 'var(--ink-soft)', margin: '4px 0 6px', lineHeight: 1.5 }}>{w.description}</p>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {w.tags.map((t) => <span key={t} className="t-mono-up" style={{ fontSize: 9, padding: '2px 6px', border: '1px solid var(--rule)', borderRadius: 'var(--r-xs)' }}>{t}</span>)}
                  </div>
                </div>
              </article>
          )}
          </div>
        }

        {tab === 'generate' &&
        <div className="fade-in">
            <label className="field-label">Describe the interaction</label>
            <textarea
            value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3}
            className="input"
            placeholder='e.g. "A slider from 0 to 100 labelled Confidence; show the median to the presenter."'
            style={{ fontFamily: 'var(--sans)', fontSize: 13, lineHeight: 1.5, resize: 'vertical' }} />
          
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button className="btn btn-primary" disabled={!prompt || generating} onClick={generate}>
                <Icon name="sparkles" size={14} /> {generating ? 'Drafting…' : 'Generate widget'}
              </button>
              <button className="btn">
                <Icon name="upload" size={14} /> Import .swidget
              </button>
            </div>

            <p className="t-meta" style={{ marginTop: 14 }}>
              Widgets render in a sandboxed iframe with a postMessage bridge — they can read audience input and emit events,
              but cannot reach your deck. You can hand-edit the HTML/JS at any time.
            </p>

            {generating &&
          <div style={{ marginTop: 24, padding: 20, border: '1px dashed var(--accent)', borderRadius: 'var(--r-md)', background: 'var(--accent-soft)' }}>
                <div className="t-kicker" style={{ marginBottom: 6 }}>Drafting</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '92%' }} />
                  <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '80%' }} />
                  <span className="pulse" style={{ height: 8, borderRadius: 4, background: 'var(--accent-tint)', width: '65%' }} />
                </div>
              </div>
          }

            {generated &&
          <div className="scale-in" style={{ marginTop: 24, padding: 14, border: '1px solid var(--rule)', borderRadius: 'var(--r-md)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div className="t-kicker">Draft ready</div>
                  <span className="t-mono">{generated.updatedAt}</span>
                </div>
                <div style={{ fontFamily: 'var(--serif)', fontSize: 18, marginBottom: 6 }}>{generated.name}</div>
                <p style={{ fontFamily: 'var(--serif)', fontSize: 13, color: 'var(--ink-soft)', marginBottom: 12 }}>{generated.description}</p>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary btn-sm" onClick={() => onInsert(generated)}>
                    <Icon name="plus" size={13} /> Insert into slide
                  </button>
                  <button className="btn btn-sm">
                    <Icon name="code" size={13} /> Edit code
                  </button>
                  <button className="btn btn-sm">
                    <Icon name="book" size={13} /> Save to library
                  </button>
                </div>
              </div>
          }
          </div>
        }
      </div>
    </div>);

};

window.Widget = Widget;
window.WidgetCollection = WidgetCollection;
window.PollWidget = PollWidget;
window.FunctionPlotterWidget = FunctionPlotterWidget;