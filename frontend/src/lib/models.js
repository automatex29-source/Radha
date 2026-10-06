import { Sparkles, Zap, Feather, BookOpen, Crown, Rocket, Eye } from "lucide-react";

// Krish names and icons for each model, so chats never show a raw model id. Labels match backend AVAILABLE_MODELS.
export const MODEL_INFO = {
  "gemini-3.5-flash-lite": { label: "Krish Spark", icon: Sparkles },
  "openai/gpt-oss-120b": { label: "Krish Turbo", icon: Zap },
  "openai/gpt-oss-20b": { label: "Krish Mini", icon: Feather },
  "cerebras/gpt-oss-120b": { label: "Krish Titan", icon: BookOpen },
  "claude-sonnet-5-5": { label: "Krish Ultra", icon: Crown },
  "claude-haiku-4-5-20251001": { label: "Krish Swift", icon: Rocket },
  "gpt-5.4": { label: "Krish Vision", icon: Eye },
};

export const modelIcon = (id) => MODEL_INFO[id]?.icon || Sparkles;
export const modelLabel = (id) => MODEL_INFO[id]?.label || "Krish AI";
