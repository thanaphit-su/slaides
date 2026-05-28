/* ============ SLAIDES — settings drawer ============ */

const SettingsDrawer = ({ open, onClose, user, onSignOut, onStartSession, dark, setDark }) => {
  const [section, setSection] = useState('session');
  const [llmBase, setLlmBase] = useState('https://api.openai.com/v1');
  const [llmKey, setLlmKey] = useState('sk-•••••••••••••••2c14');
  const [llmKeyVisible, setLlmKeyVisible] = useState(false);

  // Model list — each entry: { id, provider }
  const [llmModels, setLlmModels] = useState([
    { id: 'gpt-4.1-mini',       provider: 'OpenAI' },
    { id: 'gpt-4.1',            provider: 'OpenAI' },
    { id: 'gpt-4o',             provider: 'OpenAI' },
    { id: 'claude-sonnet-4',    provider: 'Anthropic · proxy' },
    { id: 'llama-3.1-8b',       provider: 'Local · Ollama' },
  ]);
  const [addingModel, setAddingModel] = useState(false);
  const [draftModel, setDraftModel] = useState({ id: '', provider: '' });

  // Per-capability assignment — null means disabled
  const [caps, setCaps] = useState({
    inline_write:     'gpt-4.1-mini',
    interpret:        'gpt-4.1-mini',
    widget_generate:  'gpt-4.1',
    summarise:        'gpt-4.1-mini',
  });

  // Advanced config per model (or global). Default everything blank.
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedModelId, setAdvancedModelId] = useState(llmModels[0]?.id || null);
  const [advanced, setAdvanced] = useState({
    // Keyed by model id. Each entry has the same shape, all blank by default.
  });
  const adv = advanced[advancedModelId] || {};
  const setAdv = (patch) => setAdvanced(a => ({ ...a, [advancedModelId]: { ...(a[advancedModelId] || {}), ...patch } }));

  const commitNewModel = () => {
    const id = draftModel.id.trim();
    if (!id) { setAddingModel(false); setDraftModel({ id: '', provider: '' }); return; }
    if (!llmModels.some(m => m.id === id)) {
      setLlmModels(prev => [...prev, { id, provider: draftModel.provider.trim() || 'Custom' }]);
    }
    setDraftModel({ id: '', provider: '' });
    setAddingModel(false);
  };
  const removeModel = (id) => {
    setLlmModels(prev => prev.filter(m => m.id !== id));
    setCaps(c => Object.fromEntries(Object.entries(c).map(([k,v]) => [k, v === id ? null : v])));
    if (advancedModelId === id) setAdvancedModelId(llmModels.find(m => m.id !== id)?.id || null);
  };

  const capRows = [
    { key:'inline_write',    label:'Inline content writing',     desc:'Continue or rewrite paragraphs from a prompt.' },
    { key:'interpret',       label:'Interpret on selected text', desc:'Right-click a phrase to explain or translate.' },
    { key:'widget_generate', label:'Generate widgets (HTML/JS)', desc:'Draft a working widget from a prompt.' },
    { key:'summarise',       label:'Summarise session transcript', desc:'After a session ends, distill the room\'s contributions.' },
  ];

  return (
    <Drawer open={open} onClose={onClose} width={460}>
      <header style={{ padding: '18px 22px 14px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div className="t-kicker" style={{ marginBottom: 4 }}>Settings</div>
          <div style={{ fontFamily: 'var(--serif)', fontSize: 22, letterSpacing: '-0.015em', color:'var(--ink)' }}>How SLAIDES behaves.</div>
        </div>
        <button onClick={onClose} className="btn btn-ghost btn-sm"><Icon name="x" size={14} /></button>
      </header>

      <nav style={{ display: 'flex', gap: 4, padding: '10px 14px 0' }}>
        {[['session','Session'],['llm','LLM'],['display','Display'],['account','Account']].map(([k, label]) =>
          <button key={k} onClick={() => setSection(k)} style={{
            border: 'none', background: section === k ? 'var(--paper-2)' : 'transparent',
            color: section === k ? 'var(--ink)' : 'var(--ink-soft)',
            padding: '6px 10px', borderRadius: 'var(--r-sm)', cursor: 'pointer', fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 12
          }}>{label}</button>
        )}
      </nav>

      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 22px 24px' }}>

        {section === 'session' && (
          <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <Block title="Publish & start a session" desc="Take this deck live. Audience can join by code or share link.">
              <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={() => { onClose(); onStartSession(); }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--live)' }} />
                Start new session
              </button>
            </Block>
            <Block title="Recordings & transcripts" desc="Sessions are saved with a full interaction log. Anonymous attendees are stored as salted hashes.">
              <label style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', color:'var(--ink)' }}>Save transcripts <Toggle on={true} /></label>
              <label style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', color:'var(--ink)' }}>Allow anonymous join <Toggle on={true} /></label>
              <label style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', color:'var(--ink)' }}>Show audience count to room <Toggle on={false} /></label>
            </Block>
            <Block title="Deck access">
              <Field label="Sharable link">
                <input className="input" readOnly value="https://slaides.app/d/fieldnotes" style={{ fontFamily: 'var(--mono)', fontSize: 12 }} />
              </Field>
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <button className="btn btn-sm"><Icon name="copy" size={13} /> Copy link</button>
                <button className="btn btn-sm"><Icon name="download" size={13} /> Export .slaides</button>
              </div>
            </Block>
          </div>
        )}

        {section === 'llm' && (
          <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <Block title="OpenAI-compatible endpoint" desc="Used for inline writing, interpret-on-select, and widget generation.">
              <Field label="Base URL">
                <input className="input" value={llmBase} onChange={(e) => setLlmBase(e.target.value)} placeholder="https://api.openai.com/v1" style={{ fontFamily: 'var(--mono)', fontSize: 12 }} />
              </Field>
              <Field label="API key">
                <div style={{ position:'relative' }} data-comment-anchor="488ac3604f-input-70-17">
                  <input
                    className="input"
                    value={llmKey}
                    onChange={(e) => setLlmKey(e.target.value)}
                    type={llmKeyVisible ? 'text' : 'password'}
                    style={{ fontFamily: 'var(--mono)', fontSize: 12, paddingRight: 38 }}
                  />
                  <button
                    type="button"
                    onClick={() => setLlmKeyVisible(v => !v)}
                    title={llmKeyVisible ? 'Hide API key' : 'Show API key'}
                    style={{
                      position:'absolute', right:6, top:'50%', transform:'translateY(-50%)',
                      background:'transparent', border:'none', cursor:'pointer',
                      color:'var(--ink-soft)', padding:6, display:'inline-flex', borderRadius:'var(--r-sm)'
                    }}
                  >
                    <Icon name={llmKeyVisible ? 'eye_off' : 'eye'} size={15}/>
                  </button>
                </div>
              </Field>
            </Block>

            <Block title="Model library" desc="Add any OpenAI-compatible model id. Free-text provider tag is optional and informational.">
              <div data-comment-anchor="63073a2f22-select-73-17" style={{ display:'flex', flexDirection:'column', gap:10 }}>
                <ModelList
                  models={llmModels}
                  onRemove={removeModel}
                  onAdvanced={(id) => { setAdvancedModelId(id); setAdvancedOpen(true); }}
                  hasAdvanced={(id) => !!advanced[id] && Object.values(advanced[id]).some(v => v !== '' && v !== false && v != null)}
                />
                {!addingModel ? (
                  <button
                    onClick={() => setAddingModel(true)}
                    className="btn btn-sm"
                    style={{ alignSelf:'flex-start' }}
                  >
                    <Icon name="plus" size={12}/> Add model
                  </button>
                ) : (
                  <div className="scale-in" style={{
                    border:'1px solid var(--rule)', borderRadius:'var(--r-md)', padding:12,
                    background:'var(--paper-2)', display:'flex', flexDirection:'column', gap:8
                  }}>
                    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                      <div>
                        <div className="field-label">Model id</div>
                        <input
                          autoFocus
                          className="input"
                          value={draftModel.id}
                          onChange={e => setDraftModel(m => ({ ...m, id: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitNewModel();
                            if (e.key === 'Escape') { setAddingModel(false); setDraftModel({ id:'', provider:'' }); }
                          }}
                          placeholder="gpt-4.1-nano"
                          style={{ fontFamily:'var(--mono)', fontSize:12 }}
                        />
                      </div>
                      <div>
                        <div className="field-label">Provider (free text)</div>
                        <input
                          className="input"
                          value={draftModel.provider}
                          onChange={e => setDraftModel(m => ({ ...m, provider: e.target.value }))}
                          placeholder="OpenAI · or your own label"
                          style={{ fontSize:12 }}
                        />
                      </div>
                    </div>
                    <div style={{ display:'flex', gap:6, justifyContent:'flex-end' }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => { setAddingModel(false); setDraftModel({ id:'', provider:'' }); }}>Cancel</button>
                      <button className="btn btn-primary btn-sm" onClick={commitNewModel} disabled={!draftModel.id.trim()}>
                        <Icon name="check" size={13}/> Add to library
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </Block>

            <Block title="What the LLM can do" desc="Assign a model to each capability — or pick None to disable.">
              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                {capRows.map(c => (
                  <CapabilityRow
                    key={c.key}
                    label={c.label}
                    desc={c.desc}
                    models={llmModels}
                    value={caps[c.key]}
                    onChange={(v) => setCaps(prev => ({ ...prev, [c.key]: v }))}
                  />
                ))}
              </div>
            </Block>

            <button className="btn btn-sm" data-comment-anchor="fce753d3cd-button-83-17" onClick={() => setAdvancedOpen(true)} style={{ alignSelf:'flex-start' }}>
              <Icon name="settings" size={13} /> Advanced model config
            </button>
          </div>
        )}

        {section === 'display' && (
          <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <Block title="Appearance">
              <label style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', color:'var(--ink)' }}>Dark mode <Toggle on={dark} onChange={setDark} /></label>
            </Block>
            <Block title="Editor density">
              <div style={{ display: 'flex', gap: 6 }}>
                {['Comfortable', 'Compact', 'Reading'].map((d, i) =>
                  <button key={d} className="btn btn-sm" style={i === 0 ? { background: 'var(--ink)', color: 'var(--paper)', borderColor: 'var(--ink)' } : {}}>{d}</button>
                )}
              </div>
            </Block>
          </div>
        )}

        {section === 'account' && (
          <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <Block title="Signed in as">
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '8px 0' }}>
                <span style={{
                  width: 42, height: 42, borderRadius: '50%', background: 'var(--ink)', color: 'var(--paper)',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 500
                }}>{(user?.name || 'A').slice(0, 1)}</span>
                <div>
                  <div style={{ fontFamily: 'var(--serif)', fontSize: 17, color:'var(--ink)' }}>{user?.name || 'Anonymous'}</div>
                  <div className="t-meta">{user?.email || 'unknown@studio.press'}</div>
                </div>
              </div>
            </Block>
            <button onClick={onSignOut} className="btn" style={{ justifyContent: 'center', color: 'var(--err)', borderColor: 'var(--err)' }}>
              Sign out
            </button>
          </div>
        )}
      </div>

      {advancedOpen && (
        <AdvancedModelConfig
          models={llmModels}
          modelId={advancedModelId}
          setModelId={setAdvancedModelId}
          config={adv}
          setConfig={setAdv}
          onClose={() => setAdvancedOpen(false)}
        />
      )}
    </Drawer>
  );
};

/* ---------- Model list (chips) ---------- */
const ModelList = ({ models, onRemove, onAdvanced, hasAdvanced }) => (
  <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
    {models.length === 0 && (
      <div style={{ padding:14, border:'1px dashed var(--rule-strong)', borderRadius:'var(--r-md)', textAlign:'center', color:'var(--ink-soft)', fontSize:12 }}>
        No models yet. Add one below.
      </div>
    )}
    {models.map(m => (
      <div key={m.id} style={{
        display:'flex', alignItems:'center', gap:10,
        padding:'8px 10px', borderRadius:'var(--r-md)',
        border:'1px solid var(--rule)', background:'var(--paper)',
      }}>
        <div style={{ flex:1, minWidth:0, display:'flex', flexDirection:'column', gap:2 }}>
          <span style={{ fontFamily:'var(--mono)', fontSize:12, color:'var(--ink)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{m.id}</span>
          <span style={{ fontFamily:'var(--sans)', fontSize:10, color:'var(--ink-soft)', letterSpacing:'.04em' }}>{m.provider || 'Custom'}</span>
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => onAdvanced(m.id)}
          title="Advanced config for this model"
          style={{ position:'relative', padding:'4px 6px' }}
        >
          <Icon name="settings" size={13}/>
          {hasAdvanced && hasAdvanced(m.id) && (
            <span style={{ position:'absolute', top:2, right:2, width:6, height:6, borderRadius:'50%', background:'var(--accent)' }}/>
          )}
        </button>
        {models.length > 1 && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onRemove(m.id)}
            title="Remove model"
            style={{ padding:'4px 6px', color:'var(--ink-mute)' }}
          >
            <Icon name="trash" size={13}/>
          </button>
        )}
      </div>
    ))}
  </div>
);

/* ---------- Capability row: pick a model id or None ---------- */
const CapabilityRow = ({ label, desc, models, value, onChange }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef();
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    if (open) document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);
  const disabled = value == null;
  return (
    <div style={{
      display:'flex', alignItems:'center', justifyContent:'space-between', gap:14,
      padding:'10px 12px', borderRadius:'var(--r-md)',
      border:'1px solid var(--rule)', background:'var(--paper)',
      opacity: disabled ? 0.78 : 1, transition:'opacity .15s ease'
    }}>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontFamily:'var(--sans)', fontSize:13, fontWeight:600, color:'var(--ink)' }}>{label}</div>
        <div style={{ fontFamily:'var(--serif)', fontSize:12, color:'var(--ink-soft)', marginTop:2, lineHeight:1.5 }}>{desc}</div>
      </div>
      <div style={{ position:'relative', flexShrink:0 }} ref={ref}>
        <button
          onClick={() => setOpen(o => !o)}
          style={{
            display:'inline-flex', alignItems:'center', gap:6,
            padding:'6px 10px', borderRadius:'var(--r-sm)',
            border:'1px solid', borderColor: disabled ? 'var(--rule)' : 'var(--accent-tint)',
            background: disabled ? 'var(--paper-2)' : 'var(--accent-soft)',
            color: disabled ? 'var(--ink-mute)' : 'var(--accent)',
            fontFamily:'var(--mono)', fontSize:11, cursor:'pointer', maxWidth:200,
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'
          }}
        >
          {disabled ? <span style={{ fontFamily:'var(--sans)', fontWeight:600 }}>None</span> : value}
          <Icon name="chev_down" size={11}/>
        </button>
        {open && (
          <div className="scale-in" style={{
            position:'absolute', top:'calc(100% + 6px)', right:0, zIndex:30,
            background:'var(--paper)', border:'1px solid var(--rule)', borderRadius:'var(--r-md)',
            boxShadow:'var(--shadow-3)', padding:6, minWidth:240
          }}>
            <button
              onClick={() => { onChange(null); setOpen(false); }}
              style={{
                width:'100%', display:'flex', alignItems:'center', gap:10,
                padding:'7px 10px', border:'none', borderRadius:'var(--r-sm)',
                background:'transparent', color:'var(--ink-mute)', textAlign:'left', cursor:'pointer', fontSize:13
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--paper-2)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <Icon name="eye_off" size={13}/>
              <span style={{ flex:1, fontWeight:600 }}>None — disable</span>
              {value == null && <Icon name="check" size={13} stroke="var(--accent)"/>}
            </button>
            <div style={{ height:1, background:'var(--rule-soft)', margin:'4px 0' }}/>
            {models.map(m => (
              <button
                key={m.id}
                onClick={() => { onChange(m.id); setOpen(false); }}
                style={{
                  width:'100%', display:'flex', alignItems:'center', gap:10,
                  padding:'7px 10px', border:'none', borderRadius:'var(--r-sm)',
                  background:'transparent', color:'var(--ink)', textAlign:'left', cursor:'pointer'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--paper-2)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <span style={{ display:'flex', flexDirection:'column', flex:1, minWidth:0 }}>
                  <span style={{ fontFamily:'var(--mono)', fontSize:12, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{m.id}</span>
                  <span style={{ fontFamily:'var(--sans)', fontSize:10, color:'var(--ink-soft)' }}>{m.provider}</span>
                </span>
                {value === m.id && <Icon name="check" size={13} stroke="var(--accent)"/>}
              </button>
            ))}
            {models.length === 0 && (
              <div style={{ padding:'8px 10px', color:'var(--ink-soft)', fontSize:12, fontStyle:'italic' }}>
                No models in your library yet.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

/* ---------- Advanced model config (sub-modal inside drawer) ---------- */
const AdvancedModelConfig = ({ models, modelId, setModelId, config, setConfig, onClose }) => {
  const current = models.find(m => m.id === modelId);
  return (
    <div className="fade-in" onClick={onClose} style={{
      position:'absolute', inset:0, background:'rgba(11,13,16,.4)', zIndex:40,
      display:'flex', alignItems:'stretch', justifyContent:'flex-end'
    }}>
      <div onClick={e => e.stopPropagation()} className="slide-in-right" style={{
        width:'100%', maxWidth:460, background:'var(--paper)', display:'flex', flexDirection:'column',
        borderLeft:'1px solid var(--rule)', boxShadow:'var(--shadow-4)'
      }}>
        <header style={{ padding:'18px 22px 14px', borderBottom:'1px solid var(--rule)', display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
          <div>
            <div className="t-kicker" style={{ marginBottom:4 }}>Advanced</div>
            <div style={{ fontFamily:'var(--serif)', fontSize:20, letterSpacing:'-0.015em', color:'var(--ink)' }}>Model parameters</div>
            <div className="t-meta" style={{ marginTop:4 }}>Leave anything blank to use the endpoint's default.</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}><Icon name="x" size={14}/></button>
        </header>

        <div style={{ padding:'14px 22px', borderBottom:'1px solid var(--rule)' }}>
          <div className="field-label">Configure for model</div>
          <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
            {models.map(m => (
              <button key={m.id} onClick={() => setModelId(m.id)} style={{
                padding:'6px 10px', borderRadius:'var(--r-pill)',
                border: m.id === modelId ? '1.5px solid var(--accent)' : '1px solid var(--rule)',
                background: m.id === modelId ? 'var(--accent-soft)' : 'var(--paper)',
                color: m.id === modelId ? 'var(--accent)' : 'var(--ink)',
                fontFamily:'var(--mono)', fontSize:11, cursor:'pointer'
              }}>{m.id}</button>
            ))}
          </div>
          {current && <div className="t-meta" style={{ marginTop:8 }}>Provider · <span style={{ color:'var(--ink)' }}>{current.provider}</span></div>}
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:'18px 22px 28px', display:'flex', flexDirection:'column', gap:18 }}>

          <Block title="Capabilities" desc="Tell SLAIDES what this model supports. Used to gate features in the editor + presenter.">
            <CheckRow
              label="Supports image input"
              desc="Lets you attach screenshots to inline AI chat and Interpret."
              checked={!!config.supports_image}
              onChange={(v) => setConfig({ supports_image: v })}
            />
            <CheckRow
              label="Supports internet search"
              desc="Lets the model use a built-in web tool, if your endpoint provides one."
              checked={!!config.supports_search}
              onChange={(v) => setConfig({ supports_search: v })}
            />
          </Block>

          <Block title="Limits" desc="Affect how SLAIDES chunks context. Blank means use the endpoint's default.">
            <Field label="Max context window (tokens)">
              <input
                className="input"
                value={config.max_context ?? ''}
                onChange={(e) => setConfig({ max_context: e.target.value.replace(/[^\d]/g, '') })}
                placeholder="128000"
                style={{ fontFamily:'var(--mono)', fontSize:12 }}
              />
            </Field>
            <Field label="Max output tokens">
              <input
                className="input"
                value={config.max_output ?? ''}
                onChange={(e) => setConfig({ max_output: e.target.value.replace(/[^\d]/g, '') })}
                placeholder="4096"
                style={{ fontFamily:'var(--mono)', fontSize:12 }}
              />
            </Field>
          </Block>

          <Block title="Common parameters" desc="Forwarded as-is to your endpoint. All blank by default.">
            <Field label="Temperature">
              <input
                className="input"
                value={config.temperature ?? ''}
                onChange={(e) => setConfig({ temperature: e.target.value })}
                placeholder="e.g. 0.7"
                style={{ fontFamily:'var(--mono)', fontSize:12 }}
              />
            </Field>
            <Field label="Top-p">
              <input
                className="input"
                value={config.top_p ?? ''}
                onChange={(e) => setConfig({ top_p: e.target.value })}
                placeholder="e.g. 1.0"
                style={{ fontFamily:'var(--mono)', fontSize:12 }}
              />
            </Field>
            <Field label="Frequency penalty">
              <input
                className="input"
                value={config.frequency_penalty ?? ''}
                onChange={(e) => setConfig({ frequency_penalty: e.target.value })}
                placeholder="e.g. 0.0"
                style={{ fontFamily:'var(--mono)', fontSize:12 }}
              />
            </Field>
            <Field label="System prompt prefix">
              <textarea
                className="input"
                rows={3}
                value={config.system_prefix ?? ''}
                onChange={(e) => setConfig({ system_prefix: e.target.value })}
                placeholder="(blank — SLAIDES uses its own purpose-specific prompts)"
                style={{ fontFamily:'var(--sans)', fontSize:13, resize:'vertical' }}
              />
            </Field>
          </Block>
        </div>

        <footer style={{ padding:'12px 22px', borderTop:'1px solid var(--rule)', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <span className="t-mono" style={{ color:'var(--ink-soft)' }}>changes apply immediately</span>
          <button className="btn btn-primary btn-sm" onClick={onClose}>Done</button>
        </footer>
      </div>
    </div>
  );
};

const CheckRow = ({ label, desc, checked, onChange }) => (
  <button
    onClick={() => onChange(!checked)}
    style={{
      display:'flex', alignItems:'flex-start', gap:12, width:'100%',
      padding:'10px 12px', borderRadius:'var(--r-md)',
      border:'1px solid var(--rule)', background:'var(--paper)',
      textAlign:'left', cursor:'pointer'
    }}
  >
    <span style={{
      flexShrink:0, width:18, height:18, borderRadius:4, marginTop:2,
      border: checked ? '1.5px solid var(--accent)' : '1.5px solid var(--rule-strong)',
      background: checked ? 'var(--accent)' : 'transparent',
      display:'inline-flex', alignItems:'center', justifyContent:'center', color:'#fff',
      transition:'background .12s ease, border-color .12s ease'
    }}>
      {checked && <Icon name="check" size={12} stroke="#fff" strokeWidth={2.4}/>}
    </span>
    <span style={{ flex:1 }}>
      <span style={{ fontFamily:'var(--sans)', fontSize:13, fontWeight:600, color:'var(--ink)', display:'block' }}>{label}</span>
      <span style={{ fontFamily:'var(--serif)', fontSize:12, color:'var(--ink-soft)', display:'block', marginTop:2, lineHeight:1.5 }}>{desc}</span>
    </span>
  </button>
);

const Block = ({ title, desc, children }) =>
  <section>
    <div style={{ fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 13, marginBottom: 4, color:'var(--ink)' }}>{title}</div>
    {desc && <div style={{ fontFamily: 'var(--serif)', fontSize: 13, color: 'var(--ink-soft)', marginBottom: 12, lineHeight: 1.55 }}>{desc}</div>}
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{children}</div>
  </section>;

const Field = ({ label, children }) =>
  <label style={{ display:'block' }}>
    <div className="field-label">{label}</div>
    {children}
  </label>;


window.SettingsDrawer = SettingsDrawer;
