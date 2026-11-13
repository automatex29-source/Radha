import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { AppWindow, Loader2, Trash2, Wand2, Github, ArrowUp, ChevronRight } from "lucide-react";

// Tap a starter to fill the box with a full brief: real jobs Indian businesses and people run every day.
const STARTERS = [
  { title: "Shop with WhatsApp orders", text: "Customers browse, add to cart and order on WhatsApp",
    prompt: "An online store for my kirana shop. Customers browse items by category with photos and prices in ₹, add them to a cart and place the order on WhatsApp with one tap. I can log in as the owner to add items, change prices and stock, and see today's orders." },
  { title: "Clinic appointments", text: "Patients book a slot, the doctor sees the day's list",
    prompt: "A website for my clinic. Patients see the doctor's timings and fees, pick a free time slot and book with their name and phone number. The doctor logs in to see today's appointments, mark patients as seen and block days off." },
  { title: "Coaching class manager", text: "Students, batches, attendance and monthly fees",
    prompt: "An app to run my coaching centre. I add students to batches, mark daily attendance, and track monthly fees as paid or due with reminders. Parents log in to see their child's attendance and fee status." },
  { title: "GST invoice maker", text: "Bills with GST split, saved customers, PDF download",
    prompt: "A GST invoice maker for my small business. I save my business details and customers, add items with HSN code, quantity and rate, and it works out CGST, SGST or IGST and the total in ₹. Each invoice gets a number and downloads as a PDF." },
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
  const [boosting, setBoosting] = useState(false);
  // Krish picks the design that suits each app (backend/design_themes.py); a style named in the text still wins.
  const build = () => onCreate(text);
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
  const ready = text.trim() && !busy;
  return (
    <section data-testid="new-app-box">
      <div className="rounded-2xl border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,0.04),0_8px_24px_-12px_rgba(0,0,0,0.12)] transition-colors focus-within:border-foreground/25">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} data-testid="new-app-input" autoFocus
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !window.matchMedia?.("(pointer: coarse)").matches) { e.preventDefault(); if (ready) build(); } }}
          placeholder="Describe the app you want to build…"
          className="radha-scroll block min-h-[96px] w-full resize-none bg-transparent px-4 pt-4 text-[15px] leading-relaxed placeholder:text-muted-foreground/70 focus:outline-none" />
        <div className="flex items-center gap-1 px-2.5 pb-2.5">
          <button type="button" onClick={boost} disabled={!text.trim() || boosting} data-testid="new-app-boost"
            title="Turn a short idea into a detailed brief"
            className="flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-50">
            {boosting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />} Improve prompt
          </button>
          <button type="button" onClick={() => setRepo(repo === null ? "" : null)} data-testid="import-github-open"
            className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs transition-colors hover:bg-muted hover:text-foreground ${repo !== null ? "bg-muted text-foreground" : "text-muted-foreground"}`}>
            <Github className="h-3.5 w-3.5" /> <span className="max-sm:hidden">Open from GitHub</span><span className="sm:hidden">GitHub</span>
          </button>
          <button type="button" onClick={build} disabled={!ready} data-testid="create-app-button" aria-label="Build it" title="Build it"
            className="ml-auto flex h-8 items-center gap-1.5 rounded-lg bg-foreground pl-3 pr-2.5 text-xs font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-30">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <>Build it <ArrowUp className="h-3.5 w-3.5" /></>}
          </button>
        </div>
        {repo !== null && (
          <form onSubmit={importRepo} className="flex items-center gap-2 border-t border-border px-3 py-2.5" data-testid="import-github">
            <Github className="h-4 w-4 shrink-0 text-muted-foreground" />
            <input autoFocus value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="https://github.com/owner/repo"
              data-testid="import-github-input" className="min-w-0 flex-1 bg-transparent py-1 text-sm focus:outline-none" />
            <button type="submit" disabled={!repo.trim() || importing} data-testid="import-github-button"
              className="flex h-7 items-center rounded-md border border-border px-2.5 text-xs font-medium hover:bg-muted disabled:opacity-40">
              {importing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Open"}
            </button>
          </form>
        )}
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2" data-testid="new-app-starters">
        {STARTERS.map((i) => (
          <button key={i.title} onClick={() => setText(i.prompt)} data-testid={`starter-${i.title}`}
            className="rounded-xl border border-border px-3.5 py-2.5 text-left transition-colors hover:bg-muted/60">
            <span className="block text-sm font-medium">{i.title}</span>
            <span className="block text-xs text-muted-foreground">{i.text}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function ago(when) {
  const s = Math.max(0, (Date.now() - new Date(when).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  return new Date(when).toLocaleDateString();
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
    <div className="flex h-dvh w-full overflow-hidden bg-background max-md:flex-col">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 pb-16 pt-12 sm:px-6 sm:pt-[12vh]">
          <header className="mb-6 text-center">
            <h1 className="text-[28px] font-semibold tracking-tight sm:text-[32px]" data-testid="apps-title">What do you want to build?</h1>
            <p className="mt-2 text-sm text-muted-foreground">Krish AI writes the app, tests it and designs it for you. Preview, version history and publishing are built in.</p>
          </header>

          <NewAppBox busy={busy} onCreate={create} />

          <div className="mt-14">
            <div className="mb-2 flex items-baseline justify-between px-1">
              <h2 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Your apps</h2>
              {apps?.length > 0 && <span className="text-xs text-muted-foreground">{apps.length}</span>}
            </div>
            {apps === null ? (
              <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
            ) : apps.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-6 py-10 text-center" data-testid="apps-empty">
                <p className="text-sm font-medium">No apps yet</p>
                <p className="mt-1 text-sm text-muted-foreground">Describe one above, or start from one of the ideas, and Krish AI builds it in seconds.</p>
              </div>
            ) : (
              <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
                {apps.map((a) => (
                  <li key={a.id} className="group relative" data-testid={`app-card-${a.id}`}>
                    <button onClick={() => navigate(`/apps/${a.id}`)} className="flex w-full items-center gap-3 px-4 py-3 pr-12 text-left transition-colors hover:bg-muted/60">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-muted-foreground"><AppWindow className="h-4 w-4" /></span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium">{a.name}</span>
                          {a.published && <span className="flex shrink-0 items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />Live</span>}
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">{a.description || "No description"}</span>
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground max-sm:hidden">{ago(a.updatedAt)}</span>
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/60 group-hover:hidden max-sm:hidden" />
                    </button>
                    <button onClick={() => remove(a)} title="Delete app" aria-label={`Delete ${a.name}`} data-testid={`delete-app-${a.id}`}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-2 text-muted-foreground opacity-0 transition-opacity hover:text-destructive focus:opacity-100 group-hover:opacity-100 max-md:opacity-100">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
