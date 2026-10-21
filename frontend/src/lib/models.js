import { Sparkles, Crown, Rocket, Eye } from "lucide-react";

// Krish names and icons for each model, so chats never show a raw model id. Labels match backend AVAILABLE_MODELS.
// The free models are one model, Krish Basic, that picks the right one for each question, so replies from any of
// them (and from older chats that picked one) show as Krish Basic.
const KRISH = { label: "Krish Basic", icon: Sparkles };
export const MODEL_INFO = {
  "krish-auto": KRISH,
  "gemini-3.5-flash-lite": KRISH,
  "openai/gpt-oss-120b": KRISH,
  "openai/gpt-oss-20b": KRISH,
  "cerebras/gpt-oss-120b": KRISH,
  "claude-sonnet-5-5": { label: "Krish Ultra", icon: Crown },
  "claude-haiku-4-5-20251001": { label: "Krish Swift", icon: Rocket },
  "gpt-5.4": { label: "Krish Vision", icon: Eye },
};

// Krish Coder (OpenRouter's free coding model) answers coding questions inside Krish AI.
const infoFor = (id) => MODEL_INFO[id] || (id?.startsWith("openrouter/") ? KRISH : null);

export const modelIcon = (id) => infoFor(id)?.icon || Sparkles;
export const modelLabel = (id) => infoFor(id)?.label || "Krish AI";
// The menu choice for a chat's saved model: a free model saved by an older chat is Krish Basic now.
export const menuModel = (id) => (MODEL_INFO[id] && MODEL_INFO[id] !== KRISH ? id : "krish-auto");
