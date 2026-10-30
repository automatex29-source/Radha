import AgentPortrait from "@/components/AgentPortrait";

// Pro Counsellor agents: companions people can chat or have a voice call with. Their personalities live in
// backend/counsellor.py (AGENTS); here are their looks, taglines and the voice that speaks for them.
export const COUNSEL_AGENTS = [
  { id: "krishna", name: "Krishna", voice: "onyx", gradient: "from-sky-500 to-indigo-600",
    tagline: "Calm wisdom for big questions and hard choices", hello: "I'm here, dear friend. What's on your mind?" },
  { id: "bal_krishna", name: "Bal Krishna", voice: "coral", gradient: "from-amber-400 to-orange-500",
    tagline: "Little Kanha: playful, sweet, cheers you up", hello: "Hehe, you came! Want some makhan and a smile?" },
  { id: "radha", name: "Radha", voice: "nova", gradient: "from-pink-500 to-rose-500",
    tagline: "Gentle love for heartbreak and loneliness", hello: "Come, sit with me. Tell me what your heart feels." },
  { id: "hanuman", name: "Hanuman", voice: "ballad", gradient: "from-orange-500 to-red-600",
    tagline: "Courage and strength when you feel weak", hello: "Jai Shri Ram! Tell me, what feels too big right now?" },
  { id: "vivekananda", name: "Swami Vivekananda", voice: "echo", gradient: "from-amber-500 to-orange-600",
    tagline: "Self-belief, focus and fire for your goals", hello: "Arise, awake! Tell me, what goal is in your heart?" },
];

export const counselAgent = (id) => COUNSEL_AGENTS.find((a) => a.id === id) || null;

export function AgentAvatar({ agent, className = "h-8 w-8", speaking = false }) {
  return <AgentPortrait id={agent.id} className={`shadow-sm ${speaking ? "animate-pulse" : ""} ${className}`} />;
}
