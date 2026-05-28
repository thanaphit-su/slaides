/* ============ SLAIDES — shared components & icons ============ */

const { useState, useEffect, useRef, useLayoutEffect, useMemo, useCallback } = React;

/* ---------- Icons (hand-tuned, single-stroke, 20×20 viewBox) ---------- */
const Icon = ({ name, size = 18, stroke = 'currentColor', strokeWidth = 1.4, style }) => {
  const paths = {
    plus:        <path d="M10 4v12M4 10h12"/>,
    minus:       <path d="M4 10h12"/>,
    x:           <path d="M5 5l10 10M15 5L5 15"/>,
    chev_right:  <path d="M8 5l5 5-5 5"/>,
    chev_left:   <path d="M12 5l-5 5 5 5"/>,
    chev_down:   <path d="M5 8l5 5 5-5"/>,
    chev_up:     <path d="M5 12l5-5 5 5"/>,
    play:        <path d="M6 4l10 6-10 6V4z" fill="currentColor" stroke="none"/>,
    pause:       <g><rect x="5" y="4" width="3" height="12" fill="currentColor" stroke="none"/><rect x="12" y="4" width="3" height="12" fill="currentColor" stroke="none"/></g>,
    sun:         <g><circle cx="10" cy="10" r="3.2"/><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4 4l1.5 1.5M14.5 14.5L16 16M16 4l-1.5 1.5M5.5 14.5L4 16"/></g>,
    moon:        <path d="M15 11.5A6 6 0 0 1 8.5 5 6 6 0 1 0 15 11.5z"/>,
    user:        <g><circle cx="10" cy="7.5" r="3"/><path d="M4 17c0-3 2.7-5 6-5s6 2 6 5"/></g>,
    users:       <g><circle cx="7.5" cy="8" r="2.5"/><circle cx="13.5" cy="8" r="2.5"/><path d="M3 16c0-2.5 2-4 4.5-4M17 16c0-2.5-2-4-4.5-4"/></g>,
    settings:    <g><circle cx="10" cy="10" r="2.2"/><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4 4l1.5 1.5M14.5 14.5L16 16M16 4l-1.5 1.5M5.5 14.5L4 16"/></g>,
    gear:        <g><circle cx="10" cy="10" r="2.5"/><path d="M10 1.5l1.2 2 2.3-.2.8 2.2 2.1 1-1 2.2.8 2.1-2 1.1-.2 2.3-2.3.3-1 2-2.2-1-2.1 1-1.4-1.9-2.3-.2-.3-2.3-2-1L1.5 9 .6 6.7 2.7 5.6l.3-2.3 2.3-.3 1.1-2 2.2 1L10 1.5z"/></g>,
    search:      <g><circle cx="9" cy="9" r="5"/><path d="M13 13l3 3"/></g>,
    book:        <path d="M4 4h5.5c1.4 0 2.5 1.1 2.5 2.5V17H5.5C4.7 17 4 16.3 4 15.5V4zM16 4h-5.5C9.1 4 8 5.1 8 6.5V17h6.5c.8 0 1.5-.7 1.5-1.5V4z"/>,
    book_open:   <path d="M3 4.5C5 4 8 4 10 5.5 12 4 15 4 17 4.5V15c-2-.5-5-.5-7 1-2-1.5-5-1.5-7-1V4.5z"/>,
    grid:        <g><rect x="3" y="3" width="6" height="6"/><rect x="11" y="3" width="6" height="6"/><rect x="3" y="11" width="6" height="6"/><rect x="11" y="11" width="6" height="6"/></g>,
    list:        <g><path d="M4 5h12M4 10h12M4 15h12"/></g>,
    deck:        <g><rect x="3" y="6" width="14" height="9" rx="1"/><path d="M5 4h10M6 2.5h8"/></g>,
    widget:      <g><rect x="3" y="3" width="6" height="6" rx="1"/><circle cx="14" cy="6" r="3"/><rect x="3" y="11" width="14" height="6" rx="1"/></g>,
    palette:     <g><circle cx="10" cy="10" r="6"/><circle cx="7" cy="7.5" r=".8" fill="currentColor"/><circle cx="12.5" cy="7" r=".8" fill="currentColor"/><circle cx="13.5" cy="11" r=".8" fill="currentColor"/></g>,
    sparkles:    <g><path d="M10 3l1.4 3.4L15 8l-3.6 1.6L10 13l-1.4-3.4L5 8l3.6-1.6L10 3z"/><path d="M15.5 14.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6.6-1.4z"/></g>,
    spark:       <path d="M10 2l2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6z"/>,
    arrow_right: <path d="M4 10h11M11 6l4 4-4 4"/>,
    arrow_left:  <path d="M16 10H5M9 6l-4 4 4 4"/>,
    upload:      <path d="M10 14V4M6 8l4-4 4 4M4 16h12"/>,
    download:    <path d="M10 4v10M14 10l-4 4-4-4M4 16h12"/>,
    share:       <g><circle cx="5" cy="10" r="2"/><circle cx="15" cy="5" r="2"/><circle cx="15" cy="15" r="2"/><path d="M7 9l6-3M7 11l6 3"/></g>,
    link:        <path d="M8 12l-1 1a3 3 0 0 1-4.2-4.2L5 6.5M12 8l1-1a3 3 0 0 1 4.2 4.2L15 13.5M7.5 12.5l5-5"/>,
    copy:        <g><rect x="6" y="6" width="9" height="11" rx="1.5"/><path d="M4 13V4.5C4 3.7 4.7 3 5.5 3H12"/></g>,
    edit:        <path d="M4 16l1-3 8-8 3 3-8 8-3 1z"/>,
    trash:       <path d="M5 6h10M8 6V4h4v2M6.5 6l.7 10.2c0 .5.4.8.8.8h4c.4 0 .8-.3.8-.8L13.5 6"/>,
    eye:         <g><path d="M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5z"/><circle cx="10" cy="10" r="2"/></g>,
    eye_off:     <g><path d="M3 3l14 14M5 6.5C3.5 8 2 10 2 10s3 5 8 5c1.6 0 3-.5 4.2-1.3M8 5.2C8.6 5 9.3 5 10 5c5 0 8 5 8 5s-.9 1.5-2.5 3"/></g>,
    poll:        <g><rect x="4" y="11" width="3" height="6"/><rect x="8.5" y="7" width="3" height="10"/><rect x="13" y="3" width="3" height="14"/></g>,
    question:    <g><circle cx="10" cy="10" r="7"/><path d="M8 8a2 2 0 1 1 3 1.7c-.8.4-1 1-1 1.6"/><circle cx="10" cy="14" r=".6" fill="currentColor"/></g>,
    hand:        <path d="M7 14V5.5a1.5 1.5 0 1 1 3 0V11M10 11V4.5a1.5 1.5 0 1 1 3 0V11M13 11V6.5a1.5 1.5 0 1 1 3 0V13a4 4 0 0 1-8 0v-2"/>,
    dot:         <circle cx="10" cy="10" r="3" fill="currentColor" stroke="none"/>,
    check:       <path d="M4 10l4 4 8-8"/>,
    code:        <path d="M7 6l-4 4 4 4M13 6l4 4-4 4"/>,
    md:          <g><rect x="2" y="5" width="16" height="10" rx="1.5"/><path d="M5 13V7l2 2 2-2v6M11 7v4M11 11l2-2M13 9l1 1.2"/></g>,
    flag:        <path d="M5 17V3M5 4l8 1-1 4 1 4-8-1"/>,
    section:     <g><path d="M5 7c0-2 4-2 4 0s-4 0-4 2 4 2 4 4-4 2-4 0M15 9l-3 4-2-3"/></g>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={style}>
      {paths[name] || null}
    </svg>
  );
};

/* ---------- Wordmark ---------- */
const Wordmark = ({ size = 18, withMark = true, style }) => (
  <span style={{ display:'inline-flex', alignItems:'center', gap:8, ...style }}>
    {withMark && (
      <svg width={size + 4} height={size + 4} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="3" y="6" width="18" height="13" rx="2" />
        <path d="M3 10h18" />
        <circle cx="6.5" cy="8" r=".7" fill="currentColor" stroke="none"/>
      </svg>
    )}
    <span style={{ fontFamily:'var(--serif)', fontWeight:500, fontSize: size, letterSpacing:'0.22em' }}>SLAIDES</span>
  </span>
);

/* ---------- Modal / drawer ---------- */
const Backdrop = ({ onClick, children }) => (
  <div onClick={onClick} className="fade-in" style={{
    position:'fixed', inset:0, background:'rgba(11,13,16,0.42)', zIndex: 50,
    display:'flex', alignItems:'center', justifyContent:'center'
  }}>
    {children}
  </div>
);

const Drawer = ({ open, side = 'right', width = 380, onClose, children }) => {
  if (!open) return null;
  return (
    <Backdrop onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        className="slide-in-right"
        style={{
          position:'fixed', top:0, bottom:0, [side]:0, width,
          background:'var(--paper)', borderLeft: side==='right' ? '1px solid var(--rule)' : 'none',
          borderRight: side==='left'  ? '1px solid var(--rule)' : 'none',
          boxShadow:'var(--shadow-4)', display:'flex', flexDirection:'column'
        }}
      >
        {children}
      </div>
    </Backdrop>
  );
};

/* ---------- Toggle ---------- */
const Toggle = ({ on, onChange, label }) => (
  <button
    onClick={() => onChange && onChange(!on)}
    style={{
      display:'inline-flex', alignItems:'center', gap:10, background:'transparent', border:'none', padding:0, color:'var(--ink)',
      cursor:'pointer'
    }}
  >
    <span style={{
      width:34, height:20, borderRadius:999, background: on ? 'var(--accent)' : 'var(--rule-strong)',
      position:'relative', transition:'background .15s ease', display:'inline-block', flexShrink:0
    }}>
      <span style={{
        position:'absolute', top:2, left: on ? 16 : 2, width:16, height:16, borderRadius:'50%',
        background:'#fff', transition:'left .15s ease', boxShadow:'0 1px 2px rgba(0,0,0,.2)'
      }}/>
    </span>
    {label && <span style={{ fontSize:13, color:'var(--ink)' }}>{label}</span>}
  </button>
);

/* ---------- Tooltip ---------- */
const Tooltip = ({ text, children }) => {
  const [show, setShow] = useState(false);
  return (
    <span style={{ position:'relative', display:'inline-flex' }} onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
      {children}
      {show && (
        <span style={{
          position:'absolute', bottom:'calc(100% + 6px)', left:'50%', transform:'translateX(-50%)',
          background:'var(--ink)', color:'var(--paper)', padding:'4px 8px', borderRadius:'var(--r-sm)',
          fontFamily:'var(--sans)', fontSize:11, whiteSpace:'nowrap', pointerEvents:'none', zIndex:60
        }}>{text}</span>
      )}
    </span>
  );
};

/* ---------- Live dot ---------- */
const LiveDot = ({ size = 8, color = 'var(--live)' }) => (
  <span style={{ display:'inline-flex', alignItems:'center', position:'relative', width:size, height:size }}>
    <span style={{
      position:'absolute', inset:0, borderRadius:'50%', background:color, opacity:.4,
      animation:'pulse 1.6s ease-in-out infinite'
    }}/>
    <span style={{ position:'absolute', inset:2, borderRadius:'50%', background:color }}/>
  </span>
);

/* ---------- Deck cover thumbnail (placeholder art) ---------- */
const DeckCover = ({ variant = 'fieldnotes', style }) => {
  // Each variant draws a small editorial composition referencing the slide style.
  const compositions = {
    fieldnotes: (
      <svg viewBox="0 0 320 200" style={{ width:'100%', height:'100%', display:'block' }}>
        <rect width="320" height="200" fill="#fdfcf9"/>
        <text x="22" y="60" fontFamily="Newsreader, serif" fontSize="22" fill="#0b0d10" fontStyle="italic">A line is the</text>
        <text x="22" y="86" fontFamily="Newsreader, serif" fontSize="22" fill="#0b0d10">smallest possible</text>
        <text x="22" y="112" fontFamily="Newsreader, serif" fontSize="22" fill="#1f3a8a" fontStyle="italic">brain you can build.</text>
        <line x1="22" y1="130" x2="48" y2="130" stroke="#0b0d10" strokeWidth="1.2"/>
        <text x="22" y="148" fontFamily="Inter, sans-serif" fontSize="9" fill="#4b525b">15 MIN · 4 INTERACTIVES</text>
        <circle cx="280" cy="40" r="3" fill="#c2410c"/>
        <circle cx="296" cy="64" r="2" fill="#117a45"/>
        <circle cx="270" cy="80" r="2.5" fill="#be1d4a"/>
      </svg>
    ),
    onboarding: (
      <svg viewBox="0 0 320 200" style={{ width:'100%', height:'100%', display:'block' }}>
        <rect width="320" height="200" fill="#f6f6f1"/>
        <rect x="22" y="40" width="80" height="6" fill="#1f3a8a"/>
        <text x="22" y="86" fontFamily="Newsreader, serif" fontSize="26" fill="#0b0d10">Welcome to</text>
        <text x="22" y="116" fontFamily="Newsreader, serif" fontSize="26" fill="#0b0d10" fontStyle="italic">cohort fourteen.</text>
        <text x="22" y="150" fontFamily="Inter, sans-serif" fontSize="10" fill="#4b525b">DAY ONE PLAYBOOK</text>
      </svg>
    ),
    allhands: (
      <svg viewBox="0 0 320 200" style={{ width:'100%', height:'100%', display:'block' }}>
        <rect width="320" height="200" fill="#0b0d10"/>
        <text x="22" y="60" fontFamily="Inter, sans-serif" fontSize="10" fill="#8bb0ff" letterSpacing="2">Q3 — ALL HANDS</text>
        <text x="22" y="100" fontFamily="Newsreader, serif" fontSize="28" fill="#fdfcf9">Plain talk</text>
        <text x="22" y="128" fontFamily="Newsreader, serif" fontSize="28" fill="#fdfcf9" fontStyle="italic">about the quarter.</text>
        <line x1="22" y1="150" x2="60" y2="150" stroke="#8bb0ff" strokeWidth="1.2"/>
      </svg>
    ),
    crit: (
      <svg viewBox="0 0 320 200" style={{ width:'100%', height:'100%', display:'block' }}>
        <rect width="320" height="200" fill="#f7f6f2"/>
        <rect x="22" y="22" width="160" height="60" fill="#fdfcf9" stroke="#0b0d10" strokeWidth="1"/>
        <rect x="32" y="32" width="50" height="6" fill="#cfccc4"/>
        <rect x="32" y="44" width="80" height="6" fill="#cfccc4"/>
        <rect x="32" y="56" width="60" height="6" fill="#cfccc4"/>
        <text x="22" y="116" fontFamily="Newsreader, serif" fontSize="22" fill="#0b0d10">A 45-minute</text>
        <text x="22" y="142" fontFamily="Newsreader, serif" fontSize="22" fill="#0b0d10" fontStyle="italic">generative critique.</text>
      </svg>
    ),
  };
  return <div style={style}>{compositions[variant] || compositions.fieldnotes}</div>;
};

/* expose globally for other babel files */
Object.assign(window, { Icon, Wordmark, Backdrop, Drawer, Toggle, Tooltip, LiveDot, DeckCover });
