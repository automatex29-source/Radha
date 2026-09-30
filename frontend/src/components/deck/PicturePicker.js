import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { ImageOff, Link2, Loader2, Search, Sparkles, Upload } from "lucide-react";
import { pictureSrc } from "@/components/deck/Slide";

const TABS = [
  ["ai", Sparkles, "AI picture"],
  ["photos", Search, "Photos"],
  ["own", Upload, "Your picture"],
];

/** Choose a slide's picture: make one with AI, pick a stock photo, or use your own. */
export default function PicturePicker({ open, onOpenChange, deckId, index, slide, onDeck }) {
  const [tab, setTab] = useState("ai");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    if (!open || !slide) return;
    setQuery(slide.image_query || slide.title || "");
    setPrompt(slide.image_prompt || slide.image_query || slide.title || "");
    setResults(null);
    setLink("");
  }, [open, slide]);

  const run = async (label, fn) => {
    setBusy(label);
    try {
      await fn();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy("");
    }
  };

  const done = (data) => {
    onDeck(data);
    onOpenChange(false);
  };

  const search = () => run("search", async () => {
    if (!query.trim()) return;
    setResults(null);
    const { data } = await api.get("/decks/images/search", { params: { q: query.trim() } });
    setResults(data.results);
  });

  useEffect(() => {
    if (open && tab === "photos" && results === null && query.trim()) search();
  }, [open, tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const choose = (image) => run("choose", async () => {
    const { data } = await api.post(`/decks/${deckId}/slides/${index}/image`, { image });
    done(data);
  });

  const makeAi = () => run("ai", async () => {
    const { data } = await api.post(`/decks/${deckId}/slides/${index}/ai-image`, { prompt: prompt.trim() });
    done(data);
  });

  const upload = (file) => run("upload", async () => {
    const form = new FormData();
    form.append("file", file);
    const { data: saved } = await api.post("/media", form);
    const { data } = await api.post(`/decks/${deckId}/slides/${index}/image`,
      { image: { url: saved.url, thumb: "", credit: "", link: "" } });
    done(data);
  });

  const remove = () => run("remove", async () => {
    const { data } = await api.delete(`/decks/${deckId}/slides/${index}/image`);
    done(data);
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !busy && onOpenChange(v)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl" data-testid="picture-picker">
        <DialogHeader>
          <DialogTitle>Change picture</DialogTitle>
          <DialogDescription>For slide {index + 1}: {slide?.title || "untitled"}</DialogDescription>
        </DialogHeader>
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          {TABS.map(([id, Icon, label]) => (
            <button key={id} onClick={() => setTab(id)} data-testid={`picker-tab-${id}`}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-sm font-medium ${tab === id ? "bg-background shadow-sm" : "text-muted-foreground"}`}>
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}
        </div>

        {tab === "ai" && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">Describe exactly what the picture should show. Krish AI draws it to match the slide.</p>
            <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} data-testid="picker-ai-prompt"
              placeholder="e.g. Indian farmer checking a green wheat field at sunrise, drone in the sky" />
            <Button onClick={makeAi} disabled={!!busy || prompt.trim().length < 3} className="gap-1.5" data-testid="picker-ai-make">
              {busy === "ai" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {busy === "ai" ? "Drawing… this can take up to a minute" : "Make picture"}
            </Button>
          </div>
        )}

        {tab === "photos" && (
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()}
                placeholder="What should the photo show?" data-testid="picker-search" />
              <Button variant="outline" onClick={search} disabled={!!busy}>
                {busy === "search" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </Button>
            </div>
            {results === null ? (
              busy === "search" && <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
            ) : results.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">No photos found. Try simpler words, like "doctor with patient".</p>
            ) : (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {results.map((r) => (
                  <button key={r.url} onClick={() => choose(r)} disabled={!!busy} title={r.credit}
                    className="group relative aspect-video overflow-hidden rounded-md border border-border hover:ring-2 hover:ring-primary">
                    <img src={r.thumb || r.url} alt="" referrerPolicy="no-referrer" loading="lazy" className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "own" && (
          <div className="space-y-4">
            <label className="flex cursor-pointer flex-col items-center gap-1 rounded-xl border-2 border-dashed border-border px-4 py-6 text-sm text-muted-foreground hover:border-primary/40">
              {busy === "upload" ? <Loader2 className="h-5 w-5 animate-spin text-primary" /> : <Upload className="h-5 w-5" />}
              Upload a picture (PNG, JPG or WebP)
              <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" disabled={!!busy}
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) upload(f); }} />
            </label>
            <div className="flex gap-2">
              <Input value={link} onChange={(e) => setLink(e.target.value)} placeholder="Or paste a picture link (https://…)" />
              <Button variant="outline" disabled={!!busy || !link.trim().startsWith("https://")} className="gap-1.5"
                onClick={() => choose({ url: link.trim(), thumb: "", credit: "", link: "" })}>
                <Link2 className="h-4 w-4" /> Use
              </Button>
            </div>
          </div>
        )}

        {slide?.image && (
          <div className="flex items-center gap-3 border-t border-border pt-3">
            <img src={pictureSrc(slide.image.url)} alt="" referrerPolicy="no-referrer" className="h-12 w-20 rounded object-cover" />
            <span className="flex-1 truncate text-xs text-muted-foreground">Current: {slide.image.credit || "your picture"}</span>
            <Button variant="ghost" size="sm" onClick={remove} disabled={!!busy} className="gap-1.5 text-muted-foreground">
              <ImageOff className="h-4 w-4" /> Remove
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
