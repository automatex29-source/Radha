import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { toast } from "sonner";
import { Bug, CheckCircle2, LifeBuoy, Loader2, MessageSquareHeart, Search, Send, Star, CircleHelp } from "lucide-react";

const FAQS = [
  { q: "What is Krish AI?", a: "Krish AI by EmpireX is your AI helper. Chat to ask anything, make presentations in Decks, build small apps in Apps, let Automations do tasks for you on a schedule, and use Talk it out when you just need someone to talk to." },
  { q: "Is Krish AI free?", a: "Yes. Krish AI is free to use right now. Some premium AI models need a paid plan, which we will add later." },
  { q: "I forgot my password. What do I do?", a: "On the sign-in page, tap \"Forgot password?\" and enter your email. We'll send you a link to choose a new password. The link works once and expires soon, so use it right away. Check your spam folder if you don't see it." },
  { q: "Why is the AI slow, or why did it stop answering?", a: "The free AI models are shared, so they can be busy for a moment. Wait a few seconds and send your message again, or pick another model from the model menu above the chat box. If it keeps happening, report a bug here." },
  { q: "What is Talk it out?", a: "Talk it out is a warm friend to talk to when you're stressed, sad or confused. It listens, helps you feel better and shares wisdom from the Bhagavad Gita when it helps. It is not a doctor. In an emergency in India, call Tele-MANAS 14416 (free, 24x7) or 112." },
  { q: "How do I make a presentation?", a: "Open Decks, type your topic (or add notes, a file, a web page or a YouTube link), check the outline, pick a style and tap Create. You can edit slides and download a real PowerPoint file." },
  { q: "What are Automations?", a: "An automation is a task Krish AI does for you on its own, for example a news brief every morning or a weekly price check. Open Automations, describe the task, choose when it should run, and it can email you the result." },
  { q: "Does Krish AI remember things about me?", a: "Krish AI can remember useful facts you share, like your name or your business, so answers fit you better. Open the menu with your name and choose Memory to see or delete what it remembers." },
  { q: "How do I share a chat?", a: "Open the chat and tap the share button at the top. Anyone with the link can read that chat, and you can stop sharing at any time." },
  { q: "Is my data safe?", a: "Your chats and files are private to your account and are never shown to other people unless you share a link. Your password is stored in a scrambled form, so even we can't read it." },
  { q: "How do I delete my account or my data?", a: "You can delete any chat from the chat list. To delete your whole account, send us a message from \"Send feedback\" below and we'll do it for you." },
];

const AREAS = ["Chat", "Projects", "Apps", "Decks", "Automations", "Talk it out", "Sign in", "Other"];
const SECTIONS = [
  { id: "faq", label: "FAQs", Icon: CircleHelp },
  { id: "bug", label: "Report a bug", short: "Report bug", Icon: Bug },
  { id: "feedback", label: "Send feedback", short: "Feedback", Icon: MessageSquareHeart },
];
const KIND_LABEL = { bug: "Bug report", feedback: "Feedback", question: "Question" };

function Chip({ active, onClick, children, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
        active ? "border-primary bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground"}`}>
      {children}
    </button>
  );
}

function deviceInfo() {
  const w = typeof window !== "undefined" ? `${window.innerWidth}x${window.innerHeight}` : "";
  return `${navigator.userAgent} · ${w}`.slice(0, 400);
}

function ReportForm({ kind, onSent }) {
  const bug = kind === "bug";
  const [area, setArea] = useState("");
  const [rating, setRating] = useState(0);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (message.trim().length < 3) return toast.error(bug ? "Please tell us what went wrong." : "Please write a few words.");
    setBusy(true);
    try {
      await api.post("/help/reports", {
        kind, message: message.trim(), area: area || null, rating: rating || null,
        device: deviceInfo(),
      });
      setSent(true);
      setMessage(""); setArea(""); setRating(0);
      onSent();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-border bg-card px-6 py-10 text-center shadow-sm" data-testid="help-sent">
        <CheckCircle2 className="h-10 w-10 text-emerald-500" />
        <h3 className="mt-3 text-lg font-bold">{bug ? "Thanks, we got your report" : "Thanks for your feedback"}</h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          {bug ? "Our team will look into it. If we need more details, we'll email you." : "Every message is read by the EmpireX team and helps make Krish AI better."}
        </p>
        <Button variant="outline" className="mt-5 rounded-xl" onClick={() => setSent(false)}>Send another</Button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-border bg-card p-5 shadow-sm" data-testid={`help-form-${kind}`}>
      <h2 className="text-lg font-bold">{bug ? "Report a bug" : "Send feedback"}</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {bug ? "Something not working? Tell us what happened and we'll fix it." : "Love something, miss something, or have an idea? We'd love to hear it."}
      </p>

      {!bug && (
        <div className="mt-5">
          <p className="text-sm font-medium">How do you like Krish AI?</p>
          <div className="mt-2 flex gap-1" data-testid="help-rating">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" onClick={() => setRating(n)} aria-label={`${n} star${n > 1 ? "s" : ""}`}
                className="rounded-lg p-1 transition-transform hover:scale-110">
                <Star className={`h-7 w-7 ${n <= rating ? "fill-amber-400 text-amber-400" : "text-muted-foreground/40"}`} />
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-5">
        <p className="text-sm font-medium">{bug ? "Where did it happen?" : "What is it about? (optional)"}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {AREAS.map((a) => (
            <Chip key={a} active={area === a} onClick={() => setArea(area === a ? "" : a)} testid={`help-area-${a.toLowerCase().replace(" ", "-")}`}>{a}</Chip>
          ))}
        </div>
      </div>

      <div className="mt-5">
        <p className="text-sm font-medium">{bug ? "What went wrong?" : "Your feedback"}</p>
        <Textarea value={message} onChange={(e) => setMessage(e.target.value)} maxLength={5000} rows={6}
          data-testid={`help-message-${kind}`} className="mt-2 rounded-xl"
          placeholder={bug ? "What did you do, what did you expect, and what happened instead?" : "Tell us what you think..."} />
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">We reply by email to your account address.</p>
        <Button type="submit" disabled={busy} className="rounded-xl" data-testid={`help-submit-${kind}`}>
          {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
          {bug ? "Send report" : "Send feedback"}
        </Button>
      </div>
    </form>
  );
}

export default function HelpPage() {
  const [params, setParams] = useSearchParams();
  const section = SECTIONS.some((s) => s.id === params.get("tab")) ? params.get("tab") : "faq";
  const [query, setQuery] = useState("");
  const [reports, setReports] = useState([]);

  const loadReports = () => api.get("/help/reports").then(({ data }) => setReports(data)).catch(() => {});
  useEffect(() => { loadReports(); }, []);

  const faqs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? FAQS.filter((f) => `${f.q} ${f.a}`.toLowerCase().includes(q)) : FAQS;
  }, [query]);

  const go = (id) => setParams(id === "faq" ? {} : { tab: id }, { replace: true });

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-10" data-testid="help-page">
          <div className="text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <LifeBuoy className="h-6 w-6" />
            </div>
            <h1 className="radha-heading-gradient mt-4 text-3xl font-extrabold tracking-tighter sm:text-4xl">Help Center</h1>
            <p className="mt-2 text-sm text-muted-foreground">Find answers, report a problem, or tell us what you think.</p>
          </div>

          <div className="mt-6 grid grid-cols-3 gap-2 sm:gap-3" data-testid="help-sections">
            {SECTIONS.map(({ id, label, short, Icon }) => {
              const active = section === id;
              return (
                <button key={id} type="button" onClick={() => go(id)} data-testid={`help-tab-${id}`}
                  className={`flex flex-col items-center gap-2 rounded-2xl border p-3 text-center transition-all sm:p-4 ${
                    active ? "border-primary bg-card text-primary shadow-[0_6px_20px_rgba(99,102,241,0.18)]"
                      : "border-border bg-card/70 text-muted-foreground hover:text-foreground"}`}>
                  <Icon className="h-5 w-5" />
                  <span className="text-xs font-semibold sm:text-sm">
                    <span className="sm:hidden">{short || label}</span><span className="max-sm:hidden">{label}</span>
                  </span>
                </button>
              );
            })}
          </div>

          <div className="mt-6">
            {section === "faq" && (
              <section className="rounded-2xl border border-border bg-card p-5 shadow-sm" data-testid="help-faq">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search questions"
                    className="rounded-xl pl-9" data-testid="help-faq-search" />
                </div>
                {faqs.length ? (
                  <Accordion type="single" collapsible className="mt-2">
                    {faqs.map((f) => (
                      <AccordionItem key={f.q} value={f.q} className="last:border-b-0">
                        <AccordionTrigger className="text-[15px] font-semibold hover:no-underline">{f.q}</AccordionTrigger>
                        <AccordionContent className="text-sm leading-relaxed text-muted-foreground">{f.a}</AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">No answer found for that.</p>
                )}
                <div className="mt-4 rounded-xl bg-muted/60 p-4 text-sm">
                  Still need help?{" "}
                  <button type="button" onClick={() => go("bug")} className="font-semibold text-primary hover:underline">Report a bug</button>
                  {" "}or{" "}
                  <button type="button" onClick={() => go("feedback")} className="font-semibold text-primary hover:underline">send us a message</button>.
                </div>
              </section>
            )}
            {section !== "faq" && <ReportForm key={section} kind={section} onSent={loadReports} />}
          </div>

          {reports.length > 0 && (
            <section className="mt-8" data-testid="help-my-reports">
              <h2 className="text-sm font-bold uppercase tracking-wide text-muted-foreground">Your messages</h2>
              <ul className="mt-3 space-y-2">
                {reports.slice(0, 10).map((r) => (
                  <li key={r.id} className="rounded-xl border border-border bg-card px-4 py-3 text-sm">
                    <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span className="font-semibold text-foreground">{KIND_LABEL[r.kind]}{r.area ? ` · ${r.area}` : ""}</span>
                      <span>{new Date(r.createdAt).toLocaleDateString()} · Received</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-muted-foreground">{r.message}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
