// The Counsellor's portrait (see lib/counselAgents.js), in public/agents/.
// `face` is where the face sits in the picture (x%, y%), for round crops; `bg` matches its colours.
const LOOKS = {
  krish_robo: { image: "/agents/krish_robo.webp", face: [50, 40], bg: ["#0b0a24", "#6d4bff"] },
};

/** The two background colours of an agent's portrait, for screens that match it. */
export const portraitColors = (id) => LOOKS[id]?.bg || ["#4f46e5", "#7c3aed"];

/** The agent's picture filling a box (cards, call backgrounds). */
export function AgentArt({ id, className = "" }) {
  const look = LOOKS[id];
  if (!look) return null;
  return <img src={look.image} alt="" loading="lazy" className={`h-full w-full object-cover ${className}`}
    style={{ objectPosition: `50% ${Math.max(0, look.face[1] - 12)}%` }} />;
}

/** A round crop of the agent's picture, centred on the face. */
export default function AgentPortrait({ id, className = "h-10 w-10", ring = false }) {
  const look = LOOKS[id];
  if (!look) return null;
  return (
    <span role="img" aria-hidden="true"
      className={`block shrink-0 rounded-full bg-no-repeat ${ring ? "ring-2 ring-white/70" : ""} ${className}`}
      style={{ backgroundImage: `url(${look.image})`, backgroundSize: "185%",
        backgroundPosition: `${look.face[0]}% ${look.face[1]}%`, backgroundColor: look.bg[0] }} />
  );
}
