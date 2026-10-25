import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { DailyVerse } from "@/components/SettingsDialog";
import { PlanBadge } from "@/components/settings/ConnectorsPanel";
import { toast } from "sonner";
import { BookOpen, ChevronDown, Clapperboard, CloudSun, Globe, Loader2, Lock, Sunrise, Trophy } from "lucide-react";

const LOOK = {
  auto_search: { icon: Globe, tile: "from-sky-500 to-indigo-500" },
  daily_verse: { icon: BookOpen, tile: "from-amber-400 to-orange-500" },
  weather: { icon: CloudSun, tile: "from-cyan-400 to-blue-500" },
  panchang: { icon: Sunrise, tile: "from-orange-400 to-rose-500" },
  cricket: { icon: Trophy, tile: "from-emerald-400 to-green-600" },
  video: { icon: Clapperboard, tile: "from-fuchsia-500 to-pink-500" },
};
const TRY = {
  weather: "Try: \"Will it rain in Mumbai tomorrow?\"",
  panchang: "Try: \"What's the tithi today?\" or \"When is Ekadashi?\"",
  cricket: "Try: \"India score?\"",
  auto_search: "Every answer starts with a web search.",
  video: "Try: \"Make a 10 second reel for my bakery\"",
};

/** Settings > Plugins: extra skills to switch on or off. */
export default function PluginsPanel({ onClose }) {
  const navigate = useNavigate();
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    api.get("/plugins").then(({ data }) => setItems(data.plugins)).catch((e) => { toast.error(formatApiError(e)); setItems([]); });
  }, []);

  const toggle = async (p, on) => {
    if (p.locked && on) { onClose(); navigate("/plans"); return; }
    setBusy(p.id);
    setItems((list) => list.map((x) => (x.id === p.id ? { ...x, on } : x)));
    try {
      const { data } = await api.put(`/plugins/${p.id}`, { on });
      setItems(data.plugins);
    } catch (e) {
      setItems((list) => list.map((x) => (x.id === p.id ? { ...x, on: !on } : x)));
      toast.error(formatApiError(e));
    } finally { setBusy(null); }
  };

  if (items === null) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>;

  const card = (p) => {
    const { icon: Icon, tile } = LOOK[p.id] || LOOK.weather;
    const expanded = open === p.id;
    return (
      <div key={p.id} className={`rounded-2xl border border-border bg-card transition-shadow ${expanded ? "shadow-[0_6px_24px_-12px_rgba(15,23,42,0.25)]" : ""} ${!p.ready ? "opacity-70" : ""}`}
        data-testid={`plugin-${p.id}`}>
        <div className="flex items-center gap-3.5 p-3.5">
          <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-sm ${tile}`}><Icon className="h-5 w-5" strokeWidth={2} /></span>
          <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setOpen(expanded ? null : p.id)} aria-expanded={expanded}>
            <span className="flex items-center gap-1.5 text-[14px] font-semibold">{p.name} <PlanBadge plan={p.plan} />
              <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} /></span>
            <span className="mt-0.5 block text-[12.5px] leading-snug text-muted-foreground">{p.blurb}</span>
          </button>
          {!p.ready ? <span className="shrink-0 rounded-full border border-border px-2.5 py-1 text-[12px] text-muted-foreground">Soon</span>
            : p.device ? <DailyVerse compact />
              : busy === p.id ? <Loader2 className="h-4 w-4 animate-spin text-primary" />
                : p.locked ? <button type="button" onClick={() => toggle(p, true)} className="flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[12px] text-muted-foreground hover:bg-surface">
                  <Lock className="h-3 w-3" /> Upgrade</button>
                  : <Switch checked={p.on} onCheckedChange={(on) => toggle(p, on)} aria-label={p.name} data-testid={`plugin-toggle-${p.id}`} />}
        </div>
        {expanded && (
          <div className="border-t border-border px-4 pb-4 pt-3">
            <ul className="space-y-1.5 text-[13px]">{p.does.map((d) => <li key={d} className="flex gap-2"><span className="text-primary">•</span>{d}</li>)}</ul>
            {TRY[p.id] && <p className="mt-2.5 text-xs text-muted-foreground">{TRY[p.id]}</p>}
          </div>
        )}
      </div>
    );
  };

  const on = items.filter((p) => p.on && !p.device);
  const rest = items.filter((p) => !p.on || p.device);
  return (
    <div data-testid="plugins-panel">
      <div className="mb-6 hidden sm:block">
        <h2 className="font-heading text-[22px] font-semibold tracking-tight">Plugins</h2>
        <p className="mt-1 text-[13.5px] text-muted-foreground">Extra skills you can switch on. Krish uses them only when they help.</p>
      </div>
      {on.length > 0 && <>
        <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Turned on</p>
        <div className="mb-6 grid gap-3 lg:grid-cols-2">{on.map(card)}</div>
      </>}
      <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">{on.length ? "More plugins" : "Plugins"}</p>
      <div className="grid gap-3 lg:grid-cols-2">{rest.map(card)}</div>
    </div>
  );
}
