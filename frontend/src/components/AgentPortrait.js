import { useId } from "react";

// Portraits of the Pro Counsellor agents (see lib/counselAgents.js): paintings in public/agents/ for the
// divine ones, and a drawn 120x120 SVG for the guides. `face` is where the face sits in a painting (x%, y%).
const LOOKS = {
  krishna: { image: "/agents/krishna.webp", face: [56, 22], bg: ["#1e3a8a", "#6d28d9"] },
  bal_krishna: { image: "/agents/bal_krishna.webp", face: [55, 33], bg: ["#1e3a8a", "#0ea5e9"] },
  radha: { image: "/agents/radha.webp", face: [50, 40], bg: ["#1e3a8a", "#b45309"] },
  hanuman: { image: "/agents/hanuman.webp", face: [42, 26], bg: ["#c2410c", "#f59e0b"] },
  ananya: { bg: ["#0f766e", "#5eead4"], skin: "#e8b48f", skinShade: "#d49c76", hair: "#2a1a14", cloth: "#0d9488" },
  kabir: { bg: ["#1e3a8a", "#60a5fa"], skin: "#c98d64", skinShade: "#b47952", hair: "#1c1410", cloth: "#1e293b" },
};

/** The two background colours of an agent's portrait, for screens that match it. */
export const portraitColors = (id) => LOOKS[id]?.bg || ["#4f46e5", "#7c3aed"];

/** The agent's painting, when it has one (shown full size on cards and behind a call). */
export const portraitImage = (id) => LOOKS[id]?.image || null;

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

function Face({ look, open = false, smile = "M53 77 q7 6 14 0" }) {
  return (
    <g>
      <rect x="53" y="78" width="14" height="16" rx="6" fill={look.skinShade} />
      <ellipse cx="38" cy="66" rx="4" ry="6" fill={look.skinShade} />
      <ellipse cx="82" cy="66" rx="4" ry="6" fill={look.skinShade} />
      <ellipse cx="60" cy="64" rx="20" ry="24" fill={look.skin} />
      <Eyes open={open} />
      <circle cx="45" cy="72" r="4" fill="#fb7185" opacity="0.35" />
      <circle cx="75" cy="72" r="4" fill="#fb7185" opacity="0.35" />
      <path d={smile} stroke="#7a2e2e" strokeWidth="2.2" strokeLinecap="round" fill="none" />
    </g>
  );
}

function Shoulders({ color }) {
  return <path d="M18 120 q4 -28 42 -30 q38 2 42 30 z" fill={color} />;
}

const PARTS = {
  ananya: (l) => (
    <>
      {/* Long hair behind the shoulders */}
      <path d="M34 62 q-6 34 2 52 h48 q8 -18 2 -52 z" fill={l.hair} />
      <Shoulders color={l.cloth} />
      <path d="M48 92 q12 14 24 0" fill="#99f6e4" opacity="0.55" />
      <path d="M48 92 q12 14 24 0" stroke="#fde68a" strokeWidth="1.6" fill="none" />
      <Face look={l} open smile="M53 77 q7 5 14 0" />
      {/* Lashes */}
      <path d="M46 61 l-2 -2 M74 61 l2 -2" stroke="#1f1a17" strokeWidth="1.6" strokeLinecap="round" />
      {/* Side-parted hair */}
      <path d="M38 64 q-4 -32 24 -30 q22 2 20 30 q-6 -14 -16 -20 q-8 10 -28 20 z" fill={l.hair} />
      <circle cx="38" cy="72" r="1.8" fill="#fde68a" />
      <circle cx="82" cy="72" r="1.8" fill="#fde68a" />
      <circle cx="60" cy="54" r="1.4" fill="#be123c" />
    </>
  ),
  kabir: (l) => (
    <>
      <Shoulders color={l.cloth} />
      {/* Shirt collar */}
      <path d="M46 90 l14 12 l14 -12 l-4 14 h-20 z" fill="#f8fafc" />
      <path d="M60 102 v18" stroke="#cbd5e1" strokeWidth="1.2" />
      <Face look={l} open smile="M53 79 q7 5 14 0" />
      {/* Short beard */}
      <path d="M41 70 q2 20 19 22 q17 -2 19 -22 q-4 10 -19 11 q-15 -1 -19 -11 z" fill={l.hair} opacity="0.85" />
      <path d="M53 75 q7 -3 14 0" stroke={l.hair} strokeWidth="2.4" strokeLinecap="round" fill="none" />
      {/* Brows and neat hair */}
      <path d="M45 57 q5 -2 10 0 M65 57 q5 -2 10 0" stroke={l.hair} strokeWidth="2.2" strokeLinecap="round" fill="none" />
      <path d="M38 58 q-2 -26 24 -26 q22 2 20 24 q-4 -8 -10 -10 q-10 -6 -22 0 q-8 4 -12 12 z" fill={l.hair} />
    </>
  ),
};

/** The agent's art filling a box (cards, call backgrounds): the painting, or the drawn portrait. */
export function AgentArt({ id, className = "" }) {
  const look = LOOKS[id];
  if (!look) return null;
  if (look.image) {
    return <img src={look.image} alt="" loading="lazy" className={`h-full w-full object-cover ${className}`}
      style={{ objectPosition: `50% ${Math.max(0, look.face[1] - 12)}%` }} />;
  }
  return <AgentPortrait id={id} square className={`h-full w-full ${className}`} />;
}

export default function AgentPortrait({ id, className = "h-10 w-10", ring = false, square = false }) {
  const uid = useId().replace(/:/g, "");
  const look = LOOKS[id];
  if (!look) return null;
  if (look.image && !square) {
    // A round crop of the painting, centred on the face.
    return (
      <span role="img" aria-hidden="true"
        className={`block shrink-0 rounded-full bg-no-repeat ${ring ? "ring-2 ring-white/70" : ""} ${className}`}
        style={{ backgroundImage: `url(${look.image})`, backgroundSize: "185%",
          backgroundPosition: `${look.face[0]}% ${look.face[1]}%`, backgroundColor: look.bg[0] }} />
    );
  }
  return (
    <svg viewBox={square ? "10 0 100 120" : "0 0 120 120"} preserveAspectRatio="xMidYMid slice"
      className={`shrink-0 ${square ? "" : "rounded-full"} ${ring ? "ring-2 ring-white/70" : ""} ${className}`}
      role="img" aria-hidden="true">
      <defs>
        <linearGradient id={`bg-${uid}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={look.bg[0]} />
          <stop offset="1" stopColor={look.bg[1]} />
        </linearGradient>
        <clipPath id={`c-${uid}`}>{square ? <rect width="120" height="120" /> : <circle cx="60" cy="60" r="60" />}</clipPath>
      </defs>
      <g clipPath={`url(#c-${uid})`}>
        <rect width="120" height="120" fill={`url(#bg-${uid})`} />
        <circle cx="60" cy="58" r="40" fill="#fff" opacity="0.12" />
        {PARTS[id](look)}
      </g>
    </svg>
  );
}
