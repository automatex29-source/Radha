const SERVICES = [
  { id: "cut", name: "Haircut & style", mins: 45, price: 600, icon: "scissors" },
  { id: "facial", name: "Glow facial", mins: 60, price: 1400, icon: "sparkles" },
  { id: "mani", name: "Manicure", mins: 40, price: 500, icon: "hand" },
  { id: "spa", name: "Head massage", mins: 30, price: 450, icon: "flower-2" },
];
const TIMES = ["10:00", "11:00", "12:00", "13:30", "14:30", "15:30", "16:30", "18:00"];
const $ = (id) => document.getElementById(id);
const state = { service: null, day: 0, time: null };
let bookings = JSON.parse(localStorage.getItem("bookings") || "[]");

const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return d; });
const dayLabel = (d) => d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
const taken = (day, time) => bookings.some((b) => b.day === dayLabel(days[day]) && b.time === time) || (day * 7 + time.length * 3 + parseInt(time)) % 5 === 0;

function toast(msg) { $("toast").textContent = msg; $("toast").style.opacity = 1; setTimeout(() => ($("toast").style.opacity = 0), 2000); }
const pill = (on) => on ? "border-rose-500 bg-rose-50 ring-2 ring-rose-200" : "border-slate-200 hover:border-rose-300";

function render() {
  $("services").innerHTML = SERVICES.map((s) => `
    <button data-service="${s.id}" class="flex items-center gap-3 rounded-2xl border p-4 text-left transition ${pill(state.service === s.id)}">
      <span class="grid h-10 w-10 place-items-center rounded-xl bg-rose-100 text-rose-600"><i data-lucide="${s.icon}" class="h-5 w-5"></i></span>
      <span class="flex-1"><b class="block">${s.name}</b><span class="text-sm text-slate-500">${s.mins} min · ₹${s.price}</span></span>
    </button>`).join("");
  $("days").innerHTML = days.map((d, i) => `<button data-day="${i}" class="shrink-0 rounded-xl border px-4 py-2 text-sm font-medium ${pill(state.day === i)}">${i === 0 ? "Today" : dayLabel(d)}</button>`).join("");
  $("slots").innerHTML = TIMES.map((t) => {
    const off = taken(state.day, t);
    return `<button data-time="${t}" ${off ? "disabled" : ""} class="rounded-xl border py-2 text-sm font-medium ${off ? "cursor-not-allowed border-slate-100 text-slate-300 line-through" : pill(state.time === t)}">${t}</button>`;
  }).join("");
  const s = SERVICES.find((x) => x.id === state.service);
  $("summary").innerHTML = [["Service", s ? s.name : "—"], ["When", state.time ? `${dayLabel(days[state.day])}, ${state.time}` : "—"], ["Price", s ? `₹${s.price}` : "—"]]
    .map(([k, v]) => `<div class="flex justify-between gap-3"><dt class="text-slate-400">${k}</dt><dd class="text-right font-medium">${v}</dd></div>`).join("");
  $("confirm").disabled = !(state.service && state.time);
  $("my-count").textContent = bookings.length;
  $("my-list").innerHTML = bookings.length ? bookings.map((b, i) => `
    <div class="flex items-center justify-between rounded-xl bg-rose-50 p-3 text-sm"><span><b>${b.service}</b><br />${b.day}, ${b.time}</span><button data-cancel="${i}" class="text-rose-600 hover:underline">Cancel</button></div>`).join("")
    : `<p class="py-6 text-center text-slate-400">No bookings yet.</p>`;
  lucide.createIcons();
}

document.addEventListener("click", (e) => {
  const t = (sel) => e.target.closest(sel);
  if (t("[data-service]")) state.service = t("[data-service]").dataset.service;
  else if (t("[data-day]")) { state.day = +t("[data-day]").dataset.day; state.time = null; }
  else if (t("[data-time]")) state.time = t("[data-time]").dataset.time;
  else if (t("[data-cancel]")) { bookings.splice(+t("[data-cancel]").dataset.cancel, 1); localStorage.setItem("bookings", JSON.stringify(bookings)); toast("Booking cancelled"); }
  else return;
  render();
});
$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  const s = SERVICES.find((x) => x.id === state.service);
  bookings.push({ service: s.name, day: dayLabel(days[state.day]), time: state.time, name: $("name").value });
  localStorage.setItem("bookings", JSON.stringify(bookings));
  toast(`Booked! See you ${state.day === 0 ? "today" : dayLabel(days[state.day])} at ${state.time}.`);
  state.time = null;
  e.target.reset();
  render();
});
$("my-btn").onclick = () => { $("modal").classList.remove("hidden"); $("modal").classList.add("grid"); };
$("modal-close").onclick = () => { $("modal").classList.add("hidden"); $("modal").classList.remove("grid"); };
render();
