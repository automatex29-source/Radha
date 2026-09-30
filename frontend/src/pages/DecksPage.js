import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
  ArrowLeft, Check, FileText, Image as ImageIcon, ImageOff, Link2, Loader2, Plus, Presentation, Sparkles, Trash2, Upload,
  Wand2, X, Youtube, Type, ClipboardList,
} from "lucide-react";
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

const SOURCES = [
  { id: "topic", label: "Topic", Icon: Type },
  { id: "text", label: "Paste text", Icon: ClipboardList },
  { id: "file", label: "File", Icon: FileText },
  { id: "link", label: "Web link", Icon: Link2 },
  { id: "video", label: "YouTube", Icon: Youtube },
];
const PICTURES = [
  { id: "ai", label: "AI-made (best match)", Icon: Sparkles },
  { id: "stock", label: "Stock photos", Icon: ImageIcon },
  { id: "none", label: "None", Icon: ImageOff },
];
const words = (t) => (t || "").split(/\s+/).filter(Boolean).length;

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
  const [pictures, setPictures] = useState("ai");
  const [mode, setMode] = useState("topic");
  const [pasted, setPasted] = useState("");
  const [link, setLink] = useState("");
  const [source, setSource] = useState(null); // {kind, title, text, note}
  const [reading, setReading] = useState(false);
  const [improving, setImproving] = useState(false);
  const [title, setTitle] = useState("");
  const [outline, setOutline] = useState([]);
  const [theme, setTheme] = useState("aurora");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/decks").then(({ data }) => setDecks(data)).catch((e) => { toast.error(formatApiError(e)); setDecks([]); });
  }, []);

  // What the deck is built from: pasted text counts as a source too.
  const activeSource = mode === "text" ? (pasted.trim() ? { kind: "text", title: "Pasted text", text: pasted } : null)
    : mode === "topic" ? null : source;
  const ready = mode === "topic" ? prompt.trim().length >= 2 : !!activeSource;
  const brief = () => prompt.trim() || (activeSource ? `Make a clear presentation from this ${activeSource.kind === "video" ? "video" : activeSource.kind === "link" ? "web page" : "material"}: ${activeSource.title}` : "");

  const readFile = async (file) => {
    setReading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/decks/import/file", form);
      setSource(data);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setReading(false);
    }
  };

  const readLink = async () => {
    if (link.trim().length < 4) return;
    setReading(true);
    try {
      const { data } = await api.post("/decks/import/url", { url: link.trim() });
      setSource(data);
      if (data.note) toast(data.note);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setReading(false);
    }
  };

  const improve = async () => {
    setImproving(true);
    try {
      const { data } = await api.post("/decks/rephrase", { prompt });
      setPrompt(data.prompt);
      toast.success("Prompt improved. Change anything you like.");
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setImproving(false);
    }
  };

  const makeOutline = async () => {
    if (!ready) return;
    setBusy(true);
    try {
      const { data } = await api.post("/decks/outline", { prompt: brief(), slides: count, source: activeSource?.text || "" });
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
      const { data } = await api.post("/decks", { prompt: brief(), title, outline: clean, theme, density, pictures, source: activeSource?.text || "" });
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
    <div className="flex h-dvh w-full overflow-hidden bg-background max-md:flex-col">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
          {step === "prompt" ? (
            <section className="mx-auto max-w-3xl text-center" data-testid="deck-create">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Presentation className="h-6 w-6" />
              </div>
              <h1 className="radha-heading-gradient mt-4 text-3xl font-extrabold tracking-tighter sm:text-4xl">Presentations</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Start from a topic, your notes, a file, a web page or a YouTube video. Krish AI writes the outline, designs the slides, and you download a real PowerPoint.
              </p>
              <div className="mt-6 rounded-2xl border border-border bg-card p-3 text-left shadow-sm">
                <div className="mb-2 flex flex-wrap gap-1" data-testid="deck-source-tabs">
                  {SOURCES.map(({ id, label, Icon }) => (
                    <button key={id} type="button" onClick={() => { setMode(id); setSource(null); }} data-testid={`deck-source-${id}`}
                      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                        mode === id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-surface hover:text-foreground"}`}>
                      <Icon className="h-3.5 w-3.5" /> {label}
                    </button>
                  ))}
                </div>
                {mode === "text" && (
                  <Textarea value={pasted} onChange={(e) => setPasted(e.target.value)} rows={6} data-testid="deck-paste"
                    placeholder="Paste your notes, an article, a report or a table of numbers here."
                    className="mb-2 resize-y bg-background text-sm" />
                )}
                {mode === "file" && (
                  <label className="mb-2 flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground hover:border-primary/40">
                    {reading ? <Loader2 className="h-5 w-5 animate-spin text-primary" /> : <Upload className="h-5 w-5" />}
                    <span>{reading ? "Reading the file…" : "Choose a PDF, Word, PowerPoint, Excel, CSV or picture"}</span>
                    <input type="file" className="hidden" data-testid="deck-file" disabled={reading}
                      accept=".pdf,.docx,.pptx,.xlsx,.xlsm,.csv,.json,.txt,.md,.png,.jpg,.jpeg,.webp"
                      onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) readFile(f); }} />
                  </label>
                )}
                {(mode === "link" || mode === "video") && (
                  <div className="mb-2 flex gap-2">
                    <Input value={link} onChange={(e) => setLink(e.target.value)} data-testid="deck-link"
                      placeholder={mode === "video" ? "Paste a YouTube link" : "Paste a web page link"}
                      onKeyDown={(e) => { if (e.key === "Enter") readLink(); }} className="bg-background" />
                    <Button variant="outline" onClick={readLink} disabled={reading || link.trim().length < 4} data-testid="deck-read-link">
                      {reading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Read"}
                    </Button>
                  </div>
                )}
                {source && (
                  <div className="mb-2 flex items-start gap-2 rounded-lg bg-primary/10 px-3 py-2 text-xs" data-testid="deck-source-chip">
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{source.title}</p>
                      <p className="text-muted-foreground">{words(source.text).toLocaleString()} words read{source.note ? `. ${source.note}` : ""}</p>
                    </div>
                    <button onClick={() => setSource(null)} title="Remove"><X className="h-3.5 w-3.5" /></button>
                  </div>
                )}
                <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={mode === "topic" ? 3 : 2} data-testid="deck-prompt"
                  placeholder={mode === "topic" ? "What is your presentation about? Add who it's for and what to cover."
                    : "Optional: what should the deck focus on? (e.g. 'for investors, 5 key findings')"}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) makeOutline(); }}
                  className="resize-none border-0 bg-transparent text-base shadow-none focus-visible:ring-0" />
                <div className="flex flex-wrap items-center gap-2 border-t border-border px-1 pt-3">
                  <span className="text-xs text-muted-foreground">Slides</span>
                  {COUNTS.map((n) => <Chip key={n} active={count === n} onClick={() => setCount(n)} testid={`deck-count-${n}`}>{n}</Chip>)}
                  <span className="ml-2 text-xs text-muted-foreground">Text</span>
                  {DENSITIES.map((d) => <Chip key={d.id} active={density === d.id} onClick={() => setDensity(d.id)}>{d.label}</Chip>)}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 px-1">
                  <span className="text-xs text-muted-foreground">Pictures</span>
                  {PICTURES.map((p) => (
                    <Chip key={p.id} active={pictures === p.id} onClick={() => setPictures(p.id)} testid={`deck-pictures-${p.id}`}>
                      <span className="inline-flex items-center gap-1"><p.Icon className="h-3 w-3" /> {p.label}</span>
                    </Chip>
                  ))}
                  <div className="flex w-full gap-2 max-sm:mt-1 sm:ml-auto sm:w-auto">
                    <Button variant="outline" onClick={improve} disabled={busy || improving || prompt.trim().length < 2} className="gap-1.5 max-sm:flex-1" data-testid="deck-improve-button"
                      title="Turn a rough idea into a clear brief you can edit">
                      {improving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Improve prompt
                    </Button>
                    <Button onClick={makeOutline} disabled={busy || !ready} className="gap-1.5 max-sm:flex-1" data-testid="deck-outline-button">
                      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />} Write outline
                    </Button>
                  </div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((ex) => (
                  <button key={ex} onClick={() => { setMode("topic"); setPrompt(ex); }}
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
