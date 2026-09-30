import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate, useParams } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import {
  ArrowDown, ArrowLeft, ArrowUp, Copy, Download, FileText, ImageIcon, Loader2, Palette, Pencil, Play, Plus,
  Presentation, Send, Sparkles, Trash2, Undo2, X, ChevronLeft, ChevronRight,
} from "lucide-react";
import Slide, { SLIDE_H, SLIDE_W, ScaledSlide, findTheme, useDeckThemes } from "@/components/deck/Slide";
import PicturePicker from "@/components/deck/PicturePicker";

const LAYOUTS = [
  ["cover", "Cover"], ["section", "Section"], ["bullets", "Bullet points"], ["image_right", "Text + picture right"],
  ["image_left", "Picture left + text"], ["cards", "Cards with icons"], ["stats", "Big numbers"], ["chart", "Chart"],
  ["steps", "Steps / timeline"], ["quote", "Quote"], ["comparison", "Comparison"], ["closing", "Closing"],
];
const IMAGE_LAYOUTS = ["cover", "image_right", "image_left"];
const SUGGESTIONS = [
  "Make this slide more visual",
  "Add a slide about pricing after this one",
  "Make all the text shorter",
  "Use a warmer theme",
  "Translate the whole deck to Hindi",
  "Give this slide a better matching picture",
];

const CHART_TYPES = [["bar", "Bars"], ["line", "Line"], ["pie", "Pie"], ["doughnut", "Doughnut"]];
const chartRows = (ch) => (ch?.labels || []).map((l, i) => [l, ...(ch.series || []).map((sr) => sr.values[i] ?? "")].join(", ")).join("\n");
function parseChart(type, names, rows) {
  const lines_ = rows.split("\n").map((r) => r.split(",").map((x) => x.trim())).filter((r) => r[0]);
  const n = Math.max(1, ...lines_.map((r) => r.length - 1));
  const seriesNames = names.split(",").map((x) => x.trim());
  return {
    type,
    labels: lines_.map((r) => r[0]),
    series: Array.from({ length: n }, (_, i) => ({
      name: seriesNames[i] || `Series ${i + 1}`,
      values: lines_.map((r) => parseFloat(String(r[i + 1] ?? "").replace(/[^\d.-]/g, "")) || 0),
    })),
  };
}

function ChartEditor({ chart, onChange }) {
  const ch = chart || { type: "bar", labels: [], series: [{ name: "Value", values: [] }] };
  const [rows, setRows] = useState(chartRows(ch));
  const [names, setNames] = useState((ch.series || []).map((sr) => sr.name).join(", "));
  const update = (type, n, r) => onChange(parseChart(type, n, r));
  return (
    <div className="space-y-2 rounded-lg border border-border p-2">
      <div className="flex gap-1">
        {CHART_TYPES.map(([id, label]) => (
          <button key={id} onClick={() => update(id, names, rows)}
            className={`flex-1 rounded-md py-1 text-xs ${ch.type === id ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>{label}</button>
        ))}
      </div>
      <Field label="Series names (comma between)">
        <Input className="bg-card text-sm" value={names} onChange={(e) => { setNames(e.target.value); update(ch.type, e.target.value, rows); }} placeholder="Sales, Profit" />
      </Field>
      <Field label="Data: one row per line, label then numbers">
        <Textarea className="bg-card font-mono text-xs" rows={6} value={rows} placeholder={"2022, 120, 30\n2023, 150, 42"}
          onChange={(e) => { setRows(e.target.value); update(ch.type, names, e.target.value); }} />
      </Field>
    </div>
  );
}

const lines = (arr) => (arr || []).join("\n");
const unlines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);

// ------------------------------------------------------------ slide text editor
function Field({ label, children }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function SlideForm({ draft, setDraft }) {
  const L = draft.layout;
  const set = (patch) => setDraft({ ...draft, ...patch });
  const setItem = (i, patch) => set({ items: draft.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
  const setStat = (i, patch) => set({ stats: draft.stats.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
  const inputCls = "bg-card text-sm";
  return (
    <div className="space-y-3">
      <Field label="Layout">
        <select value={L} onChange={(e) => setDraft(switchLayout(draft, e.target.value))} data-testid="deck-layout-select"
          className="h-9 w-full rounded-md border border-border bg-card px-2 text-sm">
          {LAYOUTS.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
      </Field>
      {L !== "quote" && (
        <Field label="Title"><Input className={inputCls} value={draft.title} onChange={(e) => set({ title: e.target.value })} /></Field>
      )}
      {["cover", "section", "closing"].includes(L) && (
        <Field label="Subtitle"><Textarea className={inputCls} rows={2} value={draft.subtitle} onChange={(e) => set({ subtitle: e.target.value })} /></Field>
      )}
      {["bullets", "image_right", "image_left", "stats"].includes(L) && (
        <Field label={L === "stats" ? "Note under the numbers" : "Intro sentence"}>
          <Textarea className={inputCls} rows={2} value={draft.body} onChange={(e) => set({ body: e.target.value })} />
        </Field>
      )}
      {["bullets", "image_right", "image_left"].includes(L) && (
        <Field label="Bullet points (one per line)">
          <Textarea className={inputCls} rows={5} value={lines(draft.bullets)} onChange={(e) => set({ bullets: e.target.value.split("\n") })} />
        </Field>
      )}
      {["cards", "steps"].includes(L) && (
        <div className="space-y-2">
          <span className="text-xs font-medium text-muted-foreground">{L === "cards" ? "Cards" : "Steps"}</span>
          {draft.items.map((it, i) => (
            <div key={i} className="space-y-1.5 rounded-lg border border-border p-2">
              <div className="flex gap-1.5">
                {L === "cards" && <Input className={`${inputCls} w-14 text-center`} value={it.icon} onChange={(e) => setItem(i, { icon: e.target.value })} title="Emoji" />}
                <Input className={inputCls} value={it.title} placeholder="Title" onChange={(e) => setItem(i, { title: e.target.value })} />
                <button onClick={() => set({ items: draft.items.filter((_, j) => j !== i) })} className="px-1 text-muted-foreground hover:text-destructive"><X className="h-4 w-4" /></button>
              </div>
              <Textarea className={inputCls} rows={2} value={it.text} placeholder="Text" onChange={(e) => setItem(i, { text: e.target.value })} />
            </div>
          ))}
          {draft.items.length < (L === "steps" ? 5 : 4) && (
            <Button variant="outline" size="sm" onClick={() => set({ items: [...draft.items, { icon: "✨", title: "", text: "" }] })}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Add
            </Button>
          )}
        </div>
      )}
      {L === "stats" && (
        <div className="space-y-2">
          <span className="text-xs font-medium text-muted-foreground">Numbers</span>
          {draft.stats.map((st, i) => (
            <div key={i} className="flex gap-1.5">
              <Input className={`${inputCls} w-24`} value={st.value} placeholder="87%" onChange={(e) => setStat(i, { value: e.target.value })} />
              <Input className={inputCls} value={st.label} placeholder="What it means" onChange={(e) => setStat(i, { label: e.target.value })} />
              <button onClick={() => set({ stats: draft.stats.filter((_, j) => j !== i) })} className="px-1 text-muted-foreground hover:text-destructive"><X className="h-4 w-4" /></button>
            </div>
          ))}
          {draft.stats.length < 4 && (
            <Button variant="outline" size="sm" onClick={() => set({ stats: [...draft.stats, { value: "", label: "" }] })}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Add
            </Button>
          )}
        </div>
      )}
      {L === "chart" && (
        <>
          <ChartEditor key={draft.id} chart={draft.chart} onChange={(chart) => set({ chart })} />
          <Field label="Takeaway (shown beside the chart)">
            <Textarea className={inputCls} rows={2} value={draft.body} onChange={(e) => set({ body: e.target.value })} />
          </Field>
        </>
      )}
      {L === "quote" && (
        <>
          <Field label="Quote"><Textarea className={inputCls} rows={3} value={draft.quote} onChange={(e) => set({ quote: e.target.value })} /></Field>
          <Field label="Who said it"><Input className={inputCls} value={draft.author} onChange={(e) => set({ author: e.target.value })} /></Field>
        </>
      )}
      {L === "comparison" && ["left", "right"].map((side) => (
        <div key={side} className="space-y-1.5 rounded-lg border border-border p-2">
          <Input className={inputCls} value={draft[side].title} placeholder={side === "left" ? "Left heading" : "Right heading"}
            onChange={(e) => set({ [side]: { ...draft[side], title: e.target.value } })} />
          <Textarea className={inputCls} rows={3} value={lines(draft[side].bullets)} placeholder="One point per line"
            onChange={(e) => set({ [side]: { ...draft[side], bullets: e.target.value.split("\n") } })} />
        </div>
      ))}
      {IMAGE_LAYOUTS.includes(L) && (
        <Field label="Picture search words (change and save for a new picture)">
          <Input className={inputCls} value={draft.image_query} placeholder="e.g. city skyline at night" onChange={(e) => set({ image_query: e.target.value })} />
        </Field>
      )}
      <Field label="Speaker notes"><Textarea className={inputCls} rows={3} value={draft.notes} onChange={(e) => set({ notes: e.target.value })} /></Field>
    </div>
  );
}

/** Carry the slide's words over when its layout changes, so nothing typed is lost. */
function switchLayout(d, layout) {
  const next = { ...d, layout };
  const fromItems = (d.items || []).map((it) => [it.title, it.text].filter(Boolean).join(": "));
  const fromStats = (d.stats || []).map((st) => `${st.value} ${st.label}`.trim());
  const fromSides = [...(d.left?.bullets || []), ...(d.right?.bullets || [])];
  const points = unlines(lines(d.bullets)).length ? unlines(lines(d.bullets))
    : fromItems.length ? fromItems : fromStats.length ? fromStats : fromSides;
  if (["bullets", "image_right", "image_left"].includes(layout) && !unlines(lines(d.bullets)).length) next.bullets = points.slice(0, 6);
  if (["cards", "steps"].includes(layout) && !(d.items || []).length) {
    next.items = points.slice(0, layout === "steps" ? 5 : 4).map((p) => {
      const [title, ...rest] = p.split(": ");
      return { icon: "✨", title: rest.length ? title : p.split(" ").slice(0, 4).join(" "), text: rest.length ? rest.join(": ") : p };
    });
  }
  if (layout === "comparison" && !(d.left?.bullets || []).length && !(d.right?.bullets || []).length) {
    const half = Math.ceil(points.length / 2);
    next.left = { title: "Before", bullets: points.slice(0, half) };
    next.right = { title: "After", bullets: points.slice(half) };
  }
  if (layout === "chart" && !d.chart) {
    const nums = (d.stats || []).map((st) => [st.label || st.value, parseFloat(String(st.value).replace(/[^\d.-]/g, ""))]).filter(([, v]) => !Number.isNaN(v));
    next.chart = nums.length
      ? { type: "bar", labels: nums.map(([l]) => l), series: [{ name: "Value", values: nums.map(([, v]) => v) }] }
      : { type: "bar", labels: ["A", "B", "C"], series: [{ name: "Value", values: [3, 5, 4] }] };
  }
  if (layout === "quote" && !d.quote) next.quote = d.body || d.subtitle || d.title;
  if (["cover", "section", "closing"].includes(layout) && !d.subtitle) next.subtitle = d.body || points[0] || "";
  return next;
}

const cleanDraft = (d) => ({
  ...d,
  bullets: unlines(lines(d.bullets)),
  left: { ...d.left, bullets: unlines(lines(d.left?.bullets)) },
  right: { ...d.right, bullets: unlines(lines(d.right?.bullets)) },
});

// ------------------------------------------------------------ present + print
function PresentMode({ slides, theme, start, onClose }) {
  const [i, setI] = useState(start);
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.requestFullscreen?.().catch(() => {});
    const onKey = (e) => {
      if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) setI((v) => Math.min(slides.length - 1, v + 1));
      else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(e.key)) setI((v) => Math.max(0, v - 1));
      else if (e.key === "Escape") onClose();
    };
    const onFs = () => { if (!document.fullscreenElement) onClose(); };
    window.addEventListener("keydown", onKey);
    document.addEventListener("fullscreenchange", onFs);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("fullscreenchange", onFs);
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    };
  }, [slides.length, onClose]);
  return (
    <div ref={ref} className="fixed inset-0 z-50 bg-black" data-testid="deck-present"
      onClick={(e) => setI((v) => (e.clientX < window.innerWidth / 3 ? Math.max(0, v - 1) : Math.min(slides.length - 1, v + 1)))}>
      <ScaledSlide fit className="h-full w-full" slide={slides[i]} theme={theme} index={i} total={slides.length} />
      <div className="absolute bottom-4 right-4 flex items-center gap-2 text-xs text-white/60">
        {i + 1} / {slides.length}
        <button onClick={(e) => { e.stopPropagation(); onClose(); }} className="rounded-md bg-white/10 p-1.5 hover:bg-white/20"><X className="h-4 w-4" /></button>
      </div>
    </div>
  );
}

function PrintDeck({ slides, theme, onDone }) {
  const ref = useRef(null);
  useEffect(() => {
    let cancelled = false;
    const imgs = Array.from(ref.current?.querySelectorAll("img") || []);
    const loaded = Promise.all(imgs.map((img) => (img.complete ? null : new Promise((r) => { img.onload = img.onerror = r; }))));
    const timeout = new Promise((r) => setTimeout(r, 4000));
    const after = () => onDone();
    window.addEventListener("afterprint", after);
    Promise.race([loaded, timeout]).then(() => new Promise((r) => setTimeout(r, 300))).then(() => {
      if (!cancelled) window.print();
    });
    return () => { cancelled = true; window.removeEventListener("afterprint", after); };
  }, [onDone]);
  return createPortal(
    <div id="radha-deck-print" ref={ref}>
      <style>{`
        #radha-deck-print { position: fixed; left: -100000px; top: 0; }
        @page { size: ${SLIDE_W}px ${SLIDE_H}px; margin: 0; }
        @media print {
          body > *:not(#radha-deck-print) { display: none !important; }
          html, body { margin: 0 !important; padding: 0 !important; background: none !important; }
          #radha-deck-print { position: static; }
          #radha-deck-print .deck-page { width: ${SLIDE_W}px; height: ${SLIDE_H}px; overflow: hidden; break-after: page; page-break-after: always; }
          #radha-deck-print * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        }
      `}</style>
      {slides.map((s, i) => (
        <div className="deck-page" key={s.id || i}><Slide slide={s} theme={theme} index={i} total={slides.length} /></div>
      ))}
    </div>,
    document.body,
  );
}

// ------------------------------------------------------------ editor page
export default function DeckEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const themes = useDeckThemes();
  const [deck, setDeck] = useState(null);
  const [sel, setSel] = useState(0);
  const [tab, setTab] = useState("ai");
  const [draft, setDraft] = useState(null);
  const [chat, setChat] = useState([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [busy, setBusy] = useState("");
  const [presenting, setPresenting] = useState(false);
  const [printing, setPrinting] = useState(false);
  const [picker, setPicker] = useState(false);
  const chatEnd = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/decks/${id}`);
      setDeck(data);
      return data;
    } catch (e) {
      toast.error(formatApiError(e));
      if (e?.response?.status === 404) navigate("/decks");
      return null;
    }
  }, [id, navigate]);

  useEffect(() => { load(); }, [load]);

  // While slides are being written, poll so they appear one batch at a time.
  useEffect(() => {
    if (deck?.status !== "generating" && !deck?.picturesPending) return undefined;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [deck?.status, deck?.picturesPending, load]);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [chat, thinking]);

  const slides = deck?.slides || [];
  const theme = findTheme(themes, deck?.theme);
  const current = slides[Math.min(sel, Math.max(0, slides.length - 1))];
  const dirty = draft && current && draft.id === current.id && JSON.stringify(cleanDraft(draft)) !== JSON.stringify(cleanDraft(current));
  const shown = draft && current && draft.id === current.id ? cleanDraft(draft) : current;

  useEffect(() => {
    if (current && (!draft || draft.id !== current.id)) setDraft(JSON.parse(JSON.stringify(current)));
  }, [current, draft]);

  const selectSlide = (i) => {
    setSel(i);
    setDraft(slides[i] ? JSON.parse(JSON.stringify(slides[i])) : null);
  };

  const patch = async (body, label = "save") => {
    setBusy(label);
    try {
      const { data } = await api.patch(`/decks/${id}`, body);
      setDeck(data);
      return data;
    } catch (e) {
      toast.error(formatApiError(e));
      return null;
    } finally {
      setBusy("");
    }
  };

  const saveSlides = async (next, selectIndex) => {
    const data = await patch({ slides: next });
    if (data) selectSlide(Math.max(0, Math.min(selectIndex ?? sel, data.slides.length - 1)));
    return data;
  };

  const saveDraft = async () => {
    const data = await patch({ slides: slides.map((s, i) => (i === sel ? cleanDraft(draft) : s)) });
    if (data) { setDraft(JSON.parse(JSON.stringify(data.slides[sel]))); toast.success("Slide saved"); }
  };

  const move = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= slides.length) return;
    const next = [...slides];
    [next[i], next[j]] = [next[j], next[i]];
    saveSlides(next, j);
  };
  const duplicate = (i) => saveSlides([...slides.slice(0, i + 1), { ...slides[i] }, ...slides.slice(i + 1)], i + 1);
  const removeSlide = (i) => {
    if (slides.length <= 1) return;
    saveSlides(slides.filter((_, j) => j !== i), Math.max(0, i - 1));
  };
  const addSlide = async () => {
    const blank = { layout: "bullets", title: "New slide", bullets: ["First point", "Second point", "Third point"] };
    const data = await saveSlides([...slides.slice(0, sel + 1), blank, ...slides.slice(sel + 1)], sel + 1);
    if (data) setTab("edit");
  };

  const ask = async (text) => {
    const instruction = (text ?? input).trim();
    if (!instruction || thinking) return;
    setInput("");
    setChat((c) => [...c, { role: "user", text: instruction }]);
    setThinking(true);
    try {
      const { data } = await api.post(`/decks/${id}/edit`, { instruction, slide: sel });
      setDeck(data.deck);
      setDraft(null);
      setSel((v) => Math.min(v, data.deck.slides.length - 1));
      setChat((c) => [...c, { role: "ai", text: data.reply }]);
    } catch (e) {
      setChat((c) => [...c, { role: "ai", text: formatApiError(e), error: true }]);
    } finally {
      setThinking(false);
    }
  };

  const undo = async () => {
    setBusy("undo");
    try {
      const { data } = await api.post(`/decks/${id}/undo`);
      setDeck(data);
      setDraft(null);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy("");
    }
  };

  const downloadPptx = async () => {
    setBusy("pptx");
    try {
      const res = await api.get(`/decks/${id}/export`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(deck.title || "presentation").replace(/[^\w\- ]+/g, "").trim() || "presentation"}.pptx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) {
      toast.error("Download failed. Please try again.");
    } finally {
      setBusy("");
    }
  };

  const closePresent = useCallback(() => setPresenting(false), []);
  const donePrinting = useCallback(() => setPrinting(false), []);

  if (!deck || !theme) {
    return (
      <div className="flex h-dvh items-center justify-center bg-background"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
    );
  }

  const generating = deck.status === "generating";
  const pending = generating ? Math.max(0, (deck.total || 0) - slides.length) : 0;

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background max-md:flex-col">
      <IconRail mobileBar={false} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* top bar */}
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-3">
          <Button variant="ghost" size="icon" onClick={() => navigate("/decks")} title="All presentations"><ArrowLeft className="h-4 w-4" /></Button>
          <Presentation className="h-4 w-4 shrink-0 text-primary" />
          <input defaultValue={deck.title} key={deck.title} data-testid="deck-title"
            onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== deck.title) patch({ title: v }); }}
            onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
            className="min-w-0 flex-1 truncate rounded-md bg-transparent px-2 py-1 text-sm font-semibold outline-none hover:bg-surface focus:bg-surface" />
          {generating && (
            <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> Designing slides {slides.length}/{deck.total}
            </span>
          )}
          <Button variant="ghost" size="sm" onClick={undo} disabled={!deck.canUndo || !!busy || generating} title="Undo last change" data-testid="deck-undo">
            {busy === "undo" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Undo2 className="h-4 w-4" />}
          </Button>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-1.5" data-testid="deck-theme-button"><Palette className="h-4 w-4" /><span className="hidden sm:inline">Theme</span></Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-80">
              <div className="grid grid-cols-3 gap-2">
                {themes.map((t) => (
                  <button key={t.id} onClick={() => patch({ theme: t.id }, "theme")}
                    className={`overflow-hidden rounded-md border-2 ${deck.theme === t.id ? "border-primary" : "border-transparent hover:border-border"}`}>
                    <ScaledSlide slide={slides[0] || { layout: "cover", title: deck.title }} theme={t} />
                    <p className="py-0.5 text-[11px]">{t.name}</p>
                  </button>
                ))}
              </div>
            </PopoverContent>
          </Popover>
          <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => setPresenting(true)} disabled={!slides.length} data-testid="deck-present-button">
            <Play className="h-4 w-4" /><span className="hidden sm:inline">Present</span>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" className="gap-1.5" disabled={!slides.length || !!busy} data-testid="deck-download-button">
                {busy === "pptx" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                <span className="hidden sm:inline">Download</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={downloadPptx} data-testid="deck-download-pptx"><Presentation className="mr-2 h-4 w-4" /> PowerPoint (.pptx)</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setPrinting(true)}><FileText className="mr-2 h-4 w-4" /> PDF (choose “Save as PDF”)</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <div className="radha-scroll flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
          {/* thumbnails */}
          <aside className="radha-scroll hidden w-52 shrink-0 space-y-3 overflow-y-auto border-r border-border p-3 lg:block">
            {slides.map((s, i) => (
              <div key={s.id} className="group relative">
                <button onClick={() => selectSlide(i)} data-testid={`deck-thumb-${i}`}
                  className={`block w-full overflow-hidden rounded-md border-2 transition-colors ${i === sel ? "border-primary" : "border-transparent hover:border-border"}`}>
                  <ScaledSlide slide={s} theme={theme} index={i} total={slides.length} pending={deck.picturesPending} />
                </button>
                <span className="absolute left-1 top-1 rounded bg-black/50 px-1 text-[10px] text-white">{i + 1}</span>
                {!generating && (
                  <div className="absolute right-1 top-1 hidden gap-0.5 rounded bg-black/60 p-0.5 group-hover:flex">
                    {[[ArrowUp, "Move up", () => move(i, -1)], [ArrowDown, "Move down", () => move(i, 1)],
                      [Copy, "Duplicate", () => duplicate(i)], [Trash2, "Delete", () => removeSlide(i)]].map(([Icon, label, fn]) => (
                      <button key={label} title={label} onClick={fn} className="rounded p-0.5 text-white hover:bg-white/20"><Icon className="h-3 w-3" /></button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {Array.from({ length: pending }).map((_, i) => (
              <div key={`p${i}`} className="aspect-video animate-pulse rounded-md bg-surface-strong" />
            ))}
            {!generating && (
              <Button variant="outline" size="sm" className="w-full gap-1" onClick={addSlide} disabled={!!busy}><Plus className="h-3.5 w-3.5" /> Add slide</Button>
            )}
          </aside>

          {/* main slide */}
          <main className="flex min-w-0 flex-col bg-sunken/40 max-lg:h-[55vh] max-lg:shrink-0 lg:flex-1">
            <div className="flex min-h-0 flex-1 items-center justify-center p-4 sm:p-8">
              {current ? (
                <ScaledSlide fit className="h-full w-full" slide={shown} theme={theme} index={sel} total={slides.length} pending={deck.picturesPending} />
              ) : generating ? (
                <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground">
                  <Sparkles className="h-8 w-8 animate-pulse text-primary" /> Krish AI is designing your slides…
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">{deck.error || "No slides yet."}</p>
              )}
            </div>
            <div className="flex shrink-0 items-center justify-center gap-2 pb-3 text-xs text-muted-foreground">
              <Button variant="ghost" size="icon" onClick={() => selectSlide(Math.max(0, sel - 1))} disabled={sel === 0}><ChevronLeft className="h-4 w-4" /></Button>
              {slides.length ? `${sel + 1} / ${slides.length}` : ""}
              <Button variant="ghost" size="icon" onClick={() => selectSlide(Math.min(slides.length - 1, sel + 1))} disabled={sel >= slides.length - 1}><ChevronRight className="h-4 w-4" /></Button>
              {current && [...IMAGE_LAYOUTS, "bullets", "section", "closing"].includes(current.layout) && (
                <Button variant="outline" size="sm" className="ml-2 gap-1.5" onClick={() => setPicker(true)} disabled={!!busy || generating} data-testid="deck-change-picture">
                  <ImageIcon className="h-3.5 w-3.5" /> {current.image ? "Change picture" : "Add picture"}
                </Button>
              )}
              {deck.picturesPending && (
                <span className="ml-2 flex items-center gap-1.5"><Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> Making pictures…</span>
              )}
            </div>
            {deck.error && slides.length > 0 && !generating && (
              <p className="pb-3 text-center text-xs text-amber-600 dark:text-amber-400">{deck.error}</p>
            )}
          </main>

          {/* right panel */}
          <aside className="flex shrink-0 flex-col border-border max-lg:h-[60vh] max-lg:border-t lg:w-80 lg:border-l">
            <div className="flex gap-1 border-b border-border p-2">
              {[["ai", Sparkles, "Ask Krish AI"], ["edit", Pencil, "Edit slide"]].map(([key, Icon, label]) => (
                <button key={key} onClick={() => setTab(key)} data-testid={`deck-tab-${key}`}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-sm font-medium ${tab === key ? "bg-surface-strong text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                  <Icon className="h-3.5 w-3.5" /> {label}
                </button>
              ))}
            </div>
            {tab === "ai" ? (
              <>
                <div className="radha-scroll min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
                  {chat.length === 0 && (
                    <div className="space-y-2">
                      <p className="text-sm text-muted-foreground">Tell Krish AI what to change. It edits slide {sel + 1} or the whole deck.</p>
                      {SUGGESTIONS.map((s) => (
                        <button key={s} onClick={() => ask(s)} disabled={generating || thinking}
                          className="block w-full rounded-lg border border-border px-3 py-2 text-left text-xs hover:border-primary/40 disabled:opacity-50">{s}</button>
                      ))}
                    </div>
                  )}
                  {chat.map((m, i) => (
                    <div key={i} className={`rounded-xl px-3 py-2 text-sm ${m.role === "user" ? "ml-6 bg-primary text-primary-foreground" : m.error ? "mr-6 bg-destructive/10 text-destructive" : "mr-6 bg-surface-strong"}`}>
                      {m.text}
                    </div>
                  ))}
                  {thinking && <div className="mr-6 flex items-center gap-2 rounded-xl bg-surface-strong px-3 py-2 text-sm text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Working on it…</div>}
                  <div ref={chatEnd} />
                </div>
                <div className="border-t border-border p-2">
                  <div className="flex items-end gap-1.5 rounded-lg border border-border bg-card p-1.5">
                    <Textarea value={input} onChange={(e) => setInput(e.target.value)} rows={2} data-testid="deck-chat-input"
                      placeholder={generating ? "Wait for the slides to finish…" : "e.g. Turn this into 3 cards with icons"}
                      disabled={generating}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
                      className="min-h-0 resize-none border-0 bg-transparent p-1 text-sm shadow-none focus-visible:ring-0" />
                    <Button size="icon" onClick={() => ask()} disabled={!input.trim() || thinking || generating} data-testid="deck-chat-send"><Send className="h-4 w-4" /></Button>
                  </div>
                </div>
              </>
            ) : (
              <div className="radha-scroll min-h-0 flex-1 overflow-y-auto p-3">
                {draft && current ? (
                  <>
                    <SlideForm draft={draft} setDraft={setDraft} />
                    <div className="sticky bottom-0 mt-4 flex gap-2 bg-background py-2">
                      <Button className="flex-1" onClick={saveDraft} disabled={!dirty || !!busy || generating} data-testid="deck-save-slide">
                        {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save slide"}
                      </Button>
                      <Button variant="outline" onClick={() => setDraft(JSON.parse(JSON.stringify(current)))} disabled={!dirty}>Reset</Button>
                    </div>
                    {IMAGE_LAYOUTS.includes(draft.layout) && !current.image && (
                      <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground"><ImageIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" /> Add picture search words and save to get a photo.</p>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">Pick a slide to edit.</p>
                )}
              </div>
            )}
          </aside>
        </div>
      </div>
      {presenting && slides.length > 0 && <PresentMode slides={slides} theme={theme} start={sel} onClose={closePresent} />}
      <PicturePicker open={picker} onOpenChange={setPicker} deckId={id} index={sel} slide={current}
        onDeck={(data) => { setDeck(data); setDraft(null); }} />
      {printing && <PrintDeck slides={slides} theme={theme} onDone={donePrinting} />}
    </div>
  );
}
