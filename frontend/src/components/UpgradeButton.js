import { useNavigate } from "react-router-dom";
import { Crown } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

/** Small "Upgrade" link in the chat's top bar that opens the Plans page. Hidden for Max users. */
export default function UpgradeButton() {
  const navigate = useNavigate();
  const { user } = useAuth() || {};
  if (user?.plan === "max") return null;
  return (
    <button onClick={() => navigate("/plans")} data-testid="header-upgrade" aria-label="Upgrade"
      className="flex h-8 shrink-0 items-center gap-1 rounded-full border border-border bg-card/70 px-2.5 text-[11px] font-medium text-foreground/80 transition-colors hover:border-primary/40 hover:text-primary">
      <Crown className="h-3.5 w-3.5 text-primary" /> Upgrade
    </button>
  );
}
