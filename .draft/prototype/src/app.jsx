/* ============ SLAIDES — top-level app & router ============ */

const App = () => {
  const [route, setRoute] = useState('signin'); // signin | workspace | editor | presenter | audience
  const [user, setUser] = useState(null);
  const [decks, setDecks] = useState(SEED.decks);
  const [activeDeckId, setActiveDeckId] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const [widgetsOpen, setWidgetsOpen] = useState(false);

  const activeDeck = decks.find(d => d.id === activeDeckId) || decks[0];

  const goToWorkspace = () => setRoute('workspace');
  const onSignedIn = (u) => {
    setUser(u);
    if (u.kind === 'instructor') setRoute('workspace');
    else { setActiveDeckId(decks[0].id); setRoute('audience'); }
  };
  const onSignOut = () => { setUser(null); setRoute('signin'); setSettingsOpen(false); };

  const onOpenDeck = (id) => { setActiveDeckId(id); setRoute('editor'); };
  const onStartSession = () => setRoute('presenter');

  return (
    <div className={dark ? 'dark' : ''}>
      {route === 'signin' && <Signin onSignedIn={onSignedIn}/>}

      {route === 'workspace' && user && (
        <Workspace
          user={user}
          decks={decks}
          onOpenDeck={onOpenDeck}
          onOpenSettings={() => setSettingsOpen(true)}
          onSignOut={onSignOut}
          onOpenWidgets={() => setWidgetsOpen(true)}
          onNewDeck={() => { onOpenDeck(decks[0].id); }}
        />
      )}

      {route === 'editor' && user && activeDeck && (
        <Editor
          deck={activeDeck}
          onBack={goToWorkspace}
          onStartSession={onStartSession}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      )}

      {route === 'presenter' && user && activeDeck && (
        <Presenter
          deck={activeDeck}
          session={SEED.session}
          onExit={() => setRoute('editor')}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      )}

      {route === 'audience' && activeDeck && (
        <Audience
          deck={activeDeck}
          session={SEED.session}
          user={user}
          onExit={onSignOut}
        />
      )}

      {/* Floating route bar (prototype convenience) */}
      <RouteBar route={route} setRoute={setRoute} user={user} setUser={setUser} setActiveDeckId={setActiveDeckId} decks={decks}/>

      {/* Workspace widget drawer */}
      <Drawer open={widgetsOpen} onClose={() => setWidgetsOpen(false)} width={420}>
        <WidgetCollection
          widgets={SEED.widgets}
          onClose={() => setWidgetsOpen(false)}
        />
      </Drawer>

      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        user={user}
        onSignOut={onSignOut}
        onStartSession={() => { setRoute('presenter'); setSettingsOpen(false); }}
        dark={dark}
        setDark={setDark}
      />
    </div>
  );
};

/* Prototype-only convenience strip to jump between screens without auth */
const RouteBar = ({ route, setRoute, user, setUser, setActiveDeckId, decks }) => {
  const [open, setOpen] = useState(true);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="Open prototype navigator"
        style={{
          position:'fixed', bottom:14, left:14, zIndex:80,
          width:36, height:36, borderRadius:'50%', border:'1px solid var(--rule)',
          background:'var(--paper)', color:'var(--ink-soft)', cursor:'pointer',
          display:'inline-flex', alignItems:'center', justifyContent:'center', boxShadow:'var(--shadow-2)'
        }}
      ><Icon name="grid" size={14}/></button>
    );
  }

  const jump = (r, kind) => {
    if (r === 'audience') {
      setUser({ kind:'audience', name:'You (preview)', email:'you@guest', anon:false });
      setActiveDeckId(decks[0].id);
      setRoute('audience');
      return;
    }
    if (!user) setUser({ kind:'instructor', name:'Field Notes', email:'you@studio.press' });
    if (r === 'editor' || r === 'presenter') setActiveDeckId(decks[0].id);
    setRoute(r);
  };

  return (
    <div style={{
      position:'fixed', bottom:14, left:14, zIndex:80,
      background:'var(--paper)', border:'1px solid var(--rule)', borderRadius:'var(--r-md)',
      boxShadow:'var(--shadow-3)', padding:'8px 10px', display:'flex', alignItems:'center', gap:8,
      fontFamily:'var(--sans)', fontSize:11
    }}>
      <span className="t-mono-up" style={{ fontSize:9 }}>PROTOTYPE NAV</span>
      {[
        ['signin','Sign in'],
        ['workspace','Library'],
        ['editor','Editor'],
        ['presenter','Presenter'],
        ['audience','Audience'],
      ].map(([k,label]) => (
        <button key={k} onClick={() => jump(k)} style={{
          background: route === k ? 'var(--ink)' : 'transparent',
          color: route === k ? 'var(--paper)' : 'var(--ink-soft)',
          border:'1px solid', borderColor: route === k ? 'var(--ink)' : 'var(--rule)',
          padding:'4px 8px', borderRadius:'var(--r-xs)', cursor:'pointer', fontSize:11, fontWeight:500
        }}>{label}</button>
      ))}
      <button onClick={() => setOpen(false)} className="btn btn-ghost btn-sm" style={{ padding:'2px 4px' }}>
        <Icon name="x" size={12}/>
      </button>
    </div>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
