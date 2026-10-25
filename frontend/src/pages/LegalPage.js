import { useEffect } from "react";
import { Link } from "react-router-dom";
import ThemeToggle from "@/components/ThemeToggle";
import BrandMark from "@/components/BrandMark";

const UPDATED = "21 October 2026";

const PRIVACY = {
  title: "Privacy Policy",
  intro: "Krish AI is made by EmpireX, a company based in India. This page explains what we keep about you, why, and how you can remove it.",
  sections: [
    ["What we collect", [
      "Your account: name, email address and a scrambled (hashed) copy of your password. We never see or store your actual password.",
      "What you put into Krish AI: your chats, uploaded files, projects, memory notes, apps, decks, docs and automations.",
      "Daily usage counts (for example how many pictures you made today), so plan limits work.",
      "Bug reports and feedback you send from the Help Center.",
      "If you sign in with Google: your Google account's name, email and account id (never your Google password).",
      "When you mark an answer 👎: that question and the start of the answer, so we can see where Krish needs to get better.",
      "Crash reports from the app (what went wrong and on which page), so we can fix problems quickly.",
      "If you turn on the daily Gita verse: the notification address your browser gives for that device.",
      "If you connect apps in Settings > Connectors (Google Drive, Google Calendar, Gmail, GitHub, Notion, Telegram, WhatsApp, Slack or Discord): the access key that app gives Krish (stored encrypted), the account or channel name, and for Telegram and WhatsApp your chat id or phone number. You can disconnect any app at any time, which deletes its key.",
    ]],
    ["How we use it", [
      "To answer you and run the features you use, and to keep your work saved between visits.",
      "To send emails you ask for, such as password reset links.",
      "To fix problems and keep the service safe, for example stopping password guessing.",
      "We do not sell your data and we do not show ads.",
      "Connected apps are used only when you ask Krish to (or an automation you made asks it to): for example reading a Drive file, listing calendar events, or writing a Gmail draft. Krish never sends an email for you, and reads only what the task needs.",
      "Krish AI's use and transfer of information received from Google APIs adheres to the Google API Services User Data Policy, including the Limited Use requirements. Google data is not used to train AI models, is not sold, and is not shown to people except to keep the service safe or when the law requires it.",
    ]],
    ["Who else handles it", [
      "To write answers, your messages and files are sent to the AI provider that answers them. Depending on the model, that is Google (Gemini), Groq, Cerebras, OpenAI, Anthropic, Pollinations or fal.ai. They process it to reply and under their own terms.",
      "When web search is on, your question is sent to search services to find current results.",
      "Weather and city lookups go to Open-Meteo, and cricket scores to CricAPI, with only the city or team you asked about.",
      "The app is hosted on Render and your data is stored in a MongoDB database. Emails are sent through Brevo or Resend.",
      "Payments for Pro and Max are handled by Razorpay. Your card, UPI or bank details go straight to Razorpay; we only keep the order and payment ids, the plan and the amount.",
    ]],
    ["Sharing", [
      "A chat or page is public only if you create a share link for it. Anyone with that link can read it until you turn sharing off or delete it.",
    ]],
    ["Keeping and deleting your data", [
      "We keep your data while your account exists. You can delete single chats, files, projects and memory at any time.",
      "You can delete your whole account in Settings, under Delete account. That removes your account and everything in it from our database straight away.",
    ]],
    ["Security", [
      "Connections are encrypted (HTTPS), passwords are hashed, and repeated wrong passwords are blocked for a while. No service is perfectly secure, so please use a password you don't use anywhere else.",
    ]],
    ["Children", [
      "Krish AI is not meant for children under 13. If you are under 18, use it with a parent's or guardian's permission.",
    ]],
    ["Changes and contact", [
      "If we change this policy we will update the date at the top. For any privacy question or request, write to us from the Help Center inside the app.",
    ]],
  ],
};

const TERMS = {
  title: "Terms of Service",
  intro: "These terms are the agreement between you and EmpireX for using Krish AI. By creating an account or using the app, you agree to them.",
  sections: [
    ["Your account", [
      "Give a real email address and keep your password safe. You are responsible for what happens in your account.",
      "You must be at least 13 years old. If you are under 18, you need a parent's or guardian's permission.",
    ]],
    ["Acceptable use", [
      "Don't use Krish AI to break the law, harm others, harass people, spread malware, or create sexual content involving minors.",
      "Don't try to break, overload or get around the limits of the service, or access other people's accounts or data.",
      "We may suspend or remove accounts that break these rules.",
    ]],
    ["AI answers can be wrong", [
      "Krish AI's answers, pictures, code and documents are made by AI and may be inaccurate, incomplete or out of date. Check anything important yourself.",
      "Krish AI and its Counsellor are not a doctor, lawyer, financial adviser or therapist. Don't rely on them for medical, legal, financial or emergency decisions. In an emergency, contact local emergency services.",
    ]],
    ["Your content", [
      "What you upload and create stays yours. You give us permission to store and process it only to run the service for you, including sending it to the AI providers listed in the Privacy Policy.",
      "Only upload content you have the right to use.",
    ]],
    ["Plans and limits", [
      "Chat is free. Some features have daily limits on the free Basic plan.",
      "Pro (₹299) and Max (₹699) are paid once for 30 days, through Razorpay. They do not renew by themselves: when the 30 days end you go back to Basic, and nothing in your account is deleted. Paying again for the same plan adds 30 more days.",
      "Refunds and cancellations are explained in the Refund Policy.",
      "We may change features and limits as the service grows.",
    ]],
    ["Availability and liability", [
      "Krish AI is provided as it is. We work to keep it running but can't promise it will always be available or error free.",
      "To the extent the law allows, EmpireX is not liable for indirect losses or for decisions you make based on AI answers.",
    ]],
    ["Ending", [
      "You can stop using Krish AI and delete your account at any time in Settings.",
    ]],
    ["Law and changes", [
      "These terms are governed by the laws of India. If we change them we will update the date at the top; using the app after that means you accept the new terms.",
      "Questions? Write to us from the Help Center inside the app.",
    ]],
  ],
};

const REFUNDS = {
  title: "Refund and Cancellation Policy",
  intro: "This page explains how payments for the Pro and Max plans of Krish AI work, and when you can get your money back.",
  sections: [
    ["What you pay for", [
      "Pro costs ₹299 and Max costs ₹699, each for 30 days of the plan. Prices include all charges shown at checkout.",
      "Payments are made through Razorpay with UPI, debit or credit card, net banking or a wallet. Krish AI is a digital service: nothing is shipped, and the plan starts as soon as the payment goes through.",
    ]],
    ["No automatic renewal", [
      "A plan does not renew by itself and we never charge you again without you paying. When the 30 days end your account goes back to the free Basic plan and all your work stays.",
      "You can stop at any time simply by not paying again, so there is nothing to cancel.",
    ]],
    ["Refunds", [
      "If you were charged but your plan did not switch on, or you were charged twice for the same order, we refund the extra payment in full.",
      "If you are not happy with a plan, ask within 7 days of paying and we will refund it in full, once per account.",
      "Approved refunds go back to the same UPI, card or bank account through Razorpay, usually within 5 to 7 working days. Your account returns to Basic when a refund is made.",
    ]],
    ["How to ask", [
      "Write to us from the Help Center inside the app with the email of your account and the payment date. We reply within 2 working days.",
    ]],
  ],
};

const DOCS = { privacy: PRIVACY, terms: TERMS, refunds: REFUNDS };
const OTHER = [["/privacy", "privacy", "Privacy Policy"], ["/terms", "terms", "Terms of Service"], ["/refunds", "refunds", "Refund Policy"]];

/** Public Privacy Policy, Terms of Service and Refund Policy pages; they open without signing in. */
export default function LegalPage({ kind }) {
  const doc = DOCS[kind] || PRIVACY;
  useEffect(() => { document.title = `${doc.title} · Krish AI`; }, [doc.title]);

  return (
    <div className="min-h-dvh bg-background text-foreground" data-testid={`legal-${kind}`}>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/80 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur-xl">
        <Link to="/" className="flex items-center gap-2.5">
          <BrandMark className="h-8 w-8" />
          <span className="text-sm font-extrabold tracking-tight">Krish AI</span>
        </Link>
        <ThemeToggle />
      </header>

      <main className="mx-auto w-full max-w-2xl px-4 pb-16 pt-8">
        <h1 className="text-3xl font-bold tracking-tight">{doc.title}</h1>
        <p className="mt-1 text-xs text-muted-foreground">Last updated {UPDATED}</p>
        <p className="mt-5 leading-relaxed text-muted-foreground">{doc.intro}</p>
        {doc.sections.map(([heading, items]) => (
          <section key={heading} className="mt-8">
            <h2 className="text-lg font-semibold">{heading}</h2>
            <ul className="mt-2 list-disc space-y-2 pl-5 leading-relaxed text-muted-foreground">
              {items.map((t) => <li key={t}>{t}</li>)}
            </ul>
          </section>
        ))}
        <p className="mt-12 flex flex-wrap gap-4 text-sm">
          {OTHER.filter(([, k]) => k !== kind).map(([to, k, label]) => (
            <Link key={k} to={to} className="font-medium text-brand hover:underline">{label}</Link>
          ))}
          <Link to="/" className="text-muted-foreground hover:underline">Back to Krish AI</Link>
        </p>
      </main>
    </div>
  );
}
