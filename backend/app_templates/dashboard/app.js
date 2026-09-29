const NAMES = ["Aarav Shah", "Mia Chen", "Liam Patel", "Sofia Rossi", "Noah Kim", "Emma Wilson", "Arjun Mehta", "Olivia Brown", "Kabir Singh", "Ava Garcia"];
const STATUS = { Paid: "bg-emerald-100 text-emerald-700", Pending: "bg-amber-100 text-amber-700", Refunded: "bg-rose-100 text-rose-700" };
const orders = Array.from({ length: 24 }, (_, i) => ({
  id: `#${10240 + i}`,
  name: NAMES[i % NAMES.length],
  status: Object.keys(STATUS)[i % 7 === 0 ? 2 : i % 3 === 0 ? 1 : 0],
  total: Math.round(40 + Math.random() * 460),
}));
let revenueChart, channelChart;

function series(days) {
  let v = 1800;
  return Array.from({ length: days }, (_, i) => {
    v = Math.max(600, v + (Math.random() - 0.45) * 400);
    const d = new Date(Date.now() - (days - 1 - i) * 864e5);
    return { label: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }), value: Math.round(v) };
  });
}

function kpi(icon, label, value, delta) {
  const up = delta >= 0;
  return `<div class="rounded-2xl bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
    <div class="flex items-center justify-between text-slate-500"><span class="text-sm">${label}</span><i data-lucide="${icon}" class="h-5 w-5"></i></div>
    <p class="mt-2 text-2xl font-bold">${value}</p>
    <p class="mt-1 text-xs ${up ? "text-emerald-600" : "text-rose-600"}">${up ? "▲" : "▼"} ${Math.abs(delta)}% vs previous</p>
  </div>`;
}

function render() {
  const days = Number(document.getElementById("range").value);
  const data = series(days);
  const total = data.reduce((s, d) => s + d.value, 0);
  document.getElementById("kpis").innerHTML =
    kpi("dollar-sign", "Revenue", `$${total.toLocaleString()}`, 12.4) +
    kpi("shopping-cart", "Orders", Math.round(total / 86).toLocaleString(), 8.1) +
    kpi("users", "New customers", Math.round(total / 310).toLocaleString(), -2.3) +
    kpi("percent", "Conversion", "3.8%", 0.6);

  revenueChart?.destroy();
  revenueChart = new Chart(document.getElementById("revenue"), {
    type: "line",
    data: { labels: data.map((d) => d.label), datasets: [{ data: data.map((d) => d.value), borderColor: "#6366f1", backgroundColor: "rgba(99,102,241,.12)", fill: true, tension: 0.35, pointRadius: 0 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { grid: { color: "#f1f5f9" } } } },
  });
  channelChart?.destroy();
  channelChart = new Chart(document.getElementById("channels"), {
    type: "doughnut",
    data: { labels: ["Online store", "Instagram", "Marketplace", "In person"], datasets: [{ data: [46, 22, 20, 12], backgroundColor: ["#6366f1", "#ec4899", "#14b8a6", "#f59e0b"], borderWidth: 0 }] },
    options: { maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom" } } },
  });
  renderOrders();
  lucide.createIcons();
}

function renderOrders() {
  const q = document.getElementById("search").value.toLowerCase();
  document.getElementById("orders").innerHTML = orders
    .filter((o) => o.name.toLowerCase().includes(q))
    .slice(0, 8)
    .map((o) => `<tr><td class="py-3 font-medium">${o.id}</td><td>${o.name}</td>
      <td><span class="rounded-full px-2 py-0.5 text-xs font-medium ${STATUS[o.status]}">${o.status}</span></td>
      <td class="text-right font-medium">$${o.total}</td></tr>`)
    .join("") || `<tr><td colspan="4" class="py-6 text-center text-slate-400">No matching orders</td></tr>`;
}

document.getElementById("range").onchange = render;
document.getElementById("search").oninput = renderOrders;
render();
