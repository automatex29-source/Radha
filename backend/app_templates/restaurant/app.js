const DISHES = [
  { id: 1, name: "Dal Makhani", cat: "Mains", price: 320, text: "Black lentils slow-cooked overnight with butter.", img: "https://krish-image.invalid/dal-makhani-in-copper-bowl-with-cream-swirl.jpg?w=600&h=420" },
  { id: 2, name: "Paneer Tikka", cat: "Starters", price: 290, text: "Charred cottage cheese, mint chutney.", img: "https://krish-image.invalid/paneer-tikka-skewers-on-slate-with-mint-chutney.jpg?w=600&h=420" },
  { id: 3, name: "Laal Maas", cat: "Mains", price: 480, text: "Fiery Rajasthani mutton curry.", img: "https://krish-image.invalid/rajasthani-laal-maas-red-mutton-curry-in-clay-pot.jpg?w=600&h=420" },
  { id: 4, name: "Garlic Naan", cat: "Breads", price: 90, text: "Fresh from the tandoor.", img: "https://krish-image.invalid/garlic-naan-bread-fresh-from-tandoor-on-wooden-board.jpg?w=600&h=420" },
  { id: 5, name: "Hara Bhara Kebab", cat: "Starters", price: 240, text: "Spinach and pea patties, crisp outside.", img: "https://krish-image.invalid/hara-bhara-kebab-green-patties-on-white-plate.jpg?w=600&h=420" },
  { id: 6, name: "Gulab Jamun", cat: "Desserts", price: 150, text: "Warm, syrupy, with pistachio.", img: "https://krish-image.invalid/gulab-jamun-in-syrup-with-pistachio-in-brass-bowl.jpg?w=600&h=420" },
];
let cat = "All";
const cart = new Map();
const $ = (id) => document.getElementById(id);
const money = (n) => "₹" + n.toLocaleString("en-IN");

function toast(msg) {
  $("toast").textContent = msg;
  $("toast").style.opacity = 1;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => ($("toast").style.opacity = 0), 1800);
}

function renderMenu() {
  const cats = ["All", ...new Set(DISHES.map((d) => d.cat))];
  $("cats").innerHTML = cats.map((c) => `<button data-cat="${c}" class="rounded-full px-4 py-2 text-sm font-medium ${c === cat ? "bg-stone-900 text-white" : "bg-white text-stone-600 shadow-sm"}">${c}</button>`).join("");
  $("dishes").innerHTML = DISHES.filter((d) => cat === "All" || d.cat === cat).map((d) => `
    <article class="overflow-hidden rounded-2xl bg-white shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
      <img src="${d.img}" alt="${d.name}" class="aspect-[10/7] w-full object-cover" />
      <div class="p-5"><div class="flex justify-between gap-2"><h3 class="serif text-xl font-semibold">${d.name}</h3><span class="font-semibold text-amber-700">${money(d.price)}</span></div>
      <p class="mt-1 text-sm text-stone-500">${d.text}</p>
      <button data-add="${d.id}" class="mt-4 w-full rounded-xl bg-amber-500 py-2 font-semibold hover:bg-amber-400">Add to order</button></div>
    </article>`).join("");
}

function renderCart() {
  const items = [...cart.entries()].map(([id, qty]) => ({ ...DISHES.find((d) => d.id === id), qty }));
  $("cart-count").textContent = items.reduce((n, i) => n + i.qty, 0);
  $("cart-total").textContent = money(items.reduce((n, i) => n + i.qty * i.price, 0));
  $("cart-items").innerHTML = items.length ? items.map((i) => `
    <div class="flex items-center gap-3"><img src="${i.img}" alt="" class="h-14 w-14 rounded-lg object-cover" />
      <div class="flex-1"><p class="font-medium">${i.name}</p><p class="text-sm text-stone-500">${money(i.price)}</p></div>
      <div class="flex items-center gap-2"><button data-dec="${i.id}" class="h-7 w-7 rounded-full bg-stone-100">−</button>${i.qty}<button data-add="${i.id}" class="h-7 w-7 rounded-full bg-stone-100">+</button></div>
    </div>`).join("") : `<p class="py-10 text-center text-stone-400">Your order is empty.</p>`;
}

document.addEventListener("click", (e) => {
  const add = e.target.closest("[data-add]")?.dataset.add;
  const dec = e.target.closest("[data-dec]")?.dataset.dec;
  const c = e.target.closest("[data-cat]")?.dataset.cat;
  if (add) { cart.set(+add, (cart.get(+add) || 0) + 1); renderCart(); if (!e.target.closest("#cart")) toast("Added to your order"); }
  if (dec) { const q = cart.get(+dec) - 1; q > 0 ? cart.set(+dec, q) : cart.delete(+dec); renderCart(); }
  if (c) { cat = c; renderMenu(); }
});
$("cart-btn").onclick = () => $("cart").classList.remove("translate-x-full");
$("cart-close").onclick = () => $("cart").classList.add("translate-x-full");
$("checkout").onclick = () => {
  if (!cart.size) return toast("Add a dish first");
  cart.clear(); renderCart(); $("cart").classList.add("translate-x-full"); toast("Order placed! Ready in 30 minutes.");
};
$("reserve-form").addEventListener("submit", (e) => {
  e.preventDefault();
  $("reserved").textContent = `Thanks ${$("r-name").value}! Your table for ${$("r-guests").value} on ${$("r-date").value} is booked.`;
  $("reserved").classList.remove("hidden");
  e.target.reset();
});
renderMenu();
renderCart();
lucide.createIcons();
