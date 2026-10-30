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
  { id: "ananya", name: "Ananya", voice: "shimmer", gradient: "from-teal-500 to-emerald-600",
    tagline: "Life coach for stress, confidence and relationships", hello: "Hi, I'm Ananya. What's been on your mind lately?" },
  { id: "kabir", name: "Kabir", voice: "echo", gradient: "from-blue-600 to-sky-500",
    tagline: "Mentor for studies, career and big decisions", hello: "Hey, I'm Kabir. What are you working towards?" },
];

export const counselAgent = (id) => COUNSEL_AGENTS.find((a) => a.id === id) || null;

export function AgentAvatar({ agent, className = "h-8 w-8", speaking = false }) {
  return <AgentPortrait id={agent.id} className={`shadow-sm ${speaking ? "animate-pulse" : ""} ${className}`} />;
}
