/* ============ SLAIDES — workspace (deck library) ============ */

const Workspace = ({ user, decks, onOpenDeck, onOpenSettings, onSignOut, onOpenWidgets, onNewDeck }) => {
  const [query, setQuery] = useState('');
  const [view, setView] = useState('grid'); // 'grid' | 'list'
  const [tab, setTab] = useState('decks'); // 'decks' | 'widgets' | 'sessions'

  const filtered = decks.filter(d => d.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <div style={{ minHeight:'100vh', background:'var(--paper)', display:'flex', flexDirection:'column' }}>
      {/* Top nav */}
      <header style={{
        position:'sticky', top:0, zIndex:10, background:'var(--paper)',
        borderBottom:'1px solid var(--rule)',
        padding:'14px 32px', display:'flex', alignItems:'center', justifyContent:'space-between'
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:24 }}>
          <Wordmark size={16}/>
          <nav style={{ display:'flex', gap:4 }}>
            {[
              ['decks','Decks'],
              ['widgets','Widgets'],
              ['sessions','Sessions'],
            ].map(([k,label]) => (
              <button key={k} onClick={() => setTab(k)} style={{
                background: tab === k ? 'var(--paper-2)' : 'transparent', border:'none',
                color: tab === k ? 'var(--ink)' : 'var(--ink-soft)', fontFamily:'var(--sans)',
                fontWeight: tab === k ? 600 : 500, fontSize:13,
                padding:'6px 12px', borderRadius:'var(--r-sm)', cursor:'pointer'
              }}>{label}</button>
            ))}
          </nav>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <div style={{ position:'relative' }}>
            <span style={{ position:'absolute', left:10, top:'50%', transform:'translateY(-50%)', color:'var(--ink-mute)' }}>
              <Icon name="search" size={14}/>
            </span>
            <input
              className="input"
              placeholder="Search…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{ width:260, paddingLeft:32, paddingTop:7, paddingBottom:7, fontSize:13, background:'var(--paper-2)', border:'1px solid var(--rule)' }}
            />
          </div>
          <button className="btn btn-ghost" onClick={onOpenSettings} title="Settings">
            <Icon name="gear" size={16}/>
          </button>
          <button onClick={onSignOut} className="btn btn-ghost" title={user.name || 'You'} style={{ padding:'4px 8px' }}>
            <span style={{
              width:28, height:28, borderRadius:'50%', background:'var(--ink)', color:'var(--paper)',
              display:'inline-flex', alignItems:'center', justifyContent:'center',
              fontFamily:'var(--serif)', fontSize:13, fontWeight:500
            }}>
              {(user.name || 'A').slice(0,1)}
            </span>
          </button>
        </div>
      </header>

      {/* Hero / library header */}
      <section style={{ padding:'56px 32px 24px', maxWidth:1240, width:'100%', margin:'0 auto' }}>
        <div className="t-kicker" style={{ marginBottom:14 }}>Library · {user.name || 'You'}</div>
        <div className="t-h1" style={{ marginBottom:14 }}>
          The decks you've been <em>writing</em>.
        </div>
        <p className="t-lede" style={{ maxWidth:'62ch', marginBottom:32 }}>
          Open one to keep editing. Start a session to take it live. Import a deck or a widget from another project at any time.
        </p>

        {/* Action row */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:24 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <button className="btn btn-primary" onClick={onNewDeck}>
              <Icon name="plus" size={14}/> New deck
            </button>
            <button className="btn">
              <Icon name="upload" size={14}/> Import…
            </button>
            <button className="btn" onClick={onOpenWidgets}>
              <Icon name="widget" size={14}/> Widget collection
            </button>
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <span className="t-meta">{filtered.length} {filtered.length === 1 ? 'deck' : 'decks'}</span>
            <div style={{ display:'inline-flex', border:'1px solid var(--rule)', borderRadius:'var(--r-sm)', overflow:'hidden' }}>
              {['grid','list'].map(v => (
                <button key={v} onClick={() => setView(v)} style={{
                  background: view === v ? 'var(--paper-2)' : 'var(--paper)',
                  border:'none', color: view === v ? 'var(--ink)' : 'var(--ink-mute)', padding:'6px 8px', cursor:'pointer'
                }}>
                  <Icon name={v} size={14}/>
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Deck grid */}
      <section style={{ padding:'0 32px 96px', maxWidth:1240, width:'100%', margin:'0 auto' }}>
        {view === 'grid' ? (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px, 1fr))', gap:24 }}>
            {filtered.map(d => (
              <DeckCard key={d.id} deck={d} onClick={() => onOpenDeck(d.id)}/>
            ))}
            <NewDeckCard onClick={onNewDeck}/>
          </div>
        ) : (
          <DeckList decks={filtered} onOpen={onOpenDeck}/>
        )}
      </section>

      {/* Footer */}
      <footer style={{ borderTop:'1px solid var(--rule)', padding:'24px 32px', maxWidth:1240, width:'100%', margin:'0 auto' }}>
        <div style={{ display:'flex', justifyContent:'space-between', color:'var(--ink-soft)' }}>
          <span className="t-meta">© SLAIDES · v 0.1 prototype</span>
          <span className="t-meta">⌘ K — quick search</span>
        </div>
      </footer>
    </div>
  );
};

/* ---------- Deck card ---------- */
const DeckCard = ({ deck, onClick }) => (
  <article
    onClick={onClick}
    className="scale-in"
    style={{
      background:'var(--paper)', border:'1px solid var(--rule)', borderRadius:'var(--r-lg)',
      overflow:'hidden', cursor:'pointer', transition:'border-color .15s ease, transform .15s ease, box-shadow .15s ease',
      display:'flex', flexDirection:'column'
    }}
    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--ink)'; e.currentTarget.style.boxShadow = 'var(--shadow-2)'; }}
    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--rule)'; e.currentTarget.style.boxShadow = 'none'; }}
  >
    {/* Cover */}
    <div style={{ aspectRatio:'320 / 200', borderBottom:'1px solid var(--rule)', background:'var(--paper-2)' }}>
      <DeckCover variant={deck.cover}/>
    </div>
    {/* Meta */}
    <div style={{ padding:'16px 18px', display:'flex', flexDirection:'column', gap:6, flex:1 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <h3 style={{ fontFamily:'var(--serif)', fontSize:20, fontWeight:500, letterSpacing:'-0.015em', margin:0, lineHeight:1.2 }}>
          {deck.title}
        </h3>
        <span className="t-meta" style={{ flexShrink:0, marginLeft:8 }}>{deck.updatedAt}</span>
      </div>
      <p style={{ fontFamily:'var(--serif)', fontSize:14, color:'var(--ink-soft)', fontWeight:400, margin:0, lineHeight:1.5 }}>
        {deck.subtitle}
      </p>
      <div style={{ marginTop:'auto', paddingTop:12, display:'flex', alignItems:'center', gap:14 }}>
        <span style={{ display:'inline-flex', alignItems:'center', gap:5, color:'var(--ink-soft)', fontSize:12 }}>
          <Icon name="deck" size={13}/> {deck.slideCount} slides
        </span>
        <span style={{ display:'inline-flex', alignItems:'center', gap:5, color:'var(--ink-soft)', fontSize:12 }}>
          <Icon name="users" size={13}/> {deck.audience}
        </span>
        <span style={{ marginLeft:'auto' }} className="t-meta">
          {deck.sessions} {deck.sessions === 1 ? 'session' : 'sessions'}
        </span>
      </div>
    </div>
  </article>
);

const NewDeckCard = ({ onClick }) => (
  <button onClick={onClick} style={{
    background:'transparent', border:'1.5px dashed var(--rule-strong)', borderRadius:'var(--r-lg)',
    minHeight:280, color:'var(--ink-soft)', cursor:'pointer', fontFamily:'var(--sans)', display:'flex',
    flexDirection:'column', alignItems:'center', justifyContent:'center', gap:14, transition:'all .15s ease'
  }}
    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)'; }}
    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--rule-strong)'; e.currentTarget.style.color = 'var(--ink-soft)'; }}
  >
    <Icon name="plus" size={22}/>
    <span style={{ fontWeight:600, fontSize:14 }}>New deck</span>
    <span style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:13 }}>or drop a .slaides file to import</span>
  </button>
);

/* ---------- Deck list view ---------- */
const DeckList = ({ decks, onOpen }) => (
  <div style={{ border:'1px solid var(--rule)', borderRadius:'var(--r-lg)', overflow:'hidden', background:'var(--paper)' }}>
    <div style={{
      display:'grid', gridTemplateColumns:'2.2fr 1fr 100px 100px 80px',
      gap:14, padding:'12px 18px', borderBottom:'1px solid var(--rule)', background:'var(--paper-2)',
      fontFamily:'var(--sans)', fontSize:11, fontWeight:600, color:'var(--ink-soft)', textTransform:'uppercase', letterSpacing:'.1em'
    }}>
      <span>Title</span><span>Last edited</span><span style={{ textAlign:'right' }}>Slides</span><span style={{ textAlign:'right' }}>Sessions</span><span></span>
    </div>
    {decks.map((d,i) => (
      <div
        key={d.id}
        onClick={() => onOpen(d.id)}
        style={{
          display:'grid', gridTemplateColumns:'2.2fr 1fr 100px 100px 80px', gap:14,
          padding:'14px 18px', borderBottom: i === decks.length-1 ? 'none' : '1px solid var(--rule-soft)',
          alignItems:'center', cursor:'pointer', transition:'background .12s'
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--paper-2)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        <div>
          <div style={{ fontFamily:'var(--serif)', fontSize:18, letterSpacing:'-0.01em' }}>{d.title}</div>
          <div style={{ fontSize:12, color:'var(--ink-soft)', marginTop:2 }}>{d.subtitle}</div>
        </div>
        <span className="t-meta">{d.updatedAt}</span>
        <span style={{ textAlign:'right', fontSize:13, color:'var(--ink)' }}>{d.slideCount}</span>
        <span style={{ textAlign:'right', fontSize:13, color:'var(--ink)' }}>{d.sessions}</span>
        <span style={{ textAlign:'right' }}>
          <Icon name="arrow_right" size={16}/>
        </span>
      </div>
    ))}
  </div>
);

window.Workspace = Workspace;
