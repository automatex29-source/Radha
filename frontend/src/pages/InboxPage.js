import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHero from "@/components/PageHero";
import IconRail from "@/components/IconRail";
import { AppLogo } from "@/components/BrandLogos";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { ArrowLeft, Bot, Check, Clock, Hand, Inbox, Loader2, Lock, MessageCircle, PauseCircle, Play, Send, Settings2, Sparkles, Trash2, User, X } from "lucide-react";

/** Business inbox: Krish answers the user's customers on Instagram and WhatsApp Business (backend social_inbox.py). */

export function InstagramLogo({ size = "md" }) {
  const box = size === "sm" ? "h-8 w-8 rounded-lg" : size === "xs" ? "h-5 w-5 rounded-md" : "h-11 w-11 rounded-xl";
  const icon = size === "sm" ? "h-[18px] w-[18px]" : size === "xs" ? "h-3 w-3" : "h-6 w-6";
  return (
    <span className={`flex shrink-0 items-center justify-center bg-[radial-gradient(circle_at_30%_107%,#fdf497_0%,#fd5949_45%,#d6249f_60%,#285AEB_90%)] text-white ${box}`} aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={icon}><rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="12" cy="12" r="4" /><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" /></svg>
    </span>
  );
}

const PlatformLogo = ({ platform, size }) => platform === "instagram" ? <InstagramLogo size={size} />
  : <AppLogo id="whatsapp" size={size === "xs" ? "sm" : size} className={size === "xs" ? "!h-5 !w-5 !rounded-md [&_svg]:!h-3 [&_svg]:!w-3" : ""} />;

const MODES = [["off", "Off", "Krish doesn't reply"], ["draft", "Draft", "Krish writes, you approve"], ["auto", "Auto-reply", "Krish replies on its own"]];

const ago = (iso) => {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
};

function loadFacebook(appId) {
  return new Promise((resolve, reject) => {
    if (window.FB) { resolve(window.FB); return; }
    window.fbAsyncInit = () => { window.FB.init({ appId, autoLogAppEvents: true, xfbml: false, version: "v21.0" }); resolve(window.FB); };
    const s = document.createElement("script");
    s.src = "https://connect.facebook.net/en_US/sdk.js";
    s.async = true; s.defer = true; s.crossOrigin = "anonymous";
    s.onerror = () => reject(new Error("Couldn't load Meta's sign-up. Check your connection."));
    document.body.appendChild(s);
  });
}

export default function InboxPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState("");

  const load = useCallback(() => api.get("/social").then(({ data: d }) => setData(d))
    .catch((e) => { toast.error(formatApiError(e)); setData({ accounts: [], threads: [], ready: {}, locked: false }); }), []);
  useEffect(() => {
    load();
    const q = new URLSearchParams(window.location.search);
    if (q.get("error")) toast.error(q.get("error"));
    if (q.get("connected")) toast.success("Instagram is connected.");
    if (q.get("error") || q.get("connected")) window.history.replaceState(null, "", "/inbox");
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const threads = useMemo(() => (data?.threads || []).filter((t) =>
    filter === "needs" ? t.handoff : filter === "drafts" ? t.drafts > 0 : true), [data, filter]);

  const connectInstagram = async () => {
    setBusy("instagram");
    try { window.location.href = (await api.post("/social/instagram/start")).data.url; }
    catch (e) { toast.error(formatApiError(e)); setBusy(""); }
  };
  const connectWhatsApp = async () => {
    const cfg = data?.whatsappSignup;
    if (!cfg) return;
    setBusy("whatsapp");
    let session = null;
    const onMsg = (e) => {
      if (!/facebook\.com$/.test(new URL(e.origin).hostname)) return;
      try { const d = JSON.parse(e.data); if (d.type === "WA_EMBEDDED_SIGNUP" && d.event === "FINISH") session = d.data; } catch { /* other messages */ }
    };
    window.addEventListener("message", onMsg);
    try {
      const FB = await loadFacebook(cfg.appId);
      FB.login(async (res) => {
        window.removeEventListener("message", onMsg);
        const code = res?.authResponse?.code;
        if (!code || !session?.phone_number_id) { setBusy(""); if (code) toast.error("Pick a WhatsApp number to finish."); return; }
        try {
          const { data: d } = await api.post("/social/whatsapp/connect", { code, phoneNumberId: session.phone_number_id, wabaId: session.waba_id });
          setData(d); toast.success("WhatsApp Business is connected.");
        } catch (e) { toast.error(formatApiError(e)); }
        setBusy("");
      }, { config_id: cfg.configId, response_type: "code", override_default_response_type: true, extras: { setup: {}, sessionInfoVersion: "3" } });
    } catch (e) { window.removeEventListener("message", onMsg); toast.error(e.message); setBusy(""); }
  };

  if (!data) return <Shell><div className="flex flex-1 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div></Shell>;
  const open = data.threads.find((t) => t.id === openId);
  const waiting = data.threads.filter((t) => t.handoff || t.drafts > 0).length;
  const has = (p) => data.accounts.some((a) => a.platform === p);

  return (
    <Shell>
      <div className={`radha-scroll w-full max-w-md shrink-0 overflow-y-auto border-r border-border p-5 max-md:max-w-none max-md:border-r-0 max-md:p-4 ${open ? "max-md:hidden" : ""}`}>
        <PageHero compact scene="inbox" icon={Inbox} title="Business inbox" testid="inbox-hero"
          subtitle="Krish answers your customers on Instagram and WhatsApp, in your words, around the clock." />

        <div className="mt-4 space-y-2.5">
          {data.accounts.map((a) => <AccountCard key={a.id} a={a} onChange={setData} />)}
          {!has("instagram") && <ConnectCard platform="instagram" name="Instagram" blurb="Business or creator account · DMs"
            ready={data.ready.instagram} locked={data.locked} busy={busy === "instagram"} onConnect={connectInstagram} onUpgrade={() => navigate("/plans")} />}
          {!has("whatsapp") && <ConnectCard platform="whatsapp" name="WhatsApp Business" blurb="Your business number · Cloud API"
            ready={data.ready.whatsapp} locked={data.locked} busy={busy === "whatsapp"} onConnect={connectWhatsApp} onUpgrade={() => navigate("/plans")} />}
        </div>

        {data.accounts.length > 0 && (
          <div className="mt-4 grid grid-cols-3 gap-2" data-testid="inbox-stats">
            {[[data.threads.length, "Chats"], [waiting, "Need you"], [`${data.repliesToday}/${data.dailyLimit}`, "Replies today"]].map(([v, k]) => (
              <div key={k} className="rounded-xl border border-border bg-card px-3 py-2.5">
                <p className="font-mono text-[17px] font-semibold tabular-nums">{v}</p>
                <p className="text-[10.5px] uppercase tracking-[0.1em] text-muted-foreground">{k}</p>
              </div>
            ))}
          </div>
        )}

        {data.accounts.length > 0 && (
          <>
            <div className="mb-2 mt-5 flex gap-1.5">
              {[["all", "All"], ["needs", "Needs you"], ["drafts", "Drafts"]].map(([id, label]) => (
                <button key={id} type="button" onClick={() => setFilter(id)} data-testid={`inbox-filter-${id}`}
                  className={`rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition-colors ${filter === id ? "border-transparent bg-foreground text-background" : "border-border text-muted-foreground hover:bg-surface"}`}>{label}</button>
              ))}
            </div>
            {threads.length === 0 ? (
              <p className="rounded-xl border border-dashed border-border p-6 text-center text-[13px] text-muted-foreground">
                {data.threads.length ? "Nothing here right now." : "No customer messages yet. When someone writes to you, the chat appears here."}</p>
            ) : (
              <div className="space-y-1.5">
                {threads.map((t) => (
                  <button key={t.id} type="button" onClick={() => setOpenId(t.id)} data-testid={`thread-${t.id}`}
                    className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors ${t.id === openId ? "border-primary/50 bg-primary/5" : "border-border bg-card hover:border-primary/30"}`}>
                    <span className="relative">
                      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-strong text-[14px] font-semibold text-brand">{(t.contactName || "?").replace("+", "")[0]?.toUpperCase()}</span>
                      <span className="absolute -bottom-0.5 -right-0.5"><PlatformLogo platform={t.platform} size="xs" /></span>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className={`truncate text-[13.5px] ${t.unread ? "font-bold" : "font-semibold"}`}>{t.contactName || "Customer"}</span>
                        <span className="shrink-0 text-[11px] text-muted-foreground">{ago(t.lastAt)}</span>
                      </span>
                      <span className="mt-0.5 block truncate text-[12.5px] text-muted-foreground">{t.preview}</span>
                      <span className="mt-1 flex flex-wrap gap-1">
                        {t.handoff && <Chip tone="rose" icon={Hand}>Needs you</Chip>}
                        {t.drafts > 0 && <Chip tone="amber" icon={Sparkles}>Draft ready</Chip>}
                        {t.paused && !t.handoff && <Chip icon={PauseCircle}>Krish paused</Chip>}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        <p className="mt-6 text-[11.5px] leading-relaxed text-muted-foreground">
          Uses Meta's official Instagram and WhatsApp Business APIs. Krish can reply within 24 hours of a customer's last message, as Meta allows, and never uses your other apps or private notes in these chats.
        </p>
      </div>
      <div className={`min-w-0 flex-1 ${open ? "" : "max-md:hidden"}`}>
        {open ? <ThreadView key={open.id} thread={open} onBack={() => setOpenId(null)} onChanged={load} /> : <Empty />}
      </div>
    </Shell>
  );
}

function Shell({ children }) {
  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col" data-testid="inbox-page">
      <IconRail />
      <div className="flex min-h-0 min-w-0 flex-1">{children}</div>
    </div>
  );
}

function Chip({ tone, icon: Icon, children }) {
  const c = tone === "rose" ? "bg-rose-500/10 text-rose-600 dark:text-rose-400" : tone === "amber" ? "bg-amber-500/10 text-amber-700 dark:text-amber-400" : "bg-surface-strong text-muted-foreground";
  return <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10.5px] font-semibold ${c}`}><Icon className="h-3 w-3" />{children}</span>;
}

function ConnectCard({ platform, name, blurb, ready, locked, busy, onConnect, onUpgrade }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-dashed border-border-strong bg-card p-3.5" data-testid={`connect-${platform}`}>
      <PlatformLogo platform={platform} />
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-semibold">{name}</p>
        <p className="text-[12px] text-muted-foreground">{blurb}</p>
      </div>
      {locked ? <Button size="sm" variant="outline" onClick={onUpgrade} className="h-8 gap-1"><Lock className="h-3 w-3" /> Pro</Button>
        : !ready ? <span className="rounded-lg border border-border px-2.5 py-1 text-[12px] text-muted-foreground">Coming soon</span>
          : <Button size="sm" onClick={onConnect} disabled={busy} className="h-8">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Connect"}</Button>}
    </div>
  );
}

function AccountCard({ a, onChange }) {
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(a.instructions);
  const [busy, setBusy] = useState(false);
  const save = async (patch) => {
    setBusy(true);
    try { onChange((await api.patch(`/social/accounts/${a.id}`, patch)).data); if (patch.instructions !== undefined) { setEdit(false); toast.success("Instructions saved."); } }
    catch (e) { toast.error(formatApiError(e)); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { onChange((await api.delete(`/social/accounts/${a.id}`)).data); toast.success(`${a.platformName} disconnected.`); }
    catch (e) { toast.error(formatApiError(e)); setBusy(false); }
  };
  return (
    <div className="rounded-xl border border-border bg-card p-3.5" data-testid={`account-${a.platform}`}>
      <div className="flex items-center gap-3">
        <PlatformLogo platform={a.platform} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-semibold">{a.name}</p>
          <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
            <span className={`h-1.5 w-1.5 rounded-full ${a.mode === "auto" ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.9)]" : a.mode === "draft" ? "bg-amber-500" : "bg-muted-foreground/50"}`} />
            {a.platformName} · {MODES.find((m) => m[0] === a.mode)?.[2]}
          </p>
        </div>
        <button type="button" onClick={() => setEdit(!edit)} className="rounded-lg p-2 text-muted-foreground hover:bg-surface hover:text-foreground" aria-label="Instructions" data-testid={`account-edit-${a.platform}`}><Settings2 className="h-4 w-4" /></button>
      </div>
      <div className="mt-3 flex rounded-lg bg-sunken p-0.5" role="radiogroup" aria-label="Reply mode">
        {MODES.map(([id, label]) => (
          <button key={id} type="button" role="radio" aria-checked={a.mode === id} disabled={busy} onClick={() => a.mode !== id && save({ mode: id })} data-testid={`mode-${a.platform}-${id}`}
            className={`flex-1 rounded-md px-2 py-1.5 text-[12px] font-medium transition-colors ${a.mode === id ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>{label}</button>
        ))}
      </div>
      {edit && (
        <div className="mt-3">
          <p className="mb-1 text-[12px] font-medium">How Krish should reply</p>
          <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} className="text-[13px]" data-testid={`instructions-${a.platform}`}
            placeholder="Who you are, what you sell, prices, timings, delivery areas, your tone, and when to hand a chat to you." />
          <div className="mt-2 flex items-center justify-between gap-2">
            <button type="button" onClick={remove} disabled={busy} className="text-[12px] font-medium text-destructive hover:underline">Disconnect</button>
            <Button size="sm" onClick={() => save({ instructions: text })} disabled={busy} className="h-8">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save instructions"}</Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Empty() {
  return (
    <div className="flex h-full flex-col items-center justify-center p-8 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-strong text-brand"><MessageCircle className="h-7 w-7" /></span>
      <p className="mt-4 text-[15px] font-semibold">Pick a chat</p>
      <p className="mt-1 max-w-xs text-[13px] text-muted-foreground">See what customers asked, what Krish replied, and approve drafts before they're sent.</p>
    </div>
  );
}

function ThreadView({ thread, onBack, onChanged }) {
  const [data, setData] = useState(null);
  const [text, setText] = useState("");
  const [draftText, setDraftText] = useState(null);
  const [busy, setBusy] = useState("");
  const end = useRef(null);
  const load = useCallback(() => api.get(`/social/threads/${thread.id}`).then(({ data: d }) => setData(d)).catch((e) => toast.error(formatApiError(e))), [thread.id]);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [data?.messages?.length]);
  const act = async (key, fn, ok) => {
    setBusy(key);
    try { setData((await fn()).data); onChanged(); if (ok) toast.success(ok); } catch (e) { toast.error(formatApiError(e)); } finally { setBusy(""); }
  };
  if (!data) return <div className="flex h-full items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>;
  const t = data.thread;
  const draft = data.messages.find((m) => m.status === "draft");
  const shown = data.messages.filter((m) => m.status !== "draft" && m.status !== "declined");

  return (
    <div className="flex h-full flex-col" data-testid="thread-view">
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <button type="button" onClick={onBack} className="rounded-lg p-1.5 hover:bg-surface md:hidden" aria-label="Back"><ArrowLeft className="h-5 w-5" /></button>
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-strong text-[13px] font-semibold text-brand">{(t.contactName || "?").replace("+", "")[0]?.toUpperCase()}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-semibold">{t.contactName || "Customer"}</p>
          <p className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground"><PlatformLogo platform={t.platform} size="xs" /> {t.platform === "instagram" ? "Instagram" : "WhatsApp Business"}
            {!t.canReply && <span className="flex items-center gap-1"> · <Clock className="h-3 w-3" /> reply window closed</span>}</p>
        </div>
        {(t.handoff || t.paused) && (
          <Button size="sm" variant="outline" onClick={() => act("resume", () => api.post(`/social/threads/${t.id}/resume`), "Krish will reply here again.")} disabled={!!busy} className="h-8 gap-1" data-testid="thread-resume">
            <Play className="h-3.5 w-3.5" /> Let Krish reply</Button>
        )}
      </div>
      {t.handoff && <p className="flex items-center gap-2 bg-rose-500/10 px-4 py-2 text-[12.5px] text-rose-700 dark:text-rose-300"><Hand className="h-4 w-4 shrink-0" /> Krish handed this chat to you. Reply below, then let Krish continue if you like.</p>}
      {t.paused && !t.handoff && <p className="flex items-center gap-2 bg-surface-strong px-4 py-2 text-[12.5px] text-muted-foreground"><PauseCircle className="h-4 w-4 shrink-0" /> You replied yourself, so Krish is paused in this chat for 12 hours.</p>}

      <div className="radha-scroll flex-1 space-y-2.5 overflow-y-auto px-4 py-4">
        {shown.map((m) => (
          <div key={m.id} className={`flex ${m.direction === "in" ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-[13.5px] leading-snug ${m.direction === "in" ? "rounded-bl-md bg-surface-strong" : "rounded-br-md bg-gradient-to-br from-indigo-500 to-violet-500 text-white"}`}>
              <p className="whitespace-pre-wrap break-words">{m.text}</p>
              <p className={`mt-1 flex items-center gap-1 text-[10.5px] ${m.direction === "in" ? "text-muted-foreground" : "text-white/70"}`}>
                {m.direction === "out" && (m.by === "krish" ? <><Bot className="h-3 w-3" /> Krish</> : <><User className="h-3 w-3" /> You</>)} {m.direction === "out" && "·"} {ago(m.sentAt || m.createdAt)}
              </p>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>

      {draft && (
        <div className="mx-4 mb-3 rounded-xl border border-amber-500/40 bg-amber-500/5 p-3" data-testid="thread-draft">
          <p className="flex items-center gap-1.5 text-[12px] font-semibold text-amber-700 dark:text-amber-400"><Sparkles className="h-3.5 w-3.5" /> Krish's draft: review before sending</p>
          <Textarea rows={3} value={draftText ?? draft.text} onChange={(e) => setDraftText(e.target.value)} className="mt-2 bg-card text-[13px]" data-testid="thread-draft-text" />
          <div className="mt-2 flex gap-2">
            <Button size="sm" disabled={!!busy || !t.canReply} onClick={() => act("send", () => api.post(`/social/threads/${t.id}/drafts/${draft.id}/send`, { text: draftText ?? draft.text }), "Sent.")} className="h-8 gap-1.5" data-testid="thread-draft-send">
              {busy === "send" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Approve & send</Button>
            <Button size="sm" variant="outline" disabled={!!busy} onClick={() => act("discard", () => api.delete(`/social/threads/${t.id}/drafts/${draft.id}`))} className="h-8 gap-1.5"><Trash2 className="h-3.5 w-3.5" /> Discard</Button>
          </div>
        </div>
      )}

      <form className="flex items-end gap-2 border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); if (text.trim()) act("reply", () => api.post(`/social/threads/${t.id}/reply`, { text }), null).then(() => setText("")); }}>
        <Textarea rows={1} value={text} onChange={(e) => setText(e.target.value)} disabled={!t.canReply} data-testid="thread-reply"
          placeholder={t.canReply ? "Write a reply yourself" : "Meta allows replies only within 24 hours of the customer's last message"}
          className="min-h-[40px] flex-1 resize-none text-[13.5px]" />
        <Button type="submit" size="icon" disabled={!t.canReply || !text.trim() || !!busy} className="h-10 w-10 shrink-0" aria-label="Send">
          {busy === "reply" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</Button>
      </form>
    </div>
  );
}
