import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Copy, Database, FileText, Inbox, Loader2, RefreshCw, Trash2, Users } from "lucide-react";
import { api, absoluteUrl, formatApiError } from "@/lib/api";

/**
 * The App Builder's Data tab: what the app has saved in its built-in backend (backend/appcloud.py).
 * Collections, messages sent to the owner (inbox), sign-ups and uploaded files, plus the webhook address
 * other tools (Zapier, Make, n8n, Google Forms) can post to.
 */
export default function DataTab({ appId }) {
  const [info, setInfo] = useState(null);
  const [view, setView] = useState(null); // {kind: "docs"|"users"|"files", name?}
  const [rows, setRows] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/apps/${appId}/data`);
      setInfo(data);
      setView((v) => v || (data.collections[0] ? { kind: "docs", name: data.collections[0].name } : data.users ? { kind: "users" } : null));
    } catch (e) {
      toast.error(formatApiError(e));
    }
  }, [appId]);
  useEffect(() => { load(); }, [load]);

  const viewKey = view ? `${view.kind}:${view.name || ""}` : "";
  useEffect(() => {
    if (!view) return;
    setRows(null);
    const path = view.kind === "docs" ? `docs/${encodeURIComponent(view.name)}` : view.kind;
    api.get(`/apps/${appId}/data/${path}`).then(({ data }) => setRows(data)).catch((e) => toast.error(formatApiError(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, viewKey]);

  const remove = async (row) => {
    const path = view.kind === "docs" ? `docs/${encodeURIComponent(view.name)}/${row.id}` : `${view.kind}/${row.id}`;
    try {
      await api.delete(`/apps/${appId}/data/${path}`);
      setRows((r) => r.filter((x) => x.id !== row.id));
      load();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const copyHook = () => {
    navigator.clipboard.writeText(info.hookUrl);
    setCopied(true);
    toast.success("Webhook address copied");
    setTimeout(() => setCopied(false), 1500);
  };

  if (!info) return <div className="flex h-full items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;

  const item = (key, Icon, label, count, onClick, active) => (
    <button key={key} onClick={onClick} data-testid={`data-nav-${key}`}
      className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs ${active ? "bg-surface-strong font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" /> <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="font-mono text-[10px]">{count}</span>
    </button>
  );

  return (
    <div className="flex h-full min-h-0 max-md:flex-col" data-testid="data-tab">
      <aside className="w-56 shrink-0 space-y-3 overflow-y-auto border-r border-border p-3 max-md:w-full max-md:border-b max-md:border-r-0">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold">Your app's data</p>
          <button onClick={() => { load(); setView((v) => v && { ...v }); }} title="Refresh" className="rounded p-1 text-muted-foreground hover:text-foreground">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="space-y-0.5">
          {info.collections.map((c) => item(`docs-${c.name}`, c.name === "inbox" ? Inbox : Database, c.name === "inbox" ? "Inbox (messages to you)" : c.name,
            c.count, () => setView({ kind: "docs", name: c.name }), view?.kind === "docs" && view.name === c.name))}
          {item("users", Users, "Sign-ups", info.users, () => setView({ kind: "users" }), view?.kind === "users")}
          {item("files", FileText, "Uploaded files", info.files, () => setView({ kind: "files" }), view?.kind === "files")}
        </div>
        <div className="space-y-1.5 rounded-lg border border-border p-2.5 text-[11px] text-muted-foreground">
          <p className="font-medium text-foreground">Connect other tools</p>
          <p>Zapier, Make, n8n or a form can send data here. Replace COLLECTION with a name like <span className="font-mono">leads</span>.</p>
          <button onClick={copyHook} className="flex w-full items-center gap-1.5 rounded-md border border-border bg-sunken px-2 py-1 text-left font-mono text-[10px] hover:text-foreground" data-testid="data-copy-hook">
            {copied ? <Check className="h-3 w-3 shrink-0" /> : <Copy className="h-3 w-3 shrink-0" />}
            <span className="truncate">{info.hookUrl}</span>
          </button>
          {!info.emailReady && <p>Email to you isn't set up on the server yet, so messages only arrive in the Inbox here.</p>}
          {!info.aiReady && <p>AI features in your app need a free AI key on the server.</p>}
        </div>
      </aside>
      <section className="min-h-0 min-w-0 flex-1 overflow-auto p-3">
        {!view ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
            <Database className="h-6 w-6" />
            <p>Nothing saved yet. When people use your app (sign up, send a form, add items), it shows up here.</p>
          </div>
        ) : rows === null ? (
          <Loader2 className="mx-auto mt-10 h-5 w-5 animate-spin text-muted-foreground" />
        ) : rows.length === 0 ? (
          <p className="mt-10 text-center text-sm text-muted-foreground">Empty.</p>
        ) : (
          <ul className="space-y-2" data-testid="data-rows">
            {rows.map((r) => (
              <li key={r.id} className="group rounded-lg border border-border bg-card p-2.5 text-xs">
                <div className="mb-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span>{new Date(r.createdAt).toLocaleString()}</span>
                  {r.private && <span className="rounded bg-surface-strong px-1.5">private</span>}
                  <button onClick={() => remove(r)} title="Delete" className="ml-auto rounded p-1 opacity-60 hover:text-destructive group-hover:opacity-100" data-testid="data-delete">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                {view.kind === "docs" && <pre className="whitespace-pre-wrap break-words font-mono text-[11px]">{JSON.stringify(r.data, null, 2)}</pre>}
                {view.kind === "users" && <p><span className="font-medium">{r.name || "(no name)"}</span> · {r.email}</p>}
                {view.kind === "files" && (
                  <a href={absoluteUrl(r.url)} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-primary hover:underline">
                    {r.type.startsWith("image/") && <img src={absoluteUrl(r.url)} alt="" className="h-10 w-10 rounded object-cover" />}
                    {r.name} <span className="text-muted-foreground">({Math.ceil(r.size / 1024)} KB)</span>
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
