import { useId } from "react";

// Drawn portraits of the Pro Counsellor agents (see lib/counselAgents.js). One 120x120 SVG each: a soft
// background, shoulders, face and the details that make each one recognisable.
const LOOKS = {
  krishna: { bg: ["#1e3a8a", "#6d28d9"], skin: "#5b8def", skinShade: "#4a74cf", hair: "#141a33", cloth: "#f5b72a" },
  bal_krishna: { bg: ["#f59e0b", "#f97316"], skin: "#6fa2f5", skinShade: "#5a8ae0", hair: "#1b2140", cloth: "#fde047" },
  radha: { bg: ["#db2777", "#f472b6"], skin: "#f3c6a2", skinShade: "#e2ad86", hair: "#2a1a14", cloth: "#be123c" },
  dost: { bg: ["#0f766e", "#34d399"], skin: "#d9a074", skinShade: "#c58a5e", hair: "#2b1d16", cloth: "#1e293b" },
  dadi: { bg: ["#7c3aed", "#c084fc"], skin: "#e6b993", skinShade: "#d4a27a", hair: "#e5e7eb", cloth: "#9f1239" },
};

/** The two background colours of an agent's portrait, for screens that match it. */
export const portraitColors = (id) => LOOKS[id]?.bg || ["#4f46e5", "#7c3aed"];

function Eyes({ open, y = 64 }) {
  if (!open) {
    // Calm, smiling closed eyes.
    return (
      <g stroke="#1f1a17" strokeWidth="2.4" strokeLinecap="round" fill="none">
        <path d={`M46 ${y} q5 -5 10 0`} />
        <path d={`M64 ${y} q5 -5 10 0`} />
      </g>
    );
  }
  return (
    <g>
      <ellipse cx="51" cy={y} rx="3.6" ry="4.4" fill="#1f1a17" />
      <ellipse cx="69" cy={y} rx="3.6" ry="4.4" fill="#1f1a17" />
      <circle cx="52.3" cy={y - 1.6} r="1.3" fill="#fff" />
      <circle cx="70.3" cy={y - 1.6} r="1.3" fill="#fff" />
    </g>
  );
}

function Face({ look, chubby = false, open = false, smile = "M53 77 q7 6 14 0" }) {
  const rx = chubby ? 23 : 20;
  return (
    <g>
      <rect x="53" y="78" width="14" height="16" rx="6" fill={look.skinShade} />
      <ellipse cx="38" cy="66" rx="4" ry="6" fill={look.skinShade} />
      <ellipse cx="82" cy="66" rx="4" ry="6" fill={look.skinShade} />
      <ellipse cx="60" cy="64" rx={rx} ry={chubby ? 23 : 24} fill={look.skin} />
      <Eyes open={open} />
      <circle cx="45" cy="72" r="4" fill="#fb7185" opacity="0.35" />
      <circle cx="75" cy="72" r="4" fill="#fb7185" opacity="0.35" />
      <path d={smile} stroke="#7a2e2e" strokeWidth="2.2" strokeLinecap="round" fill="none" />
    </g>
  );
}

function Shoulders({ color, trim }) {
  return (
    <g>
      <path d="M18 120 q4 -28 42 -30 q38 2 42 30 z" fill={color} />
      {trim && <path d="M44 92 q16 12 32 0" stroke={trim} strokeWidth="3" fill="none" strokeLinecap="round" />}
    </g>
  );
}

function PeacockFeather({ x, y, scale = 1, tilt = 18 }) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${tilt}) scale(${scale})`}>
      <path d="M0 16 q1 -10 0 -22" stroke="#15803d" strokeWidth="1.6" fill="none" />
      <ellipse cx="0" cy="-12" rx="6.5" ry="10" fill="#16a34a" />
      <ellipse cx="0" cy="-12" rx="4.2" ry="6.5" fill="#0ea5e9" />
      <ellipse cx="0" cy="-11" rx="2.4" ry="3.6" fill="#1e3a8a" />
      <circle cx="0" cy="-11" r="1.2" fill="#facc15" />
    </g>
  );
}

const PARTS = {
  krishna: (l) => (
    <>
      <path d="M34 66 q-6 26 4 42 l10 -8 q-8 -14 -4 -32 z" fill={l.hair} />
      <path d="M86 66 q6 26 -4 42 l-10 -8 q8 -14 4 -32 z" fill={l.hair} />
      <Shoulders color={l.cloth} trim="#b45309" />
      <circle cx="60" cy="98" r="0" />
      <path d="M44 96 q16 10 32 0" stroke="#fef3c7" strokeWidth="2" strokeDasharray="2 3" fill="none" />
      <Face look={l} />
      <path d="M38 56 q2 -22 22 -22 q20 0 22 22 q-10 -10 -22 -10 q-12 0 -22 10 z" fill={l.hair} />
      {/* Crown */}
      <path d="M40 42 l4 -14 l8 8 l8 -12 l8 12 l8 -8 l4 14 z" fill="#f5b72a" stroke="#b45309" strokeWidth="1.2" />
      <circle cx="60" cy="34" r="2.4" fill="#dc2626" />
      <PeacockFeather x={72} y={26} scale={1.05} tilt={20} />
      {/* Tilak */}
      <path d="M57 44 v8 q3 3 6 0 v-8" stroke="#fef3c7" strokeWidth="1.6" fill="none" />
      <circle cx="60" cy="52" r="1.3" fill="#dc2626" />
    </>
  ),
  bal_krishna: (l) => (
    <>
      <Shoulders color={l.cloth} trim="#f59e0b" />
      <circle cx="60" cy="100" r="3" fill="#dc2626" />
      <path d="M48 96 q12 8 24 0" stroke="#fde68a" strokeWidth="2.4" fill="none" strokeDasharray="1 3" strokeLinecap="round" />
      <Face look={l} chubby open smile="M52 76 q8 8 16 0" />
      <path d="M37 58 q0 -24 23 -24 q23 0 23 24 q-6 -6 -12 -7 q-4 6 -11 6 q-7 0 -11 -6 q-6 1 -12 7 z" fill={l.hair} />
      {/* Top knot with a little feather */}
      <circle cx="60" cy="32" r="7" fill={l.hair} />
      <path d="M53 34 q7 4 14 0" stroke="#facc15" strokeWidth="2" fill="none" />
      <PeacockFeather x={63} y={26} scale={0.7} tilt={14} />
      <circle cx="60" cy="50" r="1.6" fill="#dc2626" />
    </>
  ),
  radha: (l) => (
    <>
      {/* Veil behind */}
      <path d="M30 70 q-4 -40 30 -42 q34 2 30 42 l4 50 h-68 z" fill="#f472b6" />
      <Shoulders color={l.cloth} trim="#fbbf24" />
      <path d="M38 62 q-2 26 6 34 l6 -4 q-6 -12 -4 -30 z" fill={l.hair} />
      <path d="M82 62 q2 26 -6 34 l-6 -4 q6 -12 4 -30 z" fill={l.hair} />
      <Face look={l} smile="M54 77 q6 5 12 0" />
      <path d="M38 60 q0 -24 22 -24 q22 0 22 24 q-10 -14 -22 -14 q-12 0 -22 14 z" fill={l.hair} />
      <path d="M60 37 v10" stroke="#e11d48" strokeWidth="1.6" />
      {/* Veil edge with border */}
      <path d="M30 70 q-2 -38 30 -40 q32 2 30 40" stroke="#fbbf24" strokeWidth="3" fill="none" />
      <circle cx="60" cy="54" r="2" fill="#e11d48" />
      <circle cx="38" cy="74" r="2.4" fill="#fbbf24" />
      <circle cx="82" cy="74" r="2.4" fill="#fbbf24" />
      <circle cx="66" cy="72" r="1.3" fill="none" stroke="#fbbf24" strokeWidth="1" />
    </>
  ),
  dost: (l) => (
    <>
      <Shoulders color={l.cloth} />
      {/* Hoodie strings and collar */}
      <path d="M40 94 q20 12 40 0" stroke="#334155" strokeWidth="5" fill="none" strokeLinecap="round" />
      <path d="M54 98 v10 M66 98 v10" stroke="#e2e8f0" strokeWidth="1.8" strokeLinecap="round" />
      <Face look={l} open smile="M52 76 q8 7 16 0" />
      <path d="M37 60 q-2 -28 24 -28 q20 0 23 18 q-4 -2 -8 -1 q-6 -9 -18 -6 q-8 2 -12 8 q-4 2 -9 9 z" fill={l.hair} />
      <path d="M48 56 q3 -2 7 -1 M65 55 q4 -1 7 1" stroke={l.hair} strokeWidth="2" strokeLinecap="round" />
    </>
  ),
  dadi: (l) => (
    <>
      {/* Saree pallu over the shoulder */}
      <Shoulders color={l.cloth} />
      <path d="M18 120 q8 -24 30 -28 l-6 28 z" fill="#facc15" opacity="0.9" />
      <path d="M78 92 q18 4 24 28 h-20 z" fill="#be185d" />
      <Face look={l} smile="M53 77 q7 5 14 0" />
      {/* Grey hair with a bun */}
      <circle cx="60" cy="34" r="9" fill={l.hair} stroke="#cbd5e1" strokeWidth="1" />
      <path d="M38 62 q-2 -26 22 -26 q24 0 22 26 q-8 -14 -22 -14 q-14 0 -22 14 z" fill={l.hair} />
      <path d="M60 37 v10" stroke="#cbd5e1" strokeWidth="1.2" />
      {/* Round glasses */}
      <g stroke="#6b4f3a" strokeWidth="1.8" fill="rgba(255,255,255,0.18)">
        <circle cx="51" cy="64" r="7" />
        <circle cx="69" cy="64" r="7" />
        <path d="M58 64 h4" fill="none" />
      </g>
      <circle cx="60" cy="53" r="2" fill="#dc2626" />
    </>
  ),
};

export default function AgentPortrait({ id, className = "h-10 w-10", ring = false }) {
  const uid = useId().replace(/:/g, "");
  const look = LOOKS[id];
  if (!look) return null;
  return (
    <svg viewBox="0 0 120 120" className={`shrink-0 rounded-full ${ring ? "ring-2 ring-white/70" : ""} ${className}`}
      role="img" aria-hidden="true">
      <defs>
        <linearGradient id={`bg-${uid}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={look.bg[0]} />
          <stop offset="1" stopColor={look.bg[1]} />
        </linearGradient>
        <clipPath id={`c-${uid}`}><circle cx="60" cy="60" r="60" /></clipPath>
      </defs>
      <g clipPath={`url(#c-${uid})`}>
        <rect width="120" height="120" fill={`url(#bg-${uid})`} />
        <circle cx="60" cy="58" r="40" fill="#fff" opacity="0.12" />
        {PARTS[id](look)}
      </g>
    </svg>
  );
}
