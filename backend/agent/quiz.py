"""Interactive practice quizzes for students: one self-contained HTML page the user takes in the preview.

Multiple-choice questions, one at a time. Tapping an option shows right or wrong at once with a short
explanation. The end screen gives the score (and exam marks with JEE/NEET-style +4/-1 marking), and the
questions they got wrong can be tried again.
"""
import html
import json

MAX_QUESTIONS = 40


def clean_questions(questions) -> list:
    """Keep well-formed questions: 2-5 distinct options and a valid answer index, up to MAX_QUESTIONS."""
    if not isinstance(questions, list):
        raise ValueError("'questions' must be a list of {question, options, answer, explain}")
    out = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        text = str(q.get("question") or "").strip()
        opts = [str(o).strip()[:300] for o in (q.get("options") or []) if str(o).strip()] \
            if isinstance(q.get("options"), list) else []
        answer = q.get("answer")
        if isinstance(answer, str):  # the model sometimes gives the option text or a letter instead of an index
            a = answer.strip()
            if len(a) == 1 and a.upper() in "ABCDE":
                answer = "ABCDE".index(a.upper())
            elif a.isdigit():
                answer = int(a)
            elif a in opts:
                answer = opts.index(a)
        if not text or not 2 <= len(opts) <= 5 or len(set(opts)) != len(opts):
            continue
        if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer < len(opts):
            continue
        out.append({"q": text[:800], "o": opts, "a": answer, "e": str(q.get("explain") or "").strip()[:1200]})
    if not out:
        raise ValueError("Give at least one question with 2-5 options and the index of the right one in 'answer'")
    return out[:MAX_QUESTIONS]


def build_page(title: str, questions: list, exam_marking: bool = False) -> str:
    title = (title or "Practice quiz").strip()[:120]
    data = json.dumps(questions, ensure_ascii=False).replace("</", "<\\/")
    return (_TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__QUESTIONS__", data)
            .replace("__EXAM__", "true" if exam_marking else "false"))


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f5f6fa;--card:#fff;--fg:#151a2d;--muted:#646a85;--accent:#4f46e5;--good:#147a46;--good-bg:#e7f6ee;
--bad:#b42318;--bad-bg:#fdeceb;--line:#e1e4ee}
@media (prefers-color-scheme:dark){:root{--bg:#0f1220;--card:#181c2e;--fg:#eceefa;--muted:#a1a6c0;--accent:#a5a4ff;
--good:#6fd79d;--good-bg:#12301f;--bad:#ff9c92;--bad-bg:#3a1714;--line:#2a2f48}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",
"Noto Sans Devanagari",sans-serif}
main{max-width:640px;margin:0 auto;padding:22px 16px 28px;display:flex;flex-direction:column;gap:14px}
h1{font-size:20px;margin:0;line-height:1.3}.meta{display:flex;justify-content:space-between;color:var(--muted);font-size:14px}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden}.bar span{display:block;height:100%;
background:var(--accent);transition:width .3s}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}
.q{font-size:18px;font-weight:600;white-space:pre-wrap;margin:0 0 14px}
.opts{display:flex;flex-direction:column;gap:8px}
.opt{display:flex;gap:10px;align-items:flex-start;text-align:left;width:100%;font:inherit;color:var(--fg);background:var(--card);
border:1.5px solid var(--line);border-radius:12px;padding:11px 12px;cursor:pointer}
.opt:hover:not(:disabled){border-color:var(--accent)}.opt:disabled{cursor:default}
.opt b{flex:none;width:24px;height:24px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
font-size:13px;background:var(--bg);color:var(--muted)}
.opt.right{border-color:var(--good);background:var(--good-bg)}.opt.right b{background:var(--good);color:var(--card)}
.opt.wrong{border-color:var(--bad);background:var(--bad-bg)}.opt.wrong b{background:var(--bad);color:var(--card)}
.why{margin-top:14px;padding:12px 14px;border-radius:12px;background:var(--bg);font-size:15px;white-space:pre-wrap}
.why strong{display:block;margin-bottom:2px}.why.ok strong{color:var(--good)}.why.no strong{color:var(--bad)}
.row{display:flex;gap:10px}.row button{flex:1}
.btn{font:600 15px/1 inherit;font-family:inherit;padding:13px;border-radius:12px;border:1px solid var(--line);background:var(--card);
color:var(--fg);cursor:pointer}.btn.main{background:var(--accent);border-color:var(--accent);color:var(--card)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.score{text-align:center}.big{font-size:44px;font-weight:700;margin:4px 0}.sub{color:var(--muted);margin:0}
.stats{display:flex;justify-content:center;gap:18px;margin:14px 0 4px;font-size:14px;color:var(--muted)}
.stats span b{display:block;font-size:20px;color:var(--fg)}
.review h2{font-size:16px;margin:4px 0 8px}.review li{margin-bottom:10px}.review .ans{color:var(--good);font-weight:600}
.review .yours{color:var(--bad)}
[hidden]{display:none!important}
</style></head><body><main>
<h1>__TITLE__</h1>
<div class="meta"><span id="count"></span><span id="tally"></span></div>
<div class="bar"><span id="progress"></span></div>
<section id="quiz">
  <div class="card"><p class="q" id="q"></p><div class="opts" id="opts"></div><div class="why" id="why" hidden></div></div>
  <div class="row" style="margin-top:14px"><button class="btn main" id="next" hidden>Next</button></div>
</section>
<section id="end" hidden>
  <div class="card score"><p class="sub" id="verdict"></p><p class="big" id="final"></p><p class="sub" id="marks"></p>
    <div class="stats"><span><b id="s-right"></b>Right</span><span><b id="s-wrong"></b>Wrong</span><span><b id="s-acc"></b>Accuracy</span></div>
  </div>
  <div class="card review" id="review" hidden><h2>Revise these</h2><ol id="missed"></ol></div>
  <div class="row"><button class="btn main" id="retry" hidden>Try the wrong ones again</button><button class="btn" id="restart">Start again</button></div>
</section>
</main>
<script>
const ALL = __QUESTIONS__, EXAM = __EXAM__, L = "ABCDE";
let set, i, right, wrong, missed;
const $ = (id) => document.getElementById(id);
function start(list) {
  set = list; i = 0; right = 0; wrong = 0; missed = [];
  $("quiz").hidden = false; $("end").hidden = true; show();
}
function show() {
  const item = set[i];
  $("q").textContent = `${i + 1}. ${item.q}`;
  $("why").hidden = true; $("next").hidden = true;
  const box = $("opts"); box.innerHTML = "";
  item.o.forEach((text, n) => {
    const b = document.createElement("button");
    b.className = "opt"; b.innerHTML = `<b>${L[n]}</b><span></span>`; b.lastChild.textContent = text;
    b.onclick = () => pick(n); box.appendChild(b);
  });
  meta();
}
function pick(n) {
  const item = set[i], ok = n === item.a, btns = $("opts").children;
  for (const b of btns) b.disabled = true;
  btns[item.a].classList.add("right");
  if (!ok) { btns[n].classList.add("wrong"); wrong++; missed.push({ item, chose: n }); } else right++;
  const why = $("why");
  why.className = "why " + (ok ? "ok" : "no");
  why.innerHTML = `<strong>${ok ? "Correct ✓" : "Not quite. Answer: " + L[item.a]}</strong><span></span>`;
  why.lastChild.textContent = item.e || "";
  why.hidden = false;
  $("next").hidden = false; $("next").textContent = i + 1 < set.length ? "Next" : "See my score";
  $("next").focus(); meta();
}
function meta() {
  $("count").textContent = `Question ${Math.min(i + 1, set.length)} of ${set.length}`;
  $("tally").textContent = right + wrong ? `${right} right · ${wrong} wrong` : "";
  $("progress").style.width = `${((i + ($("next").hidden ? 0 : 1)) / set.length) * 100}%`;
}
function finish() {
  $("quiz").hidden = true; $("end").hidden = false;
  const n = set.length, acc = Math.round((right / n) * 100);
  $("final").textContent = `${right} / ${n}`;
  $("verdict").textContent = acc >= 90 ? "Excellent! 🎉" : acc >= 70 ? "Good work 👍" : acc >= 40 ? "Getting there 💪" : "Let's revise and try again 📚";
  $("marks").textContent = EXAM ? `Exam marks: ${right * 4 - wrong} of ${n * 4} (+4 right, −1 wrong)` : "";
  $("s-right").textContent = right; $("s-wrong").textContent = wrong; $("s-acc").textContent = acc + "%";
  const list = $("missed"); list.innerHTML = "";
  missed.forEach(({ item, chose }) => {
    const li = document.createElement("li");
    li.innerHTML = "<div></div><div class='yours'></div><div class='ans'></div>";
    li.children[0].textContent = item.q;
    li.children[1].textContent = `You chose ${L[chose]}: ${item.o[chose]}`;
    li.children[2].textContent = `Answer ${L[item.a]}: ${item.o[item.a]}`;
    list.appendChild(li);
  });
  $("review").hidden = !missed.length; $("retry").hidden = !missed.length;
  $("count").textContent = "Done"; $("tally").textContent = ""; $("progress").style.width = "100%";
}
$("next").onclick = () => { if (++i < set.length) show(); else finish(); };
$("retry").onclick = () => start(missed.map((m) => m.item));
$("restart").onclick = () => start(ALL);
start(ALL);
</script></body></html>
"""
