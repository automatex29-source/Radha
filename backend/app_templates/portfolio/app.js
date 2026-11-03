const PROJECTS = [
  { title: "Paylite", tag: "Fintech", text: "A UPI wallet redesign that cut failed payments by 32%.", img: "https://krish-image.invalid/clean-fintech-mobile-app-screens-on-green-gradient.jpg?w=800&h=560" },
  { title: "CareNest", tag: "Health", text: "Booking and reminders for 120 clinics across India.", img: "https://krish-image.invalid/healthcare-appointment-app-dashboard-soft-blue.jpg?w=800&h=560" },
  { title: "LearnLoop", tag: "Education", text: "Bite-sized lessons with streaks for 2 million students.", img: "https://krish-image.invalid/colorful-education-app-lesson-screens-on-desk.jpg?w=800&h=560" },
  { title: "Ledgerly", tag: "Fintech", text: "An accounting dashboard small shops actually understand.", img: "https://krish-image.invalid/minimal-accounting-dashboard-on-laptop-dark-theme.jpg?w=800&h=560" },
];
const STATS = [["8+", "Years"], ["40", "Products"], ["12", "Awards"]];
const SKILLS = ["Product strategy", "UX research", "UI design", "Design systems", "Prototyping", "Figma", "Usability testing"];
let filter = "All";

function render() {
  const tags = ["All", ...new Set(PROJECTS.map((p) => p.tag))];
  document.getElementById("filters").innerHTML = tags.map((t) => `<button data-tag="${t}" class="rounded-full border px-3 py-1 transition ${t === filter ? "border-emerald-400 bg-emerald-400/10 text-emerald-300" : "border-white/10 text-zinc-400 hover:text-white"}">${t}</button>`).join("");
  document.getElementById("projects").innerHTML = PROJECTS.filter((p) => filter === "All" || p.tag === filter).map((p) => `
    <article class="group overflow-hidden rounded-2xl border border-white/10 bg-zinc-900 transition hover:-translate-y-1 hover:border-emerald-400/40">
      <div class="overflow-hidden"><img src="${p.img}" alt="${p.title} project" class="aspect-[10/7] w-full object-cover transition duration-500 group-hover:scale-105" /></div>
      <div class="p-5"><span class="text-xs text-emerald-300">${p.tag}</span><h3 class="mt-1 text-lg font-semibold">${p.title}</h3><p class="mt-1 text-sm text-zinc-400">${p.text}</p></div>
    </article>`).join("");
}
document.getElementById("filters").addEventListener("click", (e) => {
  const tag = e.target.closest("[data-tag]")?.dataset.tag;
  if (tag) { filter = tag; render(); }
});
document.getElementById("stats").innerHTML = STATS.map(([n, l]) => `<div class="rounded-2xl border border-white/10 p-4"><p class="text-2xl font-bold text-emerald-400">${n}</p><p class="text-xs text-zinc-500">${l}</p></div>`).join("");
document.getElementById("skills").innerHTML = SKILLS.map((s) => `<span class="rounded-full bg-white/5 px-3 py-1.5 text-sm text-zinc-300">${s}</span>`).join("");
document.getElementById("contact-form").addEventListener("submit", (e) => {
  e.preventDefault();
  e.target.reset();
  document.getElementById("sent").classList.remove("hidden");
});
const io = new IntersectionObserver((entries) => entries.forEach((en) => en.isIntersecting && en.target.classList.add("show")), { threshold: 0.15 });
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
render();
lucide.createIcons();
