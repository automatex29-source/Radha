const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const N = 20, S = canvas.width / N;
let snake, dir, next, food, score, timer, paused = false;
let best = Number(localStorage.getItem("snake-best") || 0);
document.getElementById("best").textContent = best;

function reset() {
  snake = [{ x: 9, y: 10 }, { x: 8, y: 10 }, { x: 7, y: 10 }];
  dir = next = { x: 1, y: 0 };
  score = 0;
  document.getElementById("score").textContent = 0;
  placeFood();
}
function placeFood() {
  do food = { x: Math.floor(Math.random() * N), y: Math.floor(Math.random() * N) };
  while (snake.some((s) => s.x === food.x && s.y === food.y));
}
function speed() { return Math.max(60, 140 - score * 4); }

function tick() {
  dir = next;
  const head = { x: (snake[0].x + dir.x + N) % N, y: (snake[0].y + dir.y + N) % N };
  if (snake.some((s) => s.x === head.x && s.y === head.y)) return gameOver();
  snake.unshift(head);
  if (head.x === food.x && head.y === food.y) {
    score++;
    document.getElementById("score").textContent = score;
    placeFood();
    clearInterval(timer);
    timer = setInterval(tick, speed());
  } else snake.pop();
  draw();
}

function draw() {
  ctx.fillStyle = "#0d0d1c";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.shadowBlur = 16;
  ctx.shadowColor = "#22d3ee";
  ctx.fillStyle = "#22d3ee";
  ctx.beginPath();
  ctx.arc(food.x * S + S / 2, food.y * S + S / 2, S / 2.6, 0, Math.PI * 2);
  ctx.fill();
  snake.forEach((s, i) => {
    ctx.shadowColor = "#d946ef";
    ctx.fillStyle = i === 0 ? "#f0abfc" : `hsl(${292 - i * 2}, 85%, ${60 - Math.min(i, 20)}%)`;
    ctx.beginPath();
    ctx.roundRect(s.x * S + 1, s.y * S + 1, S - 2, S - 2, 5);
    ctx.fill();
  });
  ctx.shadowBlur = 0;
}

function start() {
  reset();
  paused = false;
  document.getElementById("overlay").classList.add("hidden");
  clearInterval(timer);
  timer = setInterval(tick, speed());
  draw();
}
function gameOver() {
  clearInterval(timer);
  timer = null;
  if (score > best) {
    best = score;
    localStorage.setItem("snake-best", best);
    document.getElementById("best").textContent = best;
  }
  document.getElementById("message").textContent = `Game over · ${score} point${score === 1 ? "" : "s"}`;
  document.getElementById("start").textContent = "Play again";
  document.getElementById("overlay").classList.remove("hidden");
}
function turn(x, y) {
  if (x === -dir.x && y === -dir.y) return;
  next = { x, y };
}

const KEYS = { ArrowUp: [0, -1], w: [0, -1], ArrowDown: [0, 1], s: [0, 1], ArrowLeft: [-1, 0], a: [-1, 0], ArrowRight: [1, 0], d: [1, 0] };
document.addEventListener("keydown", (e) => {
  if (e.key === " " && timer !== null && snake) {
    e.preventDefault();
    paused = !paused;
    if (paused) clearInterval(timer); else timer = setInterval(tick, speed());
    return;
  }
  const k = KEYS[e.key] || KEYS[e.key.toLowerCase()];
  if (k) { e.preventDefault(); turn(...k); }
});
let touch;
canvas.addEventListener("touchstart", (e) => (touch = e.touches[0]), { passive: true });
canvas.addEventListener("touchend", (e) => {
  const t = e.changedTouches[0], dx = t.clientX - touch.clientX, dy = t.clientY - touch.clientY;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < 20) return;
  Math.abs(dx) > Math.abs(dy) ? turn(Math.sign(dx), 0) : turn(0, Math.sign(dy));
});
document.getElementById("start").onclick = start;
reset();
draw();
