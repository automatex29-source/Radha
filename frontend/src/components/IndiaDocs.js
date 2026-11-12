import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Calendar, Heart, Home, Landmark, Loader2, Mic, Receipt, Scale, Shield, Sparkles, Square, User } from "lucide-react";
import { toast } from "sonner";
import { api, formatApiError } from "@/lib/api";
import { transcribe } from "@/lib/voice";
import { useRecorder } from "@/hooks/useRecorder";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// Ready-made Indian documents (backend: india_docs.py). Pick one, fill a few boxes or just say it in Hinglish,
// and Krish makes the finished document in Docs, ready to download as Word or PDF.
const ICONS = { receipt: Receipt, home: Home, calendar: Calendar, heart: Heart, landmark: Landmark, user: User, scale: Scale, shield: Shield };
const TONES = ["from-amber-400 to-orange-500", "from-sky-500 to-indigo-600", "from-emerald-500 to-teal-600",
  "from-rose-400 to-pink-500", "from-violet-500 to-fuchsia-500", "from-cyan-500 to-blue-600"];

function DocForm({ doc, onClose }) {
  const navigate = useNavigate();
  const rec = useRecorder();
  const [values, setValues] = useState({});
  const [said, setSaid] = useState("");
  const [hearing, setHearing] = useState(false);
  const [busy, setBusy] = useState(false);
  const typed = doc.id !== "gst_invoice"; // the invoice is worked out from the boxes alone

  const mic = async () => {
    if (rec.recording) { rec.stop(); return; }
    try {
      const blob = await rec.record({ autoStop: true });
      if (!blob) return;
      setHearing(true);
      const text = await transcribe(blob);
      if (text) setSaid((s) => (s ? `${s.trimEnd()} ${text}` : text));
      else toast.message("Didn't catch that. Tap the mic and try again.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || "Microphone error");
    } finally {
      setHearing(false);
    }
  };

  const make = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/docs", { template: doc.id, fields: values, said, title: doc.title });
      navigate(`/docs/${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
      setBusy(false);
    }
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>{doc.title} <span className="font-normal text-muted-foreground">· {doc.hindi}</span></DialogTitle>
        <DialogDescription>{doc.hint} Fill what you know; anything you leave out stays as a blank to fill in later.</DialogDescription>
      </DialogHeader>
      {typed && (
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-3">
          <p className="text-xs font-semibold text-foreground">Just say it, in Hindi, English or Hinglish</p>
          <div className="mt-1.5 flex items-start gap-2">
            <Textarea value={said} onChange={(e) => setSaid(e.target.value)} data-testid="india-doc-said"
              placeholder="e.g. Mujhe 13 se 15 November tak chhutti chahiye, behen ki shaadi hai"
              className="min-h-[64px] flex-1 bg-background text-sm" />
            <Button type="button" variant={rec.recording ? "destructive" : "outline"} size="icon" onClick={mic}
              disabled={hearing} data-testid="india-doc-mic" title={rec.recording ? "Stop" : "Speak"} className="shrink-0">
              {hearing ? <Loader2 className="h-4 w-4 animate-spin" /> : rec.recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      )}
      <div className="grid max-h-[45vh] gap-2.5 overflow-y-auto pr-1">
        {doc.fields.map((f) => (
          <label key={f.key} className="grid gap-1 text-xs font-medium text-muted-foreground">
            {f.label}
            {f.key === "items" || f.key === "what" || f.key === "info" || f.key === "family" ? (
              <Textarea value={values[f.key] || ""} placeholder={f.placeholder ? `e.g. ${f.placeholder.split("\n")[0]}` : ""} data-testid={`india-doc-field-${f.key}`}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} className="min-h-[64px] bg-background text-sm text-foreground" />
            ) : (
              <Input value={values[f.key] || ""} placeholder={f.placeholder ? `e.g. ${f.placeholder.split("\n")[0]}` : ""} data-testid={`india-doc-field-${f.key}`}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} className="bg-background text-sm text-foreground" />
            )}
          </label>
        ))}
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={make} disabled={busy} data-testid="india-doc-make" className="kb-btn gap-2 font-semibold">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Make it
        </Button>
      </div>
    </>
  );
}

export default function IndiaDocs() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(null);
  useEffect(() => {
    api.get("/docs/templates").then(({ data }) => setList(data?.templates || [])).catch(() => setList([]));
  }, []);
  if (!list.length) return null;
  return (
    <section className="mt-8" data-testid="india-docs">
      <h2 className="text-sm font-semibold">Ready-made Indian documents</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">In the format offices expect. Fill a few boxes or just say it, and download as Word or PDF.</p>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {list.map((d, i) => {
          const Icon = ICONS[d.icon] || Sparkles;
          return (
            <button key={d.id} onClick={() => setOpen(d)} data-testid={`india-doc-${d.id}`}
              className="radha-lift flex flex-col items-start gap-2 rounded-xl border border-border bg-card p-3 text-left hover:border-primary/50">
              <span className={`flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br text-white ${TONES[i % TONES.length]}`}>
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold leading-tight text-foreground">{d.title}</span>
                <span className="block text-[11px] text-muted-foreground">{d.hindi}</span>
              </span>
            </button>
          );
        })}
      </div>
      <Dialog open={!!open} onOpenChange={(o) => { if (!o) setOpen(null); }}>
        <DialogContent className="max-w-lg">
          {open && <DocForm key={open.id} doc={open} onClose={() => setOpen(null)} />}
        </DialogContent>
      </Dialog>
    </section>
  );
}
