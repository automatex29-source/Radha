const PRODUCTS = [
  { id: 1, name: "Monstera Deliciosa", cat: "Large", price: 48, emoji: "🌿", rating: 4.9 },
  { id: 2, name: "Fiddle Leaf Fig", cat: "Large", price: 62, emoji: "🌳", rating: 4.7 },
  { id: 3, name: "Snake Plant", cat: "Easy care", price: 28, emoji: "🪴", rating: 4.8 },
  { id: 4, name: "Pothos Golden", cat: "Easy care", price: 18, emoji: "🍃", rating: 4.9 },
  { id: 5, name: "Echeveria Trio", cat: "Succulents", price: 22, emoji: "🌵", rating: 4.6 },
  { id: 6, name: "Peace Lily", cat: "Flowering", price: 32, emoji: "🌸", rating: 4.5 },
  { id: 7, name: "Calathea Orbifolia", cat: "Pet safe", price: 38, emoji: "🌱", rating: 4.4 },
  { id: 8, name: "Aloe Vera", cat: "Succulents", price: 16, emoji: "🌵", rating: 4.8 },
];
let cart = JSON.parse(localStorage.getItem("cart") || "{}");
let cat = "All";
const money = (n) => `$${n.toFixed(2)}`;

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.opacity = 1;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.style.opacity = 0), 1500);
}

function renderGrid() {
  const cats = ["All", ...new Set(PRODUCTS.map((p) => p.cat))];
  document.getElementById("cats").innerHTML = cats.map((c) =>
    `<button data-cat="${c}" class="rounded-full px-4 py-1.5 text-sm font-medium transition ${c === cat ? "bg-stone-900 text-white" : "bg-white text-stone-600 ring-1 ring-stone-200 hover:ring-stone-400"}">${c}</button>`).join("");
  document.querySelectorAll("#cats button").forEach((b) => (b.onclick = () => { cat = b.dataset.cat; renderGrid(); }));
  const q = document.getElementById("search").value.toLowerCase();
  const items = PRODUCTS.filter((p) => (cat === "All" || p.cat === cat) && p.name.toLowerCase().includes(q));
  document.getElementById("grid").innerHTML = items.map((p) => `
    <article class="group rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-100 transition hover:-translate-y-1 hover:shadow-lg">
      <div class="grid aspect-square place-items-center rounded-xl bg-gradient-to-br from-emerald-50 to-stone-100 text-7xl transition group-hover:scale-[1.02]">${p.emoji}</div>
      <div class="mt-4 flex items-start justify-between gap-2">
        <div><h3 class="font-semibold">${p.name}</h3><p class="text-xs text-stone-500">${p.cat} · ★ ${p.rating}</p></div>
        <p class="font-bold">${money(p.price)}</p>
      </div>
      <button data-add="${p.id}" class="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl bg-stone-900 py-2 text-sm font-semibold text-white transition hover:bg-emerald-600 active:scale-95">
        <i data-lucide="plus" class="h-4 w-4"></i> Add to cart</button>
    </article>`).join("") || `<p class="col-span-full py-16 text-center text-stone-500">No plants match your search.</p>`;
  document.querySelectorAll("[data-add]").forEach((b) => (b.onclick = () => add(Number(b.dataset.add))));
  lucide.createIcons();
}

function add(id, n = 1) {
  cart[id] = (cart[id] || 0) + n;
  if (cart[id] <= 0) delete cart[id];
  localStorage.setItem("cart", JSON.stringify(cart));
  renderCart();
  if (n > 0) toast("Added to cart");
}

function renderCart() {
  const lines = Object.entries(cart).map(([id, qty]) => ({ ...PRODUCTS.find((p) => p.id === Number(id)), qty }));
  const count = lines.reduce((s, l) => s + l.qty, 0);
  const subtotal = lines.reduce((s, l) => s + l.qty * l.price, 0);
  const shipping = subtotal === 0 || subtotal >= 50 ? 0 : 6;
  const badge = document.getElementById("cart-count");
  badge.textContent = count;
  badge.classList.toggle("hidden", !count);
  document.getElementById("cart-items").innerHTML = lines.map((l) => `
    <li class="flex items-center gap-3">
      <div class="grid h-14 w-14 place-items-center rounded-xl bg-stone-100 text-3xl">${l.emoji}</div>
      <div class="flex-1"><p class="font-medium">${l.name}</p><p class="text-sm text-stone-500">${money(l.price)}</p></div>
      <div class="flex items-center gap-2">
        <button data-dec="${l.id}" class="h-7 w-7 rounded-lg ring-1 ring-stone-200 hover:bg-stone-100">−</button>
        <span class="w-4 text-center">${l.qty}</span>
        <button data-inc="${l.id}" class="h-7 w-7 rounded-lg ring-1 ring-stone-200 hover:bg-stone-100">+</button>
      </div>
    </li>`).join("") || `<li class="py-16 text-center text-stone-500">Your cart is empty.</li>`;
  document.querySelectorAll("[data-dec]").forEach((b) => (b.onclick = () => add(Number(b.dataset.dec), -1)));
  document.querySelectorAll("[data-inc]").forEach((b) => (b.onclick = () => add(Number(b.dataset.inc), 1)));
  document.getElementById("subtotal").textContent = money(subtotal);
  document.getElementById("shipping").textContent = shipping ? money(shipping) : "Free";
  document.getElementById("total").textContent = money(subtotal + shipping);
  document.getElementById("checkout").disabled = !count;
}

function toggleCart(open) {
  document.getElementById("cart").classList.toggle("translate-x-full", !open);
  document.getElementById("overlay").classList.toggle("hidden", !open);
}
document.getElementById("cart-btn").onclick = () => toggleCart(true);
document.getElementById("close-cart").onclick = () => toggleCart(false);
document.getElementById("overlay").onclick = () => toggleCart(false);
document.getElementById("search").oninput = renderGrid;
document.getElementById("checkout").onclick = () => {
  cart = {};
  localStorage.setItem("cart", "{}");
  renderCart();
  toggleCart(false);
  toast("Order placed! 🌿 Thank you.");
};

renderGrid();
renderCart();
