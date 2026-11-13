import { useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { LetterLogo } from "@/components/BrandLogos";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, ExternalLink, KeyRound, Link2, Loader2, RefreshCw, Send, ShieldCheck, Webhook } from "lucide-react";

/** Apps added by link (backend custom_connectors.py): MCP app servers and webhook links, with a ready-made list. */

export function customLogo(item, size = "md") {
  return <LetterLogo name={item.name} color={item.color} kind={item.kind} size={size} />;
}

function Back({ onBack }) {
  return (
    <button type="button" onClick={onBack} className="mb-5 flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground hover:text-foreground" data-testid="connector-back">
      <ArrowLeft className="h-4 w-4" /> All connectors
    </button>
  );
}

function Steps({ help, name }) {
  if (!help) return null;
  return (
    <>
      <ol className="mb-4 space-y-2">
        {help.steps.map((s, i) => (
          <li key={s} className="flex gap-3 text-[13.5px]">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-strong text-xs font-semibold text-brand">{i + 1}</span>{s}
          </li>
        ))}
      </ol>
      <a href={help.url} target="_blank" rel="noreferrer" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-brand hover:underline">
        Open {name} <ExternalLink className="h-3.5 w-3.5" /></a>
    </>
  );
}

const fail = (e) => toast.error(formatApiError(e));

/** After adding: go to the app's sign-in page, or show the new connector. */
function afterAdd(data, onDone) {
  if (data.signIn) { window.location.href = data.signIn; return; }
  onDone(data, data.item);
  toast.success(`${data.item.name} is connected.`);
}

/** A ready-made app from the list, not added yet. */
export function DirectoryDetail({ d, full, onBack, onDone }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const connect = async (e) => {
    e?.preventDefault();
    setBusy(true);
    try { afterAdd((await api.post("/connectors/custom", { kind: "mcp", directoryId: d.id, url })).data, onDone); }
    catch (err) { fail(err); setBusy(false); }
  };
  return (
    <div data-testid={`connector-detail-${d.id}`}>
      <Back onBack={onBack} />
      <div className="flex items-center gap-4">
        {customLogo(d, "lg")}
        <div className="min-w-0">
          <h2 className="font-heading text-[22px] font-semibold tracking-tight">{d.name}</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">{d.blurb}</p>
        </div>
      </div>
      <div className="mt-6 rounded-2xl bg-sunken p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Capabilities</p>
        <ul className="mt-2.5 space-y-2 text-[13.5px]">
          <li className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> {d.signIn === "oauth" ? `Secure OAuth 2.1 sign-in on ${d.name}'s own page. Krish never sees your password` : d.signIn === "open" ? "Public server: no sign-in required" : `Authenticated with your personal ${d.name} server URL`}</li>
          <li className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> Every tool {d.name} exposes is discovered automatically, with per-tool permissions</li>
          <li className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> Available in chat and automations. Write actions require your approval by default</li>
        </ul>
      </div>
      <div className="mt-6">
        {full ? <LimitNote /> : d.signIn === "paste" ? (
          <form onSubmit={connect}>
            <Steps help={d.help} name={d.name} />
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input value={url} onChange={(e) => setUrl(e.target.value)} type="password" autoComplete="off" placeholder="https://mcp.zapier.com/api/mcp/s/…"
                className="h-10 flex-1" data-testid="custom-url" />
              <Button type="submit" disabled={busy || !url.trim().startsWith("https://")} className="h-10" data-testid="connector-connect">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Connect"}</Button>
            </div>
          </form>
        ) : (
          <Button onClick={connect} disabled={busy} className="h-11 rounded-xl px-6" data-testid="connector-connect">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : `Connect ${d.name}`}</Button>
        )}
      </div>
    </div>
  );
}

function LimitNote() {
  return <p className="rounded-xl border border-dashed border-border p-4 text-[13px] text-muted-foreground">You've used all custom connector slots on your plan. Remove one, or upgrade for more.</p>;
}

/** Add any app by its link. */
export function AddApp({ full, onBack, onDone }) {
  const [kind, setKind] = useState("mcp");
  const [form, setForm] = useState({ name: "", url: "", key: "", does: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { afterAdd((await api.post("/connectors/custom", { kind, ...form })).data, onDone); }
    catch (err) { fail(err); setBusy(false); }
  };
  const tab = (id, Icon, label) => (
    <button type="button" onClick={() => setKind(id)} data-testid={`custom-kind-${id}`}
      className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${kind === id ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
      <Icon className="h-4 w-4" /> {label}
    </button>
  );
  return (
    <div data-testid="custom-add">
      <Back onBack={onBack} />
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand">Custom connector</p>
      <h2 className="mt-1 font-heading text-[22px] font-semibold tracking-tight">Connect any service</h2>
      <p className="mt-1 text-[13.5px] text-muted-foreground">Add an integration that isn't in the directory. Krish discovers its capabilities and makes them available in chat and automations.</p>
      <div className="mt-5 flex gap-1 rounded-xl bg-sunken p-1">
        {tab("mcp", Link2, "MCP server")}
        {tab("webhook", Webhook, "Webhook")}
      </div>
      <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
        {kind === "mcp"
          ? "Connect any service that exposes a Model Context Protocol (MCP) server, over Streamable HTTP or SSE. If the server uses OAuth, you'll be redirected to authorise Krish."
          : "Send structured JSON to any HTTPS endpoint: a Zapier, Make, n8n or IFTTT hook, or your own API. From there, data can flow to thousands of services."}
      </p>
      {full ? <div className="mt-5"><LimitNote /></div> : (
        <form onSubmit={submit} className="mt-5 space-y-3">
          <label className="block">
            <span className="mb-1 block text-[12.5px] font-medium">Display name</span>
            <Input value={form.name} onChange={set("name")} maxLength={40} placeholder={kind === "mcp" ? "e.g. Store inventory" : "e.g. Add lead to CRM"} className="h-10" data-testid="custom-name" />
          </label>
          <label className="block">
            <span className="mb-1 block text-[12.5px] font-medium">{kind === "mcp" ? "Server URL" : "Endpoint URL"}</span>
            <Input value={form.url} onChange={set("url")} type="url" autoComplete="off" placeholder={kind === "mcp" ? "https://example.com/mcp" : "https://hooks.zapier.com/hooks/catch/…"} className="h-10 font-mono text-[13px]" data-testid="custom-url" />
          </label>
          {kind === "webhook" && (
            <label className="block">
              <span className="mb-1 block text-[12.5px] font-medium">Action description</span>
              <Input value={form.does} onChange={set("does")} maxLength={300} placeholder="e.g. Adds a new customer row to my CRM sheet" className="h-10" data-testid="custom-does" />
              <span className="mt-1 block text-[11.5px] text-muted-foreground">Krish uses this to decide when to call the endpoint.</span>
            </label>
          )}
          <label className="block">
            <span className="mb-1 flex items-center gap-1.5 text-[12.5px] font-medium"><KeyRound className="h-3.5 w-3.5" /> Authentication <span className="font-normal text-muted-foreground">(optional)</span></span>
            <Input value={form.key} onChange={set("key")} type="password" autoComplete="off" placeholder="API key, bearer token, or Header-Name: value" className="h-10" data-testid="custom-key" />
          </label>
          <Button type="submit" disabled={busy || !form.url.trim().startsWith("https://")} className="h-11 w-full rounded-xl sm:w-auto sm:px-6" data-testid="custom-submit">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : kind === "mcp" ? "Connect server" : "Save webhook"}</Button>
        </form>
      )}
      <p className="mt-6 flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        Only connect services you trust. URLs and credentials are encrypted at rest, every request is restricted to public HTTPS addresses, and removing a connector deletes its credentials.
      </p>
    </div>
  );
}

const MODE_LABEL = { on: "Allow", ask: "Approve", off: "Block" };

/** An app the user added: its status, what it can do (each on, ask first or off), sign in again, remove. */
export function CustomDetail({ item, onBack, onChange }) {
  const [busy, setBusy] = useState("");
  const run = async (key, fn) => {
    setBusy(key);
    try { await fn(); } catch (e) { fail(e); } finally { setBusy(""); }
  };
  const setMode = (tool, mode) => run(tool, async () => {
    onChange((await api.patch(`/connectors/custom/${item.id}`, { toolModes: { [tool]: mode } })).data);
  });
  const signIn = () => run("signin", async () => { window.location.href = (await api.post(`/connectors/custom/${item.id}/signin`)).data.signIn; });
  const refresh = () => run("refresh", async () => {
    const { data } = await api.post(`/connectors/custom/${item.id}/refresh`);
    onChange(data);
    const now = data.custom.find((c) => c.id === item.id);
    if (now?.status === "ok") toast.success(`Synced ${now.tools.length} tools.`);
  });
  const remove = () => run("remove", async () => {
    const { data } = await api.delete(`/connectors/custom/${item.id}`);
    onChange(data);
    toast.success(`${item.name} is disconnected.`);
    onBack();
  });
  const test = () => run("test", async () => { await api.post(`/connectors/custom/${item.id}/test`, {}); toast.success("Test payload delivered."); });

  return (
    <div data-testid={`custom-detail-${item.id}`}>
      <Back onBack={onBack} />
      <div className="flex items-center gap-4">
        {customLogo(item, "lg")}
        <div className="min-w-0">
          <h2 className="truncate font-heading text-[22px] font-semibold tracking-tight">{item.name}</h2>
          {item.status === "ok"
            ? <p className="mt-0.5 flex items-center gap-1.5 text-[13px] text-emerald-600 dark:text-emerald-400"><CheckCircle2 className="h-4 w-4 shrink-0" /> <span className="truncate">Active · <span className="font-mono">{item.host}</span></span></p>
            : <p className="mt-0.5 flex items-center gap-1.5 text-[13px] text-amber-600 dark:text-amber-400"><AlertTriangle className="h-4 w-4 shrink-0" /> {item.status === "needs_sign_in" ? "Re-authentication required" : "Server unreachable"}</p>}
        </div>
      </div>
      {item.error && item.status !== "ok" && <p className="mt-4 rounded-xl bg-amber-500/10 p-3 text-[13px] text-amber-700 dark:text-amber-300">{item.error}</p>}

      <dl className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-4">
        {[["Type", item.kind === "webhook" ? "Webhook" : "MCP server"],
          ["Auth", { oauth: "OAuth 2.1", key: "API key", none: "None" }[item.auth] || "None"],
          ["Tools", String(item.tools.length)],
          ["Storage", "Encrypted"]].map(([k, v]) => (
          <div key={k} className="bg-card px-3 py-2.5">
            <dt className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{k}</dt>
            <dd className="mt-0.5 font-mono text-[13px] font-semibold">{v}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-6 rounded-2xl border border-border">
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <p className="text-[13.5px] font-semibold">Tool permissions <span className="ml-1 font-mono text-[12px] font-normal text-muted-foreground">{item.tools.length}</span></p>
            <p className="text-[12px] text-muted-foreground">{item.kind === "webhook" ? "Krish posts a message and JSON data to this endpoint." : "Approve: automations wait for your sign-off before running it."}</p>
          </div>
          {item.kind === "mcp" && (
            <Button variant="outline" size="sm" onClick={refresh} disabled={!!busy} className="h-8 shrink-0 gap-1.5" data-testid="custom-refresh">
              {busy === "refresh" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Re-sync</Button>
          )}
        </div>
        {item.tools.length === 0 ? (
          <p className="px-4 py-6 text-center text-[13px] text-muted-foreground">{item.status === "ok" ? "This server doesn't expose any tools." : "Re-authenticate to load this server's tools."}</p>
        ) : (
          <ul className="divide-y divide-border">
            {item.tools.map((t) => (
              <li key={t.name} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between" data-testid={`custom-tool-${t.name}`}>
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-[13.5px] font-medium">{t.title || t.name}
                    {t.readOnly && <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-px font-mono text-[9.5px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">Read-only</span>}</p>
                  {t.description && <p className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-muted-foreground">{t.description}</p>}
                </div>
                <div className="flex shrink-0 rounded-lg bg-sunken p-0.5" role="radiogroup" aria-label={`${t.title || t.name}`}>
                  {["on", "ask", "off"].map((m) => (
                    <button key={m} type="button" role="radio" aria-checked={t.mode === m} onClick={() => t.mode !== m && setMode(t.name, m)} disabled={busy === t.name}
                      className={`rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors ${t.mode === m ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                      data-testid={`custom-mode-${t.name}-${m}`}>{MODE_LABEL[m]}</button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {item.kind === "mcp" && item.auth === "oauth" && (
          <Button variant={item.status === "needs_sign_in" ? "default" : "outline"} onClick={signIn} disabled={!!busy} className="h-10" data-testid="custom-signin">
            {busy === "signin" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Re-authenticate"}</Button>
        )}
        {item.kind === "webhook" && (
          <Button variant="outline" onClick={test} disabled={!!busy} className="h-10" data-testid="custom-test">
            <Send className="mr-1.5 h-4 w-4" /> Send test payload</Button>
        )}
        <Button variant="outline" onClick={remove} disabled={!!busy} data-testid="custom-remove"
          className="h-10 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive">
          {busy === "remove" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Disconnect"}</Button>
      </div>
    </div>
  );
}
