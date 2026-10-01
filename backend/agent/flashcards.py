"""Interactive flashcards for Study mode: one self-contained HTML page the user previews in chat.

Tap a card to flip it, mark "Got it" or "Again", and cards marked Again come back until they're learnt.
"""
import html
import json

MAX_CARDS = 60


def clean_cards(cards) -> list:
    """Keep well-formed {front, back} pairs (trimmed), up to MAX_CARDS."""
    if not isinstance(cards, list):
        raise ValueError("'cards' must be a list of {front, back}")
    out = []
    for c in cards:
        if isinstance(c, dict):
            front, back = str(c.get("front") or "").strip(), str(c.get("back") or "").strip()
            if front and back:
                out.append({"front": front[:500], "back": back[:1500]})
    if not out:
        raise ValueError("Give at least one card with a 'front' and a 'back'")
    return out[:MAX_CARDS]


def build_page(title: str, cards: list) -> str:
    title = (title or "Flashcards").strip()[:120]
    data = json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")
    return _TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__CARDS__", data)


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f4f5fb;--card:#fff;--fg:#1b1f3a;--muted:#6b7090;--accent:#5b5bd6;--good:#1a7f4b;--again:#b3261e;--line:#e2e4f0}
@media (prefers-color-scheme:dark){:root{--bg:#10121f;--card:#1a1d30;--fg:#eceefa;--muted:#a3a7c2;--accent:#9d9dff;--good:#6fd79d;--again:#ff8f86;--line:#2b2f4a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:620px;margin:0 auto;padding:24px 16px;display:flex;flex-direction:column;gap:16px}
h1{font-size:22px;margin:0}.meta{display:flex;justify-content:space-between;color:var(--muted);font-size:14px}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden}.bar span{display:block;height:100%;background:var(--accent);transition:width .3s}
.scene{perspective:1200px;cursor:pointer}.card{position:relative;min-height:260px;transition:transform .45s;transform-style:preserve-3d}
.flipped .card{transform:rotateY(180deg)}
.face{position:absolute;inset:0;backface-visibility:hidden;background:var(--card);border:1px solid var(--line);border-radius:16px;
padding:28px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:10px;font-size:20px;overflow:auto;white-space:pre-wrap}
.back{transform:rotateY(180deg)}.hint{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.row{display:flex;gap:10px}.row button{flex:1}
button{font:600 15px inherit;font-family:inherit;padding:12px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.good{border-color:var(--good);color:var(--good)}button.again{border-color:var(--again);color:var(--again)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.done{text-align:center;padding:40px 16px;background:var(--card);border:1px solid var(--line);border-radius:16px}
@media (prefers-reduced-motion:reduce){.card{transition:none}}
</style></head><body><main>
<h1>__TITLE__</h1>
<div class="meta"><span id="count"></span><span id="score"></span></div>
<div class="bar"><span id="progress"></span></div>
<div id="study">
  <div class="scene" id="scene" role="button" tabindex="0" aria-label="Flip card">
    <div class="card"><div class="face front"><span class="hint">Question</span><div id="front"></div></div>
    <div class="face back"><span class="hint">Answer</span><div id="back"></div></div></div>
  </div>
  <p class="meta" style="justify-content:center">Tap the card to see the answer</p>
  <div class="row"><button class="again" id="again">Again</button><button class="good" id="good">Got it</button></div>
</div>
<div class="done" id="done" hidden><h1>All done! 🎉</h1><p id="summary"></p><button id="restart">Start again</button></div>
<div class="row"><button id="shuffle">Shuffle</button></div>
</main>
<script>
const CARDS = __CARDS__;
let queue, learnt, firstTry, seen;
const $ = (id) => document.getElementById(id);
function start(order) {
  queue = order.slice(); learnt = 0; firstTry = 0; seen = new Set();
  $("done").hidden = true; $("study").hidden = false; show();
}
function show() {
  if (!queue.length) {
    $("study").hidden = true; $("done").hidden = false;
    $("summary").textContent = `You knew ${firstTry} of ${CARDS.length} cards on the first try.`;
  } else {
    const c = CARDS[queue[0]];
    $("scene").classList.remove("flipped");
    $("front").textContent = c.front; $("back").textContent = c.back;
  }
  $("count").textContent = `${learnt} of ${CARDS.length} learnt`;
  $("score").textContent = queue.length ? `${queue.length} left` : "";
  $("progress").style.width = `${(learnt / CARDS.length) * 100}%`;
}
function answer(knew) {
  const i = queue.shift();
  if (knew) { learnt++; if (!seen.has(i)) firstTry++; }
  else { seen.add(i); queue.push(i); }
  show();
}
$("scene").onclick = () => $("scene").classList.toggle("flipped");
$("scene").onkeydown = (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); $("scene").classList.toggle("flipped"); } };
$("good").onclick = () => answer(true);
$("again").onclick = () => answer(false);
$("restart").onclick = () => start(CARDS.map((_, i) => i));
$("shuffle").onclick = () => start(CARDS.map((_, i) => i).sort(() => Math.random() - 0.5));
start(CARDS.map((_, i) => i));
</script></body></html>
"""
