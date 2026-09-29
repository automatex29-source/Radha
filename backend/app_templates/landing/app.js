const FEATURES = [
  ["zap", "Instant capture", "A global shortcut opens a blank note in under 100 ms."],
  ["search", "Find anything", "Full-text search across every note, PDF and image."],
  ["sparkles", "AI summaries", "Turn long notes into crisp bullet points in one click."],
  ["users", "Real-time teams", "Edit together with live cursors and comments."],
  ["lock", "Private by default", "End-to-end encryption for every workspace."],
  ["smartphone", "Everywhere", "Apps for web, iOS, Android, Mac and Windows."],
];
const PLANS = [
  { name: "Free", monthly: 0, perks: ["Unlimited notes", "2 devices", "Basic search"] },
  { name: "Pro", monthly: 8, perks: ["Everything in Free", "AI summaries", "Unlimited devices", "Priority support"], best: true },
  { name: "Team", monthly: 15, perks: ["Everything in Pro", "Shared workspaces", "Admin controls", "SSO"] },
];
const FAQ = [
  ["Is there a free plan?", "Yes. The Free plan is free forever, with unlimited notes."],
  ["Can I import from other apps?", "Import from Notion, Evernote, Apple Notes and Markdown files in a few clicks."],
  ["Is my data secure?", "Every workspace is end-to-end encrypted, and you can export everything at any time."],
  ["Can I cancel anytime?", "Yes. Plans are month to month and you can cancel in one click."],
];
let billing = "monthly";

document.getElementById("feature-grid").innerHTML = FEATURES.map(([icon, title, text]) => `
  <div class="reveal rounded-2xl border border-slate-100 p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
    <div class="grid h-11 w-11 place-items-center rounded-xl bg-violet-100 text-violet-600"><i data-lucide="${icon}"></i></div>
    <h3 class="mt-4 font-semibold">${title}</h3>
    <p class="mt-1 text-sm text-slate-600">${text}</p>
  </div>`).join("");

function renderPlans() {
  document.getElementById("plans").innerHTML = PLANS.map((p) => {
    const price = billing === "yearly" ? Math.round(p.monthly * 0.8) : p.monthly;
    return `<div class="relative rounded-2xl bg-white p-8 shadow-sm ${p.best ? "ring-2 ring-indigo-500" : ""}">
      ${p.best ? '<span class="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 px-3 py-0.5 text-xs font-semibold text-white">Most popular</span>' : ""}
      <h3 class="font-semibold">${p.name}</h3>
      <p class="mt-3"><span class="text-4xl font-extrabold">$${price}</span><span class="text-slate-500">/mo</span></p>
      <ul class="mt-6 space-y-2 text-sm">${p.perks.map((x) => `<li class="flex items-center gap-2"><i data-lucide="check" class="h-4 w-4 text-emerald-500"></i>${x}</li>`).join("")}</ul>
      <a href="#signup" class="mt-8 block rounded-xl py-2.5 text-center font-semibold transition ${p.best ? "bg-indigo-600 text-white hover:bg-indigo-500" : "border border-slate-200 hover:bg-slate-50"}">Choose ${p.name}</a>
    </div>`;
  }).join("");
  document.querySelectorAll(".billing").forEach((b) => {
    const on = b.dataset.billing === billing;
    b.classList.toggle("bg-slate-900", on);
    b.classList.toggle("text-white", on);
  });
  lucide.createIcons();
}
document.querySelectorAll(".billing").forEach((b) => (b.onclick = () => { billing = b.dataset.billing; renderPlans(); }));

document.getElementById("faq-list").innerHTML = FAQ.map(([q, a]) => `
  <details class="group p-5">
    <summary class="flex cursor-pointer list-none items-center justify-between font-medium">${q}<i data-lucide="chevron-down" class="h-4 w-4 transition group-open:rotate-180"></i></summary>
    <p class="mt-3 text-sm text-slate-600">${a}</p>
  </details>`).join("");

document.getElementById("signup-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const email = document.getElementById("email");
  document.getElementById("signup-msg").textContent = `Thanks! We'll email ${email.value} when your spot is ready.`;
  email.value = "";
});
document.getElementById("year").textContent = new Date().getFullYear();

const io = new IntersectionObserver((entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("show")), { threshold: 0.15 });
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
renderPlans();
