import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { AppLogo } from "@/components/BrandLogos";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { ArrowLeft, Check, CheckCircle2, ExternalLink, Loader2, Lock, Search, Send, ShieldCheck } from "lucide-react";

const FILTERS = [["all", "All"], ["connected", "Connected"], ["work", "Work & files"], ["messaging", "Messaging"]];
const PLAN = { pro: "Pro", max: "Max" };
const SITE = { github: "GitHub", notion: "Notion", slack: "Slack", discord: "Discord" };

export function PlanBadge({ plan }) {
  if (!PLAN[plan]) return null;
  return <span className="rounded-full bg-surface-strong px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-brand">{PLAN[plan]}</span>;
}

/** Settings > Connectors: link Krish to outside apps. */
export default function ConnectorsPanel({ onClose }) {
  const [items, setItems] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState(null);

  const load = () => api.get("/connectors").then(({ data }) => setItems(data.connectors))
    .catch((e) => { toast.error(formatApiError(e)); setItems([]); });
  useEffect(() => {
    load();
    const back = new URLSearchParams(window.location.search).get("connected");
    if (back) setOpenId(back);
  }, []);

  const shown = useMemo(() => (items || []).filter((c) => {
    if (filter === "connected" && !c.connected) return false;
    if (filter === "work" && !["work", "files"].includes(c.category)) return false;
    if (filter === "messaging" && c.category !== "messaging") return false;
    const q = query.trim().toLowerCase();
    return !q || `${c.name} ${c.blurb}`.toLowerCase().includes(q);
  }), [items, filter, query]);

  if (items === null) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>;
  const open = items.find((c) => c.id === openId);
  if (open) return <Detail c={open} onBack={() => setOpenId(null)} onChange={setItems} onClose={onClose} />;
  const count = items.filter((c) => c.connected).length;

  return (
    <div data-testid="connectors-panel">
      <div className="mb-5 hidden sm:block">
        <h2 className="font-heading text-[22px] font-semibold tracking-tight">Connectors</h2>
        <p className="mt-1 text-[13.5px] text-muted-foreground">Link your apps so Krish can use them in chats and automations. You can disconnect any time.</p>
      </div>
      <p className="mb-4 text-[13px] text-muted-foreground sm:hidden">Link your apps so Krish can use them in chats and automations.</p>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 sm:pb-0">
          {FILTERS.map(([id, label]) => (
            <button key={id} type="button" onClick={() => setFilter(id)} data-testid={`connectors-filter-${id}`}
              className={`shrink-0 rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                filter === id ? "border-transparent bg-foreground text-background" : "border-border hover:bg-surface"}`}>
              {label}{id === "connected" && count ? ` · ${count}` : ""}
            </button>
          ))}
        </div>
        <label className="relative sm:w-56">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search apps" className="h-9 rounded-full pl-9" data-testid="connectors-search" />
        </label>
      </div>
      {shown.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          {filter === "connected" ? "No apps connected yet." : "No apps match."}</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {shown.map((c) => (
            <button key={c.id} type="button" onClick={() => setOpenId(c.id)} data-testid={`connector-${c.id}`}
              className={`group flex items-center gap-3.5 rounded-2xl border border-border bg-card p-3.5 text-left transition-all hover:border-border-strong hover:shadow-[0_6px_24px_-12px_rgba(15,23,42,0.25)] ${
                !c.ready ? "opacity-70" : ""}`}>
              <AppLogo id={c.id} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-[14px] font-semibold">{c.name} <PlanBadge plan={c.plan} /></span>
                <span className="mt-0.5 line-clamp-2 block text-[12.5px] leading-snug text-muted-foreground">
                  {c.connected && c.account ? c.account : c.blurb}</span>
              </span>
              <Status c={c} />
            </button>
          ))}
        </div>
      )}
      <p className="mt-6 flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        Krish uses a connected app only when you ask it to, or when an automation you made does. Keys are stored encrypted, and disconnecting deletes them.
      </p>
    </div>
  );
}

function Status({ c }) {
  if (c.connected) return <span className="flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[12px] font-medium text-emerald-600 dark:text-emerald-400"><Check className="h-3.5 w-3.5" /> On</span>;
  if (!c.ready) return <span className="shrink-0 rounded-full border border-border px-2.5 py-1 text-[12px] text-muted-foreground">Soon</span>;
  if (c.locked) return <span className="flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[12px] text-muted-foreground"><Lock className="h-3 w-3" /> {PLAN[c.plan]}</span>;
  return <span className="shrink-0 rounded-full border border-border px-3 py-1 text-[12.5px] font-medium transition-colors group-hover:bg-foreground group-hover:text-background">Connect</span>;
}

function Detail({ c, onBack, onChange, onClose }) {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState(null); // { url, code } while waiting for Telegram/WhatsApp
  const poll = useRef(null);
  useEffect(() => () => clearInterval(poll.current), []);

  const fail = (e) => toast.error(formatApiError(e));
  const start = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/connectors/${c.id}/start`);
      if (c.how === "link") {
        setLink(data);
        window.open(data.url, "_blank", "noopener");
        const until = Date.now() + 5 * 60 * 1000;
        clearInterval(poll.current);
        poll.current = setInterval(async () => {
          if (Date.now() > until) { clearInterval(poll.current); return; }
          const { data: d } = await api.get("/connectors").catch(() => ({ data: null }));
          if (d && d.connectors.find((x) => x.id === c.id)?.connected) {
            clearInterval(poll.current);
            setLink(null);
            onChange(d.connectors);
            toast.success(`${c.name} is connected.`);
          }
        }, 3000);
        setBusy(false);
      } else {
        window.location.href = data.url;
      }
    } catch (e) { fail(e); setBusy(false); }
  };
  const paste = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post(`/connectors/${c.id}/connect`, { value });
      onChange(data.connectors);
      setValue("");
      toast.success(`${c.name} is connected.`);
    } catch (err) { fail(err); }
    finally { setBusy(false); }
  };
  const disconnect = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete(`/connectors/${c.id}`);
      onChange(data.connectors);
      toast.success(`${c.name} is disconnected.`);
    } catch (e) { fail(e); }
    finally { setBusy(false); }
  };
  const test = async () => {
    setBusy(true);
    try { await api.post(`/connectors/${c.id}/test`, {}); toast.success(`Sent. Check ${c.name}.`); }
    catch (e) { fail(e); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid={`connector-detail-${c.id}`}>
      <button type="button" onClick={onBack} className="mb-5 flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground hover:text-foreground" data-testid="connector-back">
        <ArrowLeft className="h-4 w-4" /> All connectors
      </button>
      <div className="flex items-center gap-4">
        <AppLogo id={c.id} size="lg" />
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-heading text-[22px] font-semibold tracking-tight">{c.name} <PlanBadge plan={c.plan} /></h2>
          {c.connected
            ? <p className="mt-0.5 flex items-center gap-1.5 text-[13px] text-emerald-600 dark:text-emerald-400"><CheckCircle2 className="h-4 w-4" /> Connected{c.account ? ` as ${c.account}` : ""}</p>
            : <p className="mt-0.5 text-[13px] text-muted-foreground">{c.blurb}</p>}
        </div>
      </div>

      <div className="mt-6 rounded-2xl bg-sunken p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">What Krish can do</p>
        <ul className="mt-2.5 space-y-2">
          {c.does.map((d) => <li key={d} className="flex gap-2.5 text-[13.5px]"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> {d}</li>)}
        </ul>
      </div>

      <div className="mt-6">
        {c.connected ? (
          <div className="flex flex-wrap gap-2">
            {["telegram", "whatsapp", "slack", "discord"].includes(c.id) && (
              <Button variant="outline" onClick={test} disabled={busy} className="h-10" data-testid="connector-test">
                <Send className="mr-1.5 h-4 w-4" /> Send a test message</Button>
            )}
            <Button variant="outline" onClick={disconnect} disabled={busy} data-testid="connector-disconnect"
              className="h-10 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Disconnect"}</Button>
          </div>
        ) : !c.ready ? (
          <p className="rounded-xl border border-dashed border-border p-4 text-[13px] text-muted-foreground">
            {c.name} is coming soon. We're finishing the setup with {c.name.split(" ")[0]}.</p>
        ) : c.locked ? (
          <div className="rounded-2xl border border-border p-4">
            <p className="text-[13.5px]">{c.name} is part of Krish {PLAN[c.plan]}.</p>
            <Button onClick={() => { onClose(); navigate("/plans"); }} className="mt-3 h-10 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 text-white" data-testid="connector-upgrade">
              Upgrade to {PLAN[c.plan]}</Button>
          </div>
        ) : c.how === "token" || c.how === "webhook" ? (
          <form onSubmit={paste}>
            {c.help && (
              <ol className="mb-4 space-y-2">
                {c.help.steps.map((s, i) => (
                  <li key={s} className="flex gap-3 text-[13.5px]">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-strong text-xs font-semibold text-brand">{i + 1}</span>{s}
                  </li>
                ))}
              </ol>
            )}
            {c.help && <a href={c.help.url} target="_blank" rel="noreferrer" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-brand hover:underline">
              Open {SITE[c.id] || c.name} <ExternalLink className="h-3.5 w-3.5" /></a>}
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input value={value} onChange={(e) => setValue(e.target.value)} type={c.how === "token" ? "password" : "url"} autoComplete="off"
                placeholder={c.how === "token" ? (c.id === "github" ? "ghp_…" : "ntn_… or secret_…") : (c.id === "slack" ? "https://hooks.slack.com/services/…" : "https://discord.com/api/webhooks/…")}
                className="h-10 flex-1" data-testid="connector-value" />
              <Button type="submit" disabled={busy || value.trim().length < 8} className="h-10" data-testid="connector-connect">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Connect"}</Button>
            </div>
          </form>
        ) : link ? (
          <div className="rounded-2xl border border-border p-4" data-testid="connector-link">
            <p className="text-[13.5px]">Send this code to Krish in {c.name}. We opened it for you:</p>
            <p className="my-3 font-mono text-2xl font-semibold tracking-[0.3em]">{link.code}</p>
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild className="h-10"><a href={link.url} target="_blank" rel="noreferrer">Open {c.name}</a></Button>
              <span className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Waiting for your message…</span>
            </div>
          </div>
        ) : (
          <Button onClick={start} disabled={busy} className="h-11 rounded-xl px-6" data-testid="connector-connect">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : `Connect ${c.name}`}</Button>
        )}
        {!c.connected && c.ready && !c.locked && c.how === "google" && (
          <p className="mt-3 text-xs text-muted-foreground">You'll sign in on Google's page and choose what Krish may see.</p>
        )}
      </div>
    </div>
  );
}
