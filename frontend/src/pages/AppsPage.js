import { useEffect, useState } from "react";
import PageHero from "@/components/PageHero";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { AppWindow, Loader2, Globe, Trash2, Sparkles, Wand2, Github } from "lucide-react";

// Tap an idea to fill the box. The builder picks the matching starter itself.
const IDEAS = [
  { label: "Habit tracker", prompt: "A habit tracker with daily check-ins, streaks and a weekly chart" },
  { label: "Restaurant site", prompt: "A restaurant website with a menu, online ordering and table booking" },
  { label: "Salon booking", prompt: "A booking app for a beauty salon: pick a service, a day and a time slot" },
  { label: "Portfolio", prompt: "A personal portfolio for a designer with projects, skills and a contact form" },
  { label: "AI chatbot", prompt: "An AI chatbot assistant with suggested questions and chat history" },
  { label: "Sales dashboard", prompt: "A sales dashboard with stats, charts and a recent orders table" },
  { label: "Online shop", prompt: "An online shop for handmade candles with a cart and checkout" },
  { label: "Snake game", prompt: "A neon snake game with a high score and sound effects" },
];

// The kit's design styles (backend/design_themes.py). "Surprise me" lets Krish pick one that suits the app.
const STYLES = [
  { id: "", label: "Surprise me", swatch: "conic-gradient(from 0deg, #7c3aed, #06b6d4, #f472b6, #facc15, #7c3aed)" },
  { id: "glass", label: "Glass", swatch: "linear-gradient(135deg, #c4b5fd, #a5f3fc)" },
  { id: "liquid", label: "Liquid glass", swatch: "radial-gradient(circle at 30% 25%, #fff, #0a84ff 45%, #ff375f)" },
  { id: "aurora", label: "Aurora", swatch: "radial-gradient(circle at 30% 30%, #a78bfa, #22d3ee 55%, #07060d)" },
  { id: "bento", label: "Bento", swatch: "linear-gradient(135deg, #f5f5f7 50%, #0a84ff 50%)" },
  { id: "bold", label: "Bold", swatch: "linear-gradient(135deg, #ffd400 50%, #ff5c00 50%)" },
  { id: "luxury", label: "Luxury", swatch: "linear-gradient(135deg, #f7f3ec 50%, #a67c37 50%)" },
  { id: "minimal", label: "Minimal", swatch: "linear-gradient(135deg, #ffffff 50%, #111111 50%)" },
  { id: "playful", label: "Playful", swatch: "linear-gradient(135deg, #ff4fa3, #7c5cff)" },
  { id: "neon", label: "Neon", swatch: "linear-gradient(135deg, #05050a 40%, #00f0ff 70%, #ff2bd6)" },
  { id: "clay", label: "Clay", swatch: "radial-gradient(circle at 35% 30%, #fff, #b9b0ff 50%, #ff9f6b)" },
  { id: "sunset", label: "Sunset", swatch: "linear-gradient(180deg, #4a1640, #c2366d 50%, #ff8f4a)" },
];

// "A habit tracker with daily check-ins" -> "Habit tracker"
function appName(text) {
  const words = text.replace(/[\r\n]+/g, " ").replace(/^(please\s+)?(make|build|create|design|i want|give me)\s+(me\s+)?(an?\s+|the\s+)?/i, "")
    .split(/\s+/).slice(0, 4).join(" ").replace(/[^\p{L}\p{N}\s&'-]/gu, "").trim();
  const name = words.split(/\s+(with|for|that|which|where|and)\s+/i)[0] || words || "My app";
  return (name.charAt(0).toUpperCase() + name.slice(1)).slice(0, 40);
}

function NewAppBox({ busy, onCreate }) {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [style, setStyle] = useState("");
  const [boosting, setBoosting] = useState(false);
  const build = () => {
    const picked = STYLES.find((s) => s.id === style);
    onCreate(style ? `${text.trim()}\n\nDesign style: ${picked.label}.` : text);
  };
  const [repo, setRepo] = useState(null); // null: closed; a string: the GitHub link being typed
  const [importing, setImporting] = useState(false);
  const importRepo = async (e) => {
    e.preventDefault();
    if (!repo?.trim() || importing) return;
    setImporting(true);
    try {
      const { data } = await api.post("/apps/import", { repo: repo.trim() });
      toast.success(`Opened ${data.name}`);
      navigate(`/apps/${data.id}`);
    } catch (err) {
      toast.error(formatApiError(err));
      setImporting(false);
    }
  };
  const boost = async () => {
    if (!text.trim() || boosting) return;
    setBoosting(true);
    try {
      const { data } = await api.post("/apps/boost", { text });
      setText(data.text);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBoosting(false);
    }
  };
  return (
    <section className="mt-6 rounded-2xl border border-border bg-card p-3 shadow-sm focus-within:border-primary/60" data-testid="new-app-box">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} data-testid="new-app-input" autoFocus
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !window.matchMedia?.("(pointer: coarse)").matches) { e.preventDefault(); build(); } }}
        placeholder="Describe the app you want, like “a booking app for my salon”…"
        className="radha-scroll w-full resize-none bg-transparent px-2 py-1 text-base focus:outline-none" />
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={boost} disabled={!text.trim() || boosting} data-testid="new-app-boost"
          title="Turn a short idea into a detailed brief" className="gap-1.5 text-muted-foreground">
          {boosting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />} Improve prompt
        </Button>
        <Button onClick={build} disabled={!text.trim() || busy} data-testid="create-app-button" className="ml-auto gap-1.5">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Build it
        </Button>
      </div>
      <div className="mt-3 flex items-center gap-1.5 overflow-x-auto border-t border-border px-1 pt-3 radha-scroll" role="radiogroup" aria-label="Design style" data-testid="new-app-styles">
        <span className="shrink-0 pr-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Style</span>
        {STYLES.map((s) => (
          <button key={s.label} type="button" role="radio" aria-checked={style === s.id} onClick={() => setStyle(s.id)} data-testid={`style-${s.id || "auto"}`}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${style === s.id ? "border-primary bg-primary/10 text-foreground" : "border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground"}`}>
            <span className="h-3.5 w-3.5 rounded-full border border-border" style={{ background: s.swatch }} /> {s.label}
          </button>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 px-1">
        {IDEAS.map((i) => (
          <button key={i.label} onClick={() => setText(i.prompt)} data-testid={`idea-${i.label}`}
            className="rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground">
            {i.label}
          </button>
        ))}
      </div>
      <div className="mt-2 px-1">
        {repo === null ? (
          <button onClick={() => setRepo("")} data-testid="import-github-open" className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
            <Github className="h-3.5 w-3.5" /> Or open a project from GitHub
          </button>
        ) : (
          <form onSubmit={importRepo} className="flex items-center gap-2" data-testid="import-github">
            <Github className="h-4 w-4 shrink-0 text-muted-foreground" />
            <input autoFocus value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="https://github.com/owner/repo"
              data-testid="import-github-input" className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm focus:outline-none focus:border-primary/60" />
            <Button size="sm" type="submit" disabled={!repo.trim() || importing} data-testid="import-github-button">
              {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : "Open"}
            </Button>
          </form>
        )}
      </div>
    </section>
  );
}

export default function AppsPage() {
  const navigate = useNavigate();
  const [apps, setApps] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/apps");
      setApps(data);
    } catch (e) {
      toast.error(formatApiError(e));
      setApps([]);
    }
  };

  useEffect(() => { load(); }, []);

  // No form: the request becomes the app (its name comes from the first words), and the builder starts on it.
  const create = async (prompt) => {
    const text = prompt.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/apps", { name: appName(text), description: text.slice(0, 500), template: "blank" });
      navigate(`/apps/${data.id}`, { state: { prompt: text } });
    } catch (e) {
      toast.error(formatApiError(e));
      setBusy(false);
    }
  };

  const remove = async (app) => {
    if (!window.confirm(`Delete “${app.name}” and its history? Its published site goes offline too.`)) return;
    try {
      await api.delete(`/apps/${app.id}`);
      setApps((list) => list.filter((a) => a.id !== app.id));
      toast.success("App deleted");
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
          <PageHero scene="apps" icon={AppWindow} title="Apps" subtitle="Describe an app and Krish AI builds it, with live preview, tests, version history and one-click publishing." />

          <NewAppBox busy={busy} onCreate={create} />

          {apps === null ? (
            <div className="mt-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : apps.length === 0 ? (
            <div className="mt-16 flex flex-col items-center text-center" data-testid="apps-empty">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-strong"><AppWindow className="h-7 w-7 text-primary" /></div>
              <p className="mt-4 font-semibold">No apps yet</p>
              <p className="mt-1 max-w-sm text-sm text-muted-foreground">Describe one above, or tap an idea, and Krish AI builds it in seconds.</p>
            </div>
          ) : (
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {apps.map((a) => (
                <div key={a.id} className="radha-lift group relative rounded-xl border border-border bg-card p-5 hover:border-primary/50" data-testid={`app-card-${a.id}`}>
                  <button onClick={() => navigate(`/apps/${a.id}`)} className="block w-full text-left">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-strong text-primary"><AppWindow className="h-5 w-5" /></div>
                    <p className="mt-3 font-semibold">{a.name}</p>
                    <p className="mt-1 line-clamp-2 min-h-[2.5rem] text-sm text-muted-foreground">{a.description || "No description"}</p>
                    <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
                      {a.published && <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-600 dark:text-emerald-400"><Globe className="h-3 w-3" /> Live</span>}
                      <span>Updated {new Date(a.updatedAt).toLocaleString()}</span>
                    </div>
                  </button>
                  <button onClick={() => remove(a)} title="Delete app" data-testid={`delete-app-${a.id}`}
                    className="absolute right-2 top-2 rounded-md p-2.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
