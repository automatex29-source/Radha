import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Plus, Presentation, Sparkles, Trash2, Wand2, X, ImageIcon } from "lucide-react";
import { ScaledSlide, findTheme, useDeckThemes } from "@/components/deck/Slide";

const EXAMPLES = [
  "Pitch deck for a food delivery startup in India",
  "Climate change explained for school students",
  "Quarterly sales review for a small business",
  "How AI is changing healthcare",
];
const COUNTS = [5, 8, 10, 12, 15];
const DENSITIES = [
  { id: "brief", label: "Brief" },
  { id: "medium", label: "Medium" },
  { id: "detailed", label: "Detailed" },
];

const PREVIEW_SLIDE = (title) => ({ layout: "cover", title: title || "Your title", subtitle: "A short, catchy subtitle" });

function Chip({ active, onClick, children, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
        active ? "border-primary bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground"}`}>
      {children}
    </button>
  );
}

export default function DecksPage() {
  const navigate = useNavigate();
  const themes = useDeckThemes();
  const [decks, setDecks] = useState(null);
  const [step, setStep] = useState("prompt"); // prompt | outline
  const [prompt, setPrompt] = useState("");
  const [count, setCount] = useState(8);
  const [density, setDensity] = useState("medium");
  const [images, setImages] = useState(true);
  const [title, setTitle] = useState("");
  const [outline, setOutline] = useState([]);
  const [theme, setTheme] = useState("aurora");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/decks").then(({ data }) => setDecks(data)).catch((e) => { toast.error(formatApiError(e)); setDecks([]); });
  }, []);

  const makeOutline = async () => {
    if (prompt.trim().length < 2) return;
    setBusy(true);
    try {
      const { data } = await api.post("/decks/outline", { prompt, slides: count });
      setTitle(data.title);
      setOutline(data.outline.map((s) => ({ title: s.title, points: s.points.join("\n") })));
      setStep("outline");
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    const clean = outline.filter((s) => s.title.trim())
      .map((s) => ({ title: s.title.trim(), points: s.points.split("\n").map((p) => p.trim()).filter(Boolean) }));
    if (!clean.length) return toast.error("Add at least one slide");
    setBusy(true);
    try {
      const { data } = await api.post("/decks", { prompt, title, outline: clean, theme, density, images });
      navigate(`/decks/${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
      setBusy(false);
    }
  };

  const setSlide = (i, patch) => setOutline((o) => o.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  const remove = async (deck) => {
    if (!window.confirm(`Delete “${deck.title}”?`)) return;
    try {
      await api.delete(`/decks/${deck.id}`);
      setDecks((list) => list.filter((d) => d.id !== deck.id));
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
          {step === "prompt" ? (
            <section className="mx-auto max-w-3xl text-center" data-testid="deck-create">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Presentation className="h-6 w-6" />
              </div>
              <h1 className="radha-heading-gradient mt-4 text-3xl font-extrabold tracking-tighter sm:text-4xl">Presentations</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Type a topic. Krish AI writes the outline, designs the slides, and you download a real PowerPoint.
              </p>
              <div className="mt-6 rounded-2xl border border-border bg-card p-3 text-left shadow-sm">
                <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} data-testid="deck-prompt"
                  placeholder="What is your presentation about? You can also paste notes or an article."
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) makeOutline(); }}
                  className="resize-none border-0 bg-transparent text-base shadow-none focus-visible:ring-0" />
                <div className="flex flex-wrap items-center gap-2 border-t border-border px-1 pt-3">
                  <span className="text-xs text-muted-foreground">Slides</span>
                  {COUNTS.map((n) => <Chip key={n} active={count === n} onClick={() => setCount(n)} testid={`deck-count-${n}`}>{n}</Chip>)}
                  <span className="ml-2 text-xs text-muted-foreground">Text</span>
                  {DENSITIES.map((d) => <Chip key={d.id} active={density === d.id} onClick={() => setDensity(d.id)}>{d.label}</Chip>)}
                  <Chip active={images} onClick={() => setImages((v) => !v)}>
                    <span className="inline-flex items-center gap-1"><ImageIcon className="h-3 w-3" /> Pictures {images ? "on" : "off"}</span>
                  </Chip>
                  <Button onClick={makeOutline} disabled={busy || prompt.trim().length < 2} className="ml-auto gap-1.5" data-testid="deck-outline-button">
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />} Write outline
                  </Button>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((ex) => (
                  <button key={ex} onClick={() => setPrompt(ex)}
                    className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground">
                    {ex}
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <section data-testid="deck-outline">
              <button onClick={() => setStep("prompt")} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-4 w-4" /> Back
              </button>
              <div className="mt-4 grid gap-8 lg:grid-cols-[1fr_320px]">
                <div>
                  <h2 className="text-xl font-bold">Check the outline</h2>
                  <p className="mt-1 text-sm text-muted-foreground">Change anything you like. Each box becomes one slide.</p>
                  <Input value={title} onChange={(e) => setTitle(e.target.value)} className="mt-4 bg-card text-lg font-semibold" data-testid="deck-title-input" />
                  <ol className="mt-4 space-y-3">
                    {outline.map((s, i) => (
                      <li key={i} className="group flex gap-3 rounded-xl border border-border bg-card p-3">
                        <span className="mt-2 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">{i + 1}</span>
                        <div className="min-w-0 flex-1 space-y-2">
                          <Input value={s.title} onChange={(e) => setSlide(i, { title: e.target.value })} className="border-0 bg-transparent px-1 font-semibold shadow-none focus-visible:ring-1" />
                          <Textarea value={s.points} onChange={(e) => setSlide(i, { points: e.target.value })} rows={Math.max(2, s.points.split("\n").length)}
                            placeholder="Key points, one per line" className="resize-none border-0 bg-transparent px-1 text-sm text-muted-foreground shadow-none focus-visible:ring-1" />
                        </div>
                        <button onClick={() => setOutline((o) => o.filter((_, j) => j !== i))} title="Remove slide"
                          className="self-start rounded-md p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100">
                          <X className="h-4 w-4" />
                        </button>
                      </li>
                    ))}
                  </ol>
                  <Button variant="outline" className="mt-3 gap-1.5" onClick={() => setOutline((o) => [...o, { title: "New slide", points: "" }])}>
                    <Plus className="h-4 w-4" /> Add slide
                  </Button>
                </div>
                <aside className="lg:sticky lg:top-6 lg:self-start">
                  <h3 className="text-sm font-semibold">Pick a theme</h3>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {themes.map((t) => (
                      <button key={t.id} onClick={() => setTheme(t.id)} data-testid={`deck-theme-${t.id}`}
                        className={`overflow-hidden rounded-lg border-2 text-left transition-colors ${theme === t.id ? "border-primary" : "border-transparent hover:border-border"}`}>
                        <ScaledSlide slide={PREVIEW_SLIDE(title)} theme={t} />
                        <p className="px-2 py-1 text-xs font-medium">{t.name}</p>
                      </button>
                    ))}
                  </div>
                  <Button onClick={generate} disabled={busy} className="mt-5 w-full gap-1.5" size="lg" data-testid="deck-generate-button">
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Make {outline.length} slides
                  </Button>
                </aside>
              </div>
            </section>
          )}

          <div className="mt-14">
            <h2 className="text-sm font-semibold text-muted-foreground">Your presentations</h2>
            {decks === null ? (
              <div className="mt-8 flex justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
            ) : decks.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">None yet. Your first one will show up here.</p>
            ) : (
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {decks.map((d) => (
                  <div key={d.id} className="radha-lift group relative overflow-hidden rounded-xl border border-border bg-card hover:border-primary/50" data-testid={`deck-card-${d.id}`}>
                    <button onClick={() => navigate(`/decks/${d.id}`)} className="block w-full text-left">
                      <ScaledSlide slide={d.cover || PREVIEW_SLIDE(d.title)} theme={findTheme(themes, d.theme)} />
                      <div className="p-3">
                        <p className="truncate font-semibold">{d.title}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {d.status === "generating" ? "Designing…" : `${d.slideCount} slides`} · {new Date(d.updatedAt).toLocaleDateString()}
                        </p>
                      </div>
                    </button>
                    <button onClick={() => remove(d)} title="Delete"
                      className="absolute right-2 top-2 rounded-md bg-black/40 p-1.5 text-white opacity-0 transition-opacity hover:bg-black/60 group-hover:opacity-100">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
