const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
const KEY = "tasks-v1";
let tasks = load();
let filter = "all";

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || seed(); } catch { return seed(); }
}
function seed() {
  return [
    { id: uid(), text: "Sketch the landing page", done: true },
    { id: uid(), text: "Email the design team", done: false },
    { id: uid(), text: "Book dentist appointment", done: false },
  ];
}
function save() { localStorage.setItem(KEY, JSON.stringify(tasks)); }

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.opacity = 1;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.style.opacity = 0), 1600);
}

function render() {
  const list = document.getElementById("list");
  const shown = tasks.filter((t) => filter === "all" || (filter === "done" ? t.done : !t.done));
  list.innerHTML = "";
  for (const t of shown) {
    const li = document.createElement("li");
    li.className = "group flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 transition hover:border-indigo-400/40";
    li.innerHTML = `
      <button class="toggle grid h-6 w-6 shrink-0 place-items-center rounded-full border ${t.done ? "border-emerald-400 bg-emerald-400 text-slate-900" : "border-slate-500"}" aria-label="Toggle">
        ${t.done ? '<i data-lucide="check" class="h-4 w-4"></i>' : ""}
      </button>
      <span class="text flex-1 ${t.done ? "text-slate-500 line-through" : ""}"></span>
      <button class="edit rounded-lg p-1.5 text-slate-400 opacity-0 transition hover:text-white group-hover:opacity-100" aria-label="Edit"><i data-lucide="pencil" class="h-4 w-4"></i></button>
      <button class="del rounded-lg p-1.5 text-slate-400 opacity-0 transition hover:text-rose-400 group-hover:opacity-100" aria-label="Delete"><i data-lucide="trash-2" class="h-4 w-4"></i></button>`;
    li.querySelector(".text").textContent = t.text;
    li.querySelector(".toggle").onclick = () => { t.done = !t.done; save(); render(); };
    li.querySelector(".del").onclick = () => { tasks = tasks.filter((x) => x.id !== t.id); save(); render(); toast("Task deleted"); };
    li.querySelector(".edit").onclick = () => {
      const text = prompt("Edit task", t.text);
      if (text && text.trim()) { t.text = text.trim(); save(); render(); }
    };
    list.appendChild(li);
  }
  const left = tasks.filter((t) => !t.done).length;
  document.getElementById("summary").textContent = `${left} to do · ${tasks.length - left} done`;
  document.getElementById("empty").classList.toggle("hidden", shown.length > 0);
  document.querySelectorAll("#filters button").forEach((b) => {
    b.classList.toggle("bg-indigo-500", b.dataset.filter === filter);
    b.classList.toggle("text-white", b.dataset.filter === filter);
    b.classList.toggle("text-slate-400", b.dataset.filter !== filter);
  });
  lucide.createIcons();
}

document.getElementById("form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("input");
  const text = input.value.trim();
  if (!text) return toast("Type a task first");
  tasks.unshift({ id: uid(), text, done: false });
  input.value = "";
  save();
  render();
});
document.querySelectorAll("#filters button").forEach((b) => (b.onclick = () => { filter = b.dataset.filter; render(); }));
document.getElementById("clear").onclick = () => { tasks = tasks.filter((t) => !t.done); save(); render(); toast("Cleared completed tasks"); };

render();
