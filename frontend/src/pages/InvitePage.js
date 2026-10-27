import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { captureRef } from "@/lib/referral";
import { Button } from "@/components/ui/button";
import KrishWordmark from "@/components/KrishWordmark";
import BrandMark from "@/components/BrandMark";
import ThemeToggle from "@/components/ThemeToggle";
import { ArrowRight, BookOpen, Gift, Loader2, MessageCircle, Palette, Sparkles, Sun } from "lucide-react";

const PERKS = [
  { icon: MessageCircle, tone: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-300", title: "Ask anything",
    text: "Questions, ideas, emails and plans, in English, Hindi or Hinglish." },
  { icon: BookOpen, tone: "bg-sky-500/10 text-sky-600 dark:text-sky-300", title: "Study smarter",
    text: "Clear explanations, notes and quick quizzes for any subject." },
  { icon: Palette, tone: "bg-pink-500/10 text-pink-600 dark:text-pink-300", title: "Make things",
    text: "Pictures, slide decks, documents and even working apps." },
  { icon: Sun, tone: "bg-amber-500/15 text-amber-600 dark:text-amber-300", title: "Find calm",
    text: "Kind, thoughtful advice from the Bhagavad Gita, any time." },
];

/** Where an invite link (/i/CODE) lands: who invited you, what Krish does, and the free Pro days. */
export default function InvitePage() {
  const { code } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null); // null = loading, false = not a real link
  const [videoOk, setVideoOk] = useState(true);

  useEffect(() => {
    captureRef();
    api.get(`/invite/${encodeURIComponent(code)}`).then(({ data }) => setInvite(data)).catch(() => setInvite(false));
  }, [code]);

  const who = invite?.name || "A friend";
  const days = invite?.days || 7;
  const start = () => navigate(user ? "/" : "/login");

  return (
    <div className="krish-canvas min-h-dvh w-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col px-4 pb-[max(2rem,env(safe-area-inset-bottom))] pt-[max(1.25rem,env(safe-area-inset-top))] sm:px-6">
        <header className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <BrandMark className="h-8 w-8" />
            <span className="text-xl leading-none"><KrishWordmark /></span>
          </Link>
          <ThemeToggle />
        </header>

        {invite === null ? (
          <div className="flex flex-1 justify-center py-32"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
        ) : (
          <main className="radha-fade-up">
            <section className="mt-8 flex flex-col items-center text-center sm:mt-12">
              <div className="relative h-40 w-64 overflow-hidden rounded-3xl sm:h-48 sm:w-80">
                {videoOk ? (
                  <video src="/krish-motion.webm" autoPlay muted loop playsInline onError={() => setVideoOk(false)}
                    className="h-full w-full object-cover" aria-hidden="true" data-testid="invite-video" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center"><BrandMark className="krish-float h-28 w-28" /></div>
                )}
              </div>
              {invite ? (
                <span className="mt-6 inline-flex items-center gap-1.5 rounded-full bg-orange-500/10 px-3 py-1 text-xs font-bold uppercase tracking-wider text-orange-600 dark:text-orange-300">
                  <Gift className="h-3.5 w-3.5" /> A gift from {who}
                </span>
              ) : (
                <span className="mt-6 text-xs font-medium text-muted-foreground">This invite link has expired, but you can still join free.</span>
              )}
              <h1 className="mt-4 text-[2rem] font-extrabold leading-[1.1] tracking-tight sm:text-5xl" data-testid="invite-heading">
                {invite ? <>{who} invited you to <span className="krish-gradient-text">Krish AI</span></> : <>Meet <span className="krish-gradient-text">Krish AI</span></>}
              </h1>
              <p className="mt-4 max-w-md text-base text-muted-foreground sm:text-lg">
                {invite
                  ? <>Your saarthi for every task: questions, study, writing and creating. Join now and <b className="text-foreground">get {days} days of Pro, free</b>.</>
                  : "Your saarthi for every task: questions, study, writing and creating. Free to start."}
              </p>
              <Button onClick={start} data-testid="invite-claim"
                className="group mt-7 h-12 rounded-2xl bg-gradient-to-r from-orange-500 to-amber-500 px-7 text-base font-bold text-white shadow-[0_10px_30px_rgba(249,115,22,0.35)] hover:from-orange-500 hover:to-amber-600">
                {user ? "Open Krish AI" : invite ? `Claim my ${days} days of Pro` : "Join free"}
                <ArrowRight className="ml-1.5 h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Button>
              <p className="mt-3 text-xs text-muted-foreground">
                {user ? "You already have an account, so this gift is for new friends." : "Sign up with Google or email in under a minute. No card needed."}
              </p>
            </section>

            <section className="mt-12 grid gap-3 sm:grid-cols-2" data-testid="invite-perks">
              {PERKS.map(({ icon: Icon, tone, title, text }) => (
                <div key={title} className="flex items-start gap-3 rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm backdrop-blur">
                  <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${tone}`}><Icon className="h-5 w-5" /></span>
                  <div>
                    <p className="font-semibold">{title}</p>
                    <p className="mt-0.5 text-sm text-muted-foreground">{text}</p>
                  </div>
                </div>
              ))}
            </section>

            {invite && (
              <section className="mt-6 rounded-2xl border border-orange-500/30 bg-orange-500/5 p-5">
                <p className="flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4 text-orange-500" /> What your {days} free Pro days include</p>
                <ul className="mt-3 grid gap-1.5 text-sm text-muted-foreground sm:grid-cols-2">
                  <li>• Premium AI models for harder questions</li>
                  <li>• HD AI pictures and Think mode</li>
                  <li>• 10x the usage of Basic, refilled every 5 hours</li>
                  <li>• Publish the apps you build</li>
                </ul>
                <p className="mt-3 text-xs text-muted-foreground">After {days} days you simply go back to the free plan. Nothing is charged.</p>
              </section>
            )}
          </main>
        )}
      </div>
    </div>
  );
}
