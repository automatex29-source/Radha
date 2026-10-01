import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Loader2, Sparkles, Plus } from "lucide-react";

/** Someone shared an assistant: show what it does and let the viewer add their own copy. */
export default function AssistantInvite() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/assistants/${code}`).then(({ data }) => setInfo(data)).catch((e) => setError(formatApiError(e)));
  }, [code]);

  const add = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/assistants/${code}/copy`);
      toast.success(`${data.name} added to your projects`);
      navigate(`/?project=${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
      setBusy(false);
    }
  };

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <div className="radha-scroll flex flex-1 items-center justify-center overflow-y-auto px-4 py-10">
        <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-sm" data-testid="assistant-invite">
          {error ? <p className="text-sm text-muted-foreground">{error}</p> : !info ? (
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-primary" />
          ) : (
            <>
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-primary"><Sparkles className="h-3.5 w-3.5" /> Shared assistant</p>
              <h1 className="mt-2 text-2xl font-bold tracking-tight">{info.name}</h1>
              {info.by && <p className="mt-0.5 text-xs text-muted-foreground">Made by {info.by}</p>}
              {info.description && <p className="mt-3 text-sm">{info.description}</p>}
              {info.instructions && (
                <div className="mt-4 rounded-lg bg-surface p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">How it behaves</p>
                  <p className="mt-1 line-clamp-6 whitespace-pre-wrap text-xs text-muted-foreground">{info.instructions}</p>
                </div>
              )}
              <Button onClick={add} disabled={busy} data-testid="add-assistant-button" className="mt-5 w-full gap-2 font-semibold">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add to my Krish AI
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
