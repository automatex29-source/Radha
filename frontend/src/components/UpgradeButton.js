import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

/** Small "Upgrade" pill in the chat's top bar that opens the Plans page. Hidden for Max users. */
export default function UpgradeButton() {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  if (user?.plan === "max") return null;
  return (
    <button onClick={() => navigate("/plans")} data-testid="header-upgrade" aria-label="Upgrade"
      className="flex h-8 shrink-0 items-center gap-1.5 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-3.5 text-[13px] font-semibold text-white shadow-[0_4px_14px_rgba(99,102,241,0.35)] transition-all hover:shadow-[0_6px_18px_rgba(99,102,241,0.45)] hover:brightness-110 active:scale-[0.98]">
      <Sparkles className="h-3.5 w-3.5" /> Upgrade
    </button>
  );
}
