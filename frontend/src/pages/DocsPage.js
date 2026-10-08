import { useEffect, useState } from "react";
import PageHero from "@/components/PageHero";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { FileText, Plus, Loader2, Sparkles, Trash2 } from "lucide-react";

const IDEAS = [
  "A leave application to my manager for 3 days",
  "A business proposal for a bakery in Pune",
  "A blog post: 5 ways small shops can use AI",
  "A rent agreement for a 2BHK flat in Mumbai",
];

export default function DocsPage() {
  const navigate = useNavigate();
  const [docs, setDocs] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api.get("/docs").then(({ data }) => setDocs(Array.isArray(data) ? data : [])).catch((e) => { toast.error(formatApiError(e)); setDocs([]); });
  }, []);

  const create = async (withPrompt) => {
    setBusy(withPrompt ? "draft" : "blank");
    try {
      const { data } = await api.post("/docs", withPrompt ? { prompt } : { title: "Untitled document", content: "" });
      navigate(`/docs/${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
      setBusy("");
    }
  };

  const remove = async (e, id) => {
    e.stopPropagation();
    try {
      await api.delete(`/docs/${id}`);
      setDocs((d) => d.filter((x) => x.id !== id));
    } catch (err) {
      toast.error(formatApiError(err));
    }
  };

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-10">
          <PageHero icon={FileText} title="Docs" subtitle="Write with Krish side by side. Select any part and ask Krish to change it, then download as Word or PDF." />

          <div className="mt-6 rounded-2xl border border-border bg-card p-4" data-testid="doc-draft-box">
            <p className="flex items-center gap-1.5 text-sm font-semibold"><Sparkles className="h-4 w-4 text-primary" /> What should Krish write?</p>
            <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} data-testid="doc-prompt-input"
              placeholder="e.g. A cover letter for a marketing job at Zomato" className="mt-2 min-h-[80px] bg-background" />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {IDEAS.map((idea) => (
                <button key={idea} onClick={() => setPrompt(idea)} className="rounded-full border border-border px-2.5 py-1 text-[11px] text-muted-foreground hover:border-primary/50 hover:text-foreground">{idea}</button>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button onClick={() => create(true)} disabled={!prompt.trim() || !!busy} data-testid="doc-write-button" className="gap-2 font-semibold">
                {busy === "draft" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Write it
              </Button>
              <Button variant="outline" onClick={() => create(false)} disabled={!!busy} data-testid="doc-blank-button" className="gap-2 border-border bg-card">
                {busy === "blank" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Blank document
              </Button>
            </div>
          </div>

          <h2 className="mt-8 text-sm font-semibold">Your documents</h2>
          {docs === null ? <Loader2 className="mx-auto mt-8 h-5 w-5 animate-spin text-primary" /> : docs.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">No documents yet.</p>
          ) : (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {docs.map((d) => (
                <div key={d.id} role="button" tabIndex={0} onClick={() => navigate(`/docs/${d.id}`)} data-testid={`doc-card-${d.id}`}
                  onKeyDown={(e) => { if (e.key === "Enter") navigate(`/docs/${d.id}`); }}
                  className="radha-lift group flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-4 hover:border-primary/50">
                  <FileText className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{d.title}</p>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{d.preview.replace(/[#*_>`]/g, "") || "Empty"}</p>
                    <p className="mt-1.5 text-[11px] text-muted-foreground">{new Date(d.updatedAt).toLocaleDateString()}</p>
                  </div>
                  <button onClick={(e) => remove(e, d.id)} title="Delete" className="text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100 max-md:opacity-100">
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
