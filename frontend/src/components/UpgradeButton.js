import { useNavigate } from "react-router-dom";
import { Crown } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const GRADIENT = "bg-gradient-to-r from-amber-400 via-orange-500 to-pink-500 text-white shadow-[0_6px_18px_rgba(249,115,22,0.35)]";

/** "Upgrade" pill that opens the Plans page. Hidden for Max users (nothing to upgrade to).
 *  variant: "pill" (chat header), "card" (sidebar), "rail" (desktop side rail). */
export default function UpgradeButton({ variant = "pill" }) {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  if (user?.plan === "max") return null;
  const go = () => navigate("/plans");

  if (variant === "rail") {
    return (
      <button onClick={go} data-testid="nav-upgrade" title="Upgrade" aria-label="Upgrade"
        className={`mb-2.5 flex h-11 w-11 items-center justify-center rounded-2xl transition-transform hover:scale-105 ${GRADIENT}`}>
        <Crown className="h-5 w-5" />
      </button>
    );
  }
  if (variant === "card") {
    return (
      <button onClick={go} data-testid="sidebar-upgrade"
        className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition-transform hover:scale-[1.01] ${GRADIENT}`}>
        <Crown className="h-5 w-5 shrink-0" />
        <span className="min-w-0 leading-tight">
          <span className="block text-sm font-bold">Upgrade to {user?.plan === "pro" ? "Max" : "Pro"}</span>
          <span className="block truncate text-[11px] text-white/90">More builds, pictures and publishing</span>
        </span>
      </button>
    );
  }
  return (
    <button onClick={go} data-testid="header-upgrade" aria-label="Upgrade"
      className={`flex h-9 shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-bold transition-transform hover:scale-105 sm:h-10 sm:px-4 ${GRADIENT}`}>
      <Crown className="h-4 w-4" /> Upgrade
    </button>
  );
}
