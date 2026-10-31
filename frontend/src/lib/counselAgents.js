import AgentPortrait from "@/components/AgentPortrait";

// The Counsellor is Krish Robo: a friend people can chat or have a voice call with. Its personality lives in
// backend/counsellor.py (PROMPT, AGENTS); here are its look, tagline and the voice that speaks for it.
export const COUNSEL_AGENTS = [
  { id: "krish_robo", name: "Krish Robo", voice: "echo", gradient: "from-indigo-500 to-violet-600",
    tagline: "Your robot buddy for stress, studies, plans and everything in between", hello: "Beep boop, hi! I'm Krish Robo. What's on your mind?" },
];

export const KRISH_ROBO = COUNSEL_AGENTS[0];

export const counselAgent = (id) => COUNSEL_AGENTS.find((a) => a.id === id) || null;

export function AgentAvatar({ agent, className = "h-8 w-8", speaking = false }) {
  return <AgentPortrait id={agent.id} className={`shadow-sm ${speaking ? "animate-pulse" : ""} ${className}`} />;
}
