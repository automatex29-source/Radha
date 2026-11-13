import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { AppLogo } from "@/components/BrandLogos";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, ExternalLink, Loader2, Lock, Plus, Search, Send, ShieldCheck } from "lucide-react";
import { AddApp, CustomDetail, DirectoryDetail, customLogo } from "@/components/settings/CustomConnectors";

const FILTERS = [["all", "All"], ["connected", "Connected"], ["work", "Work & files"], ["messaging", "Messaging"], ["developer", "Developer"]];
const WORK = ["work", "files", "money", "automation"];
const PLAN = { pro: "Pro", max: "Max" };
const SITE = { github: "GitHub", notion: "Notion", slack: "Slack", discord: "Discord" };

export function PlanBadge({ plan }) {
  if (!PLAN[plan]) return null;
  return <span className="rounded-full bg-surface-strong px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-brand">{PLAN[plan]}</span>;
}

/** Settings > Connectors: link Krish to outside apps. */
export default function ConnectorsPanel({ onClose }) {
  const [items, setItems] = useState(null);
  const [own, setOwn] = useState(null); // apps added by link, and the ready-made list (custom_connectors.py)
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState(null);

  const load = () => {
    api.get("/connectors").then(({ data }) => setItems(data.connectors))
      .catch((e) => { toast.error(formatApiError(e)); setItems([]); });
    api.get("/connectors/custom").then(({ data }) => setOwn(data))
      .catch(() => setOwn({ custom: [], directory: [], limit: 0 }));
  };
  useEffect(() => {
    load();
    let back = new URLSearchParams(window.location.search).get("connected");
    try { back = back || sessionStorage.getItem("krish-connected"); sessionStorage.removeItem("krish-connected"); } catch { /* private mode */ }
    if (back) setOpenId(back);
  }, []);

  // One list: the built-in apps, the ready-made apps that connect by link, and the apps the user added.
  const all = useMemo(() => {
    if (!items || !own) return [];
    const added = own.custom.map((x) => {
      const d = own.directory.find((y) => y.id === x.directoryId);
      return { key: `custom:${x.id}`, name: x.name, blurb: x.kind === "webhook" ? (x.does || "Webhook link") : (d?.blurb || x.host),
        category: d?.category || "work", connected: true, warn: x.status !== "ok", logo: customLogo(x), item: x,
        tag: x.kind === "webhook" ? "Webhook" : `MCP · ${x.auth === "oauth" ? "OAuth" : x.auth === "key" ? "API key" : "Open"}` };
    });
    const ready = own.directory.filter((d) => !d.added).map((d) => ({ key: `dir:${d.id}`, name: d.name, blurb: d.blurb,
      category: d.category, connected: false, logo: customLogo(d), dir: d,
      tag: `MCP · ${d.signIn === "oauth" ? "OAuth" : d.signIn === "paste" ? "Personal URL" : "Open"}` }));
    const builtIn = items.map((c) => ({ key: c.id, name: c.name, blurb: c.connected && c.account ? c.account : c.blurb,
      category: c.category, connected: c.connected, logo: <AppLogo id={c.id} />, c,
      tag: { google: "OAuth", oauth: "OAuth", token: "API token", webhook: "Webhook", link: "Bot link" }[c.how] || "Native" }));
    return [...builtIn, ...ready, ...added];
  }, [items, own]);

  const shown = useMemo(() => all.filter((c) => {
    if (filter === "connected" && !c.connected) return false;
    if (filter === "work" && !WORK.includes(c.category)) return false;
    if (filter === "messaging" && c.category !== "messaging") return false;
    if (filter === "developer" && c.category !== "developer") return false;
    const q = query.trim().toLowerCase();
    return !q || `${c.name} ${c.blurb}`.toLowerCase().includes(q);
  }), [all, filter, query]);

  if (items === null || own === null) return <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>;
  const full = own.custom.length >= own.limit;
  const back = () => setOpenId(null);
  const onOwn = (data, item) => { setOwn(data); if (item) setOpenId(`custom:${item.id}`); };
  if (openId === "new") return <AddApp full={full} onBack={back} onDone={onOwn} />;
  if (openId?.startsWith("custom:")) {
    const item = own.custom.find((x) => x.id === openId.slice(7));
    if (item) return <CustomDetail item={item} onBack={back} onChange={setOwn} />;
  }
  if (openId?.startsWith("dir:")) {
    const d = own.directory.find((x) => x.id === openId.slice(4));
    const item = d && own.custom.find((x) => x.directoryId === d.id);
    if (item) return <CustomDetail item={item} onBack={back} onChange={setOwn} />;
    if (d) return <DirectoryDetail d={d} full={full} onBack={back} onDone={onOwn} />;
  }
  const open = items.find((c) => c.id === openId);
  if (open) return <Detail c={open} onBack={back} onChange={setItems} onClose={onClose} />;
  const count = all.filter((c) => c.connected).length;

  const active = all.filter((x) => x.connected);
  const sections = [
    ["Active connections", "Live and available to Krish", shown.filter((x) => x.connected)],
    ["Built-in integrations", "Native connectors maintained by Krish", shown.filter((x) => x.c && !x.connected)],
    ["MCP directory", "Popular services that connect over the Model Context Protocol", shown.filter((x) => x.dir)],
  ].filter(([, , list]) => list.length);

  return (
    <div data-testid="connectors-panel">
      <div className="relative mb-5 overflow-hidden rounded-2xl border border-indigo-500/20 bg-[radial-gradient(120%_140%_at_0%_0%,#1e1b4b_0%,#0b1020_55%,#05070d_100%)] p-5 text-white shadow-[0_20px_60px_-30px_rgba(79,70,229,0.7)] sm:p-6">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 opacity-[0.18] [background-image:linear-gradient(rgba(148,163,184,0.35)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.35)_1px,transparent_1px)] [background-size:22px_22px] [mask-image:radial-gradient(70%_90%_at_85%_20%,black,transparent)]" />
        <div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-16 h-48 w-48 rounded-full bg-violet-500/30 blur-3xl" />
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-200/80">
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" /></span>
              Integration hub
            </p>
            <h2 className="mt-2 font-heading text-[22px] font-semibold tracking-tight sm:text-[26px]">Connectors</h2>
            <p className="mt-1 max-w-md text-[13px] leading-relaxed text-slate-300">Connect your tools and data sources. Krish can read from them, take action in them and automate work across them.</p>
          </div>
          <Button onClick={() => setOpenId("new")} className="h-10 shrink-0 gap-1.5 rounded-xl bg-white px-4 text-slate-900 hover:bg-indigo-50" data-testid="custom-add-open">
            <Plus className="h-4 w-4" /> Add custom connector</Button>
        </div>
        <dl className="relative mt-5 grid grid-cols-3 gap-2 border-t border-white/10 pt-4">
          {[[active.length, "Active"], [all.length, "Available"], [`${own.custom.length}/${own.limit}`, "Custom"]].map(([v, k]) => (
            <div key={k}>
              <dt className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-slate-400">{k}</dt>
              <dd className="mt-0.5 font-mono text-[18px] font-semibold tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 sm:pb-0">
          {FILTERS.map(([id, label]) => (
            <button key={id} type="button" onClick={() => setFilter(id)} data-testid={`connectors-filter-${id}`}
              className={`shrink-0 rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                filter === id ? "border-transparent bg-foreground text-background" : "border-border text-muted-foreground hover:bg-surface hover:text-foreground"}`}>
              {label}{id === "connected" && count ? ` · ${count}` : ""}
            </button>
          ))}
        </div>
        <label className="relative sm:w-60">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search integrations" className="h-9 rounded-lg pl-9" data-testid="connectors-search" />
        </label>
      </div>
      {shown.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          {filter === "connected" ? "No active connections yet." : "No integrations match your search."}</p>
      ) : sections.map(([title, hint, list]) => (
        <section key={title} className="mb-6">
          <div className="mb-2.5 flex items-baseline justify-between gap-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title} <span className="ml-1 font-mono text-foreground/60">{list.length}</span></h3>
            <p className="hidden truncate text-[11.5px] text-muted-foreground sm:block">{hint}</p>
          </div>
          <div className="grid gap-2.5 lg:grid-cols-2">
            {list.map((x) => (
              <button key={x.key} type="button" onClick={() => setOpenId(x.key)} data-testid={`connector-${x.key}`}
                className={`group relative flex items-center gap-3.5 rounded-xl border bg-card p-3.5 text-left transition-all hover:-translate-y-px hover:border-indigo-400/50 hover:shadow-[0_10px_30px_-18px_rgba(79,70,229,0.55)] ${
                  x.connected ? "border-emerald-500/25" : "border-border"} ${x.c && !x.c.ready ? "opacity-70" : ""}`}>
                {x.logo}
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-[14px] font-semibold">{x.name} {x.c && <PlanBadge plan={x.c.plan} />}</span>
                  <span className="mt-0.5 line-clamp-1 block text-[12.5px] leading-snug text-muted-foreground">{x.blurb}</span>
                  <span className="mt-1.5 inline-flex rounded-md border border-border bg-sunken px-1.5 py-px font-mono text-[10px] uppercase tracking-wide text-muted-foreground">{x.tag}</span>
                </span>
                {x.c ? <Status c={x.c} /> : x.warn
                  ? <span className="flex shrink-0 items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-1 text-[12px] font-medium text-amber-600 dark:text-amber-400"><AlertTriangle className="h-3.5 w-3.5" /> Action needed</span>
                  : <Status c={{ connected: x.connected, ready: true }} />}
              </button>
            ))}
          </div>
        </section>
      ))}
      <button type="button" onClick={() => setOpenId("new")} data-testid="custom-add-card"
        className="group flex w-full items-center gap-3.5 rounded-xl border border-dashed border-indigo-400/40 bg-indigo-500/[0.03] p-4 text-left transition-colors hover:bg-indigo-500/[0.07]">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_8px_20px_-8px_rgba(99,102,241,0.8)]"><Plus className="h-5 w-5" /></span>
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-semibold">Add a custom connector</span>
          <span className="mt-0.5 block text-[12.5px] leading-snug text-muted-foreground">Connect any MCP server, or route data through a Zapier, Make or n8n webhook to reach thousands of services.</span>
        </span>
        <span className="hidden shrink-0 font-mono text-[11px] text-muted-foreground sm:block">{own.custom.length}/{own.limit} used</span>
      </button>
      <p className="mt-6 flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
        Credentials are encrypted at rest and used only when you, or an automation you created, make a request. Disconnect at any time to revoke access.
      </p>
    </div>
  );
}

function Status({ c }) {
  if (c.connected) return <span className="flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[12px] font-medium text-emerald-600 dark:text-emerald-400"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.9)]" /> Active</span>;
  if (!c.ready) return <span className="shrink-0 rounded-full border border-border px-2.5 py-1 text-[12px] text-muted-foreground">Coming soon</span>;
  if (c.locked) return <span className="flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[12px] text-muted-foreground"><Lock className="h-3 w-3" /> {PLAN[c.plan]}</span>;
  return <span className="shrink-0 rounded-lg border border-border px-3 py-1 text-[12.5px] font-medium transition-colors group-hover:border-transparent group-hover:bg-foreground group-hover:text-background">Connect</span>;
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
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Capabilities</p>
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
            {c.name} is coming soon. The integration is being finalised.</p>
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
          <p className="mt-3 text-xs text-muted-foreground">You'll authorise access securely on Google's page and choose what Krish may see.</p>
        )}
      </div>
    </div>
  );
}
