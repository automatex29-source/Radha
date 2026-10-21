import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

/** "Unlock Pro" (or "Unlock Max" for Pro users) in the chat's top bar; opens the Plans page. Hidden for Max users. */
export default function UpgradeButton() {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  if (user?.plan === "max") return null;
  const next = user?.plan === "pro" ? "Max" : "Pro";
  return (
    <button onClick={() => navigate("/plans")} data-testid="header-upgrade" aria-label={`Unlock ${next}`}
      className="krish-unlock flex h-[34px] shrink-0 items-center gap-1.5 rounded-full px-3 text-[12.5px] font-semibold text-white transition-shadow sm:h-9 sm:px-3.5 sm:text-[13px]">
      <Sparkles className="h-3.5 w-3.5" /> Unlock {next}
    </button>
  );
}
