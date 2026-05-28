/* ============ SLAIDES — sign-in / guest-join flow ============ */

const Signin = ({ onSignedIn }) => {
  const [mode, setMode] = useState('instructor'); // 'instructor' | 'guest'
  const [step, setStep] = useState('credentials'); // for instructor: 'credentials'; for guest: 'code' -> 'identity'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [code, setCode] = useState('SLD-2K4F-92');
  const [anon, setAnon] = useState(false);
  const [busy, setBusy] = useState(false);

  const submitInstructor = (e) => {
    e.preventDefault();
    setBusy(true);
    setTimeout(() => onSignedIn({ kind: 'instructor', name: 'Field Notes', email: email || 'you@studio.press' }), 450);
  };

  const submitGuestCode = (e) => {
    e.preventDefault();
    setStep('identity');
  };
  const submitGuestIdentity = (e) => {
    e.preventDefault();
    setBusy(true);
    setTimeout(() => onSignedIn({ kind: 'audience', name: anon ? null : name, email, anon, code }), 450);
  };

  return (
    <div style={{ minHeight:'100vh', display:'grid', gridTemplateColumns:'1fr 1fr', background:'var(--paper)' }}>
      {/* Left — editorial side */}
      <div style={{ padding:'56px 64px', display:'flex', flexDirection:'column', justifyContent:'space-between', borderRight:'1px solid var(--rule)' }}>
        <Wordmark size={18}/>
        <div className="slide-up">
          <div className="t-kicker" style={{ marginBottom:18 }}>A press for talks worth keeping.</div>
          <div className="t-display" style={{ fontSize:64, marginBottom:24 }}>
            Write a deck.<br/>Run a <em>conversation</em>.<br/>Keep the receipts.
          </div>
          <div className="rule" style={{ marginBottom:16 }}/>
          <p className="t-lede" style={{ maxWidth:'52ch' }}>
            SLAIDES is a presentation tool built for the back‑and‑forth: live polls, open questions, on‑the‑fly LLM
            assistants, and a transcript of every interaction your audience leaves behind.
          </p>
        </div>
        <div style={{ display:'flex', gap:28, color:'var(--ink-soft)' }}>
          <span className="t-meta"><b style={{ color:'var(--ink)' }}>v 0.1</b> · prototype</span>
          <span className="t-meta">Fraunces / Newsreader · Inter</span>
        </div>
      </div>

      {/* Right — auth */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'center', padding:'56px 64px', background:'var(--paper-2)' }}>
        <div style={{ width:'100%', maxWidth:380 }}>
          {/* mode switcher */}
          <div style={{ display:'flex', gap:0, border:'1px solid var(--rule)', borderRadius:'var(--r-md)', padding:3, background:'var(--paper)', marginBottom:32 }}>
            {['instructor','guest'].map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); setStep(m === 'guest' ? 'code' : 'credentials'); }}
                style={{
                  flex:1, padding:'8px 12px', border:'none', background: mode === m ? 'var(--ink)' : 'transparent',
                  color: mode === m ? 'var(--paper)' : 'var(--ink-soft)', borderRadius:6,
                  fontFamily:'var(--sans)', fontSize:13, fontWeight:600, cursor:'pointer', transition:'all .15s ease'
                }}
              >
                {m === 'instructor' ? 'Sign in' : 'Join a session'}
              </button>
            ))}
          </div>

          {mode === 'instructor' && (
            <form className="fade-in" onSubmit={submitInstructor}>
              <div style={{ marginBottom:6 }} className="t-kicker">Instructor</div>
              <div className="t-h3" style={{ marginBottom:24 }}>Welcome back.</div>

              <div style={{ marginBottom:14 }}>
                <label className="field-label">Email</label>
                <input className="input" type="email" placeholder="you@studio.press" value={email} onChange={e => setEmail(e.target.value)} required autoFocus/>
              </div>
              <div style={{ marginBottom:18 }}>
                <label className="field-label">Password</label>
                <input className="input" type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required/>
              </div>

              <button type="submit" disabled={busy} className="btn btn-primary" style={{ width:'100%', justifyContent:'center', padding:'12px' }}>
                {busy ? 'Signing in…' : 'Sign in'} <Icon name="arrow_right" size={16}/>
              </button>

              <div style={{ textAlign:'center', marginTop:16, fontSize:12, color:'var(--ink-soft)' }}>
                New here? <a href="#" style={{ color:'var(--accent)', textDecoration:'none', fontWeight:600 }}>Request access</a>
              </div>
            </form>
          )}

          {mode === 'guest' && step === 'code' && (
            <form className="fade-in" onSubmit={submitGuestCode}>
              <div style={{ marginBottom:6 }} className="t-kicker">Audience</div>
              <div className="t-h3" style={{ marginBottom:8 }}>Join a session.</div>
              <p className="t-meta" style={{ marginBottom:24 }}>Enter the code your instructor shared, or paste the link.</p>

              <div style={{ marginBottom:18 }}>
                <label className="field-label">Session code</label>
                <input className="input" placeholder="SLD-XXXX-XX" value={code} onChange={e => setCode(e.target.value)} required autoFocus
                  style={{ fontFamily:'var(--mono)', letterSpacing:'.08em', textAlign:'center', fontSize:18 }}/>
              </div>

              <button type="submit" className="btn btn-primary" style={{ width:'100%', justifyContent:'center', padding:'12px' }}>
                Continue <Icon name="arrow_right" size={16}/>
              </button>
            </form>
          )}

          {mode === 'guest' && step === 'identity' && (
            <form className="fade-in" onSubmit={submitGuestIdentity}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:6 }}>
                <span className="t-kicker">Audience</span>
                <button type="button" onClick={() => setStep('code')} className="btn btn-ghost btn-sm">
                  <Icon name="arrow_left" size={14}/> Back
                </button>
              </div>
              <div className="t-h3" style={{ marginBottom:8 }}>Tell us who's joining.</div>
              <p className="t-meta" style={{ marginBottom:24 }}>The instructor will see your name. Anonymous mode hides it everywhere but keeps your seat.</p>

              <div style={{ marginBottom:14 }}>
                <label className="field-label">Email</label>
                <input className="input" type="email" placeholder="you@somewhere.edu" value={email} onChange={e => setEmail(e.target.value)} required autoFocus/>
                <div style={{ marginTop:6, fontSize:11, color:'var(--ink-mute)' }}>Used for the transcript — never shown to other attendees.</div>
              </div>
              <div style={{ marginBottom:14 }}>
                <label className="field-label">Display name</label>
                <input className="input" placeholder={anon ? 'Hidden — joining anonymously' : 'e.g. Sara K.'} value={name} onChange={e => setName(e.target.value)} disabled={anon} required={!anon}/>
              </div>

              <div style={{
                display:'flex', alignItems:'center', justifyContent:'space-between',
                padding:'10px 12px', border:'1px solid var(--rule)', borderRadius:'var(--r-md)',
                background:'var(--paper)', marginBottom:18
              }}>
                <div>
                  <div style={{ fontSize:13, fontWeight:600 }}>Join anonymously</div>
                  <div style={{ fontSize:11, color:'var(--ink-soft)', marginTop:2 }}>Your name and email are stored as a salted hash.</div>
                </div>
                <Toggle on={anon} onChange={setAnon}/>
              </div>

              <button type="submit" disabled={busy} className="btn btn-primary" style={{ width:'100%', justifyContent:'center', padding:'12px' }}>
                {busy ? 'Joining…' : 'Join session'} <Icon name="arrow_right" size={16}/>
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

window.Signin = Signin;
