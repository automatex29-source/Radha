// A real AI chat: RADHA.ai answers through Krish AI's free backend (no API key needed).
const SYSTEM = "You are Nova, a friendly and concise assistant. Answer in short paragraphs.";
const STARTERS = ["Plan a 3-day trip to Goa", "Explain compound interest simply", "Write a birthday wish for my mom", "Give me a 20-minute workout"];
const $ = (id) => document.getElementById(id);
let history = JSON.parse(localStorage.getItem("nova-chat") || "[]");
let busy = false;

const esc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
const format = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br />");

function bubble(role, html) {
  const me = role === "user";
  return `<div class="mx-auto flex max-w-3xl ${me ? "justify-end" : "gap-3"}">
    ${me ? "" : `<span class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-sky-400 to-violet-500"><i data-lucide="bot" class="h-4 w-4"></i></span>`}
    <div class="max-w-[80%] rounded-2xl px-4 py-2.5 leading-relaxed ${me ? "bg-sky-500 text-white" : "bg-white/5"}">${html}</div></div>`;
}

function render(thinking) {
  $("log").innerHTML = (history.length ? "" : `<div class="mx-auto mt-16 max-w-md text-center"><h2 class="text-2xl font-bold">Hi, I'm Nova 👋</h2><p class="mt-2 text-slate-400">Ask me anything, or tap an idea below.</p></div>`)
    + history.map((m) => bubble(m.role, format(m.content))).join("")
    + (thinking ? bubble("assistant", `<span class="dot">●</span> <span class="dot">●</span> <span class="dot">●</span>`) : "");
  $("starters").innerHTML = history.length ? "" : STARTERS.map((s) => `<button class="rounded-full border border-white/10 px-3 py-1.5 text-sm text-slate-300 hover:border-sky-400">${s}</button>`).join("");
  $("send").disabled = busy;
  $("log").scrollTop = $("log").scrollHeight;
  lucide.createIcons();
}

async function ask(text) {
  if (!text.trim() || busy) return;
  history.push({ role: "user", content: text.trim() });
  busy = true;
  render(true);
  try {
    const answer = await RADHA.ai(text.trim(), { system: SYSTEM, history: history.slice(-11, -1) });
    history.push({ role: "assistant", content: answer });
  } catch (err) {
    history.push({ role: "assistant", content: "Sorry, I couldn't answer just now: " + err.message });
  }
  busy = false;
  localStorage.setItem("nova-chat", JSON.stringify(history.slice(-40)));
  render(false);
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); const t = $("input").value; $("input").value = ""; ask(t); });
$("starters").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") ask(e.target.textContent); });
$("clear").onclick = () => { history = []; localStorage.removeItem("nova-chat"); render(false); };
render(false);
