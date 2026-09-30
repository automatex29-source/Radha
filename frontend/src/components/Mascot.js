/** Krish, the friendly robot on the welcome screen. Pure SVG so it stays sharp and light. */
export default function Mascot({ className = "" }) {
  return (
    <svg viewBox="0 0 340 300" className={className} role="img" aria-label="Krish, the Krish AI robot, waving">
      <defs>
        <radialGradient id="km-glow" cx="50%" cy="55%" r="50%">
          <stop offset="0%" stopColor="#c7b8ff" stopOpacity="0.75" />
          <stop offset="55%" stopColor="#f5c6e8" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="km-shell" x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="70%" stopColor="#eef0ff" />
          <stop offset="100%" stopColor="#d9dcfb" />
        </linearGradient>
        <linearGradient id="km-visor" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2b2f6b" />
          <stop offset="100%" stopColor="#12153a" />
        </linearGradient>
        <linearGradient id="km-badge" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#5b8cff" />
          <stop offset="100%" stopColor="#6d4bff" />
        </linearGradient>
        <linearGradient id="km-doc" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ffe3f1" />
          <stop offset="100%" stopColor="#e6dcff" />
        </linearGradient>
        <linearGradient id="km-ring" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#a78bfa" stopOpacity="0" />
          <stop offset="50%" stopColor="#8b8cff" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#60c6ff" stopOpacity="0.1" />
        </linearGradient>
        <radialGradient id="km-bulb" cx="40%" cy="35%" r="65%">
          <stop offset="0%" stopColor="#fff7c2" />
          <stop offset="100%" stopColor="#ffc93d" />
        </radialGradient>
        <filter id="km-eye" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.2" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="km-soft" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="8" stdDeviation="9" floodColor="#6d5dfc" floodOpacity="0.22" />
        </filter>
      </defs>

      <ellipse className="km-glow" cx="170" cy="170" rx="165" ry="125" fill="url(#km-glow)" />
      {/* soft pink cloud behind */}
      <path d="M40 215 C 30 160, 95 130, 130 160 C 150 120, 230 125, 245 175 C 290 170, 315 215, 280 245 C 220 280, 90 280, 40 215 Z" fill="#f9d3ea" opacity="0.55" className="km-glow" />

      {/* orbit ring (back half) */}
      <ellipse cx="175" cy="205" rx="140" ry="36" fill="none" stroke="url(#km-ring)" strokeWidth="3" transform="rotate(-10 175 205)" />

      {/* lightbulb */}
      <g transform="translate(292 38) rotate(14)">
        <circle cx="0" cy="0" r="17" fill="url(#km-bulb)" />
        <rect x="-7" y="15" width="14" height="10" rx="3" fill="#b9a6ff" />
        <path d="M-5 -2 q5 -7 10 0" stroke="#fff" strokeWidth="2.5" fill="none" strokeLinecap="round" opacity="0.9" />
        <g stroke="#ffd95e" strokeWidth="2.5" strokeLinecap="round">
          <line x1="-26" y1="-6" x2="-33" y2="-9" /><line x1="-20" y1="-22" x2="-25" y2="-29" /><line x1="0" y1="-26" x2="0" y2="-34" />
        </g>
      </g>

      {/* body */}
      <g filter="url(#km-soft)">
        <path d="M120 200 C 118 160, 222 160, 220 200 C 222 250, 195 268, 170 268 C 145 268, 118 250, 120 200 Z" fill="url(#km-shell)" />
        {/* waving arm */}
        <g transform="rotate(-38 222 196)">
          <rect x="214" y="150" width="26" height="58" rx="13" fill="url(#km-shell)" />
          <circle cx="227" cy="148" r="15" fill="url(#km-shell)" />
        </g>
        {/* left arm */}
        <rect x="100" y="188" width="26" height="52" rx="13" fill="url(#km-shell)" transform="rotate(28 113 214)" />
      </g>
      <circle cx="170" cy="214" r="21" fill="url(#km-badge)" />
      <path d="M163 203 v22 M163 214 l11 -11 M166 211 l9 14" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" fill="none" />

      {/* document held in front */}
      <g transform="translate(62 176) rotate(-14)">
        <rect x="0" y="0" width="64" height="80" rx="10" fill="url(#km-doc)" stroke="#fff" strokeWidth="2" />
        <rect x="10" y="12" width="16" height="14" rx="3" fill="#f3a6d0" />
        <rect x="31" y="14" width="24" height="4" rx="2" fill="#b6a3f5" />
        <rect x="31" y="22" width="18" height="4" rx="2" fill="#cfc2fb" />
        <rect x="10" y="36" width="44" height="4" rx="2" fill="#c7b8fb" />
        <rect x="10" y="46" width="38" height="4" rx="2" fill="#d9cffc" />
        <rect x="10" y="56" width="42" height="4" rx="2" fill="#d9cffc" />
      </g>

      {/* head */}
      <g filter="url(#km-soft)">
        <circle cx="106" cy="104" r="15" fill="#c9c3ff" />
        <circle cx="234" cy="104" r="15" fill="#c9c3ff" />
        <rect x="100" y="42" width="140" height="120" rx="54" fill="url(#km-shell)" />
      </g>
      <circle cx="106" cy="104" r="7" fill="#8f86ff" />
      <circle cx="234" cy="104" r="7" fill="#8f86ff" />
      <rect x="116" y="66" width="108" height="72" rx="34" fill="url(#km-visor)" />
      <path d="M128 78 q18 -8 40 -6" stroke="#fff" strokeOpacity="0.18" strokeWidth="5" strokeLinecap="round" fill="none" />
      <g filter="url(#km-eye)" stroke="#5ee7ff" strokeWidth="6" strokeLinecap="round" fill="none">
        <path d="M140 106 q10 -13 21 0" />
        <path d="M179 106 q10 -13 21 0" />
        <path d="M160 119 q10 8 20 0" strokeWidth="4" />
      </g>

      {/* orbit ring (front half) and floating orbs */}
      <path d="M36 226 C 90 250, 250 236, 312 186" fill="none" stroke="url(#km-ring)" strokeWidth="3" />
      <circle cx="318" cy="120" r="10" fill="#7cc8ff" opacity="0.9" />
      <circle cx="282" cy="236" r="12" fill="#b9a6ff" opacity="0.85" />
      <circle cx="278" cy="232" r="4" fill="#fff" opacity="0.7" />

      {/* sparkles */}
      <g fill="#fff">
        <path d="M60 70 l3 9 l9 3 l-9 3 l-3 9 l-3 -9 l-9 -3 l9 -3 z" opacity="0.95" />
        <path d="M300 150 l2 6 l6 2 l-6 2 l-2 6 l-2 -6 l-6 -2 l6 -2 z" opacity="0.9" />
      </g>
    </svg>
  );
}
