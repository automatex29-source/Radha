"""Interactive pages the agent builds from data: dashboards, animated stories and design prototypes.

The model sends structured data (numbers, scenes, screens) and these builders turn it into one polished,
self-contained HTML page with a consistent look, so the result doesn't depend on the model writing good CSS.
Each page opens in the chat's live preview (a sandboxed iframe) and downloads as an .html file.
"""
import html
import json
import re

MAX_KPIS = 8
MAX_CHARTS = 8
MAX_POINTS = 200
MAX_SERIES = 6
MAX_ROWS = 300
MAX_SCENES = 14
MAX_SCREENS = 12
MAX_SCREEN_HTML = 20_000
CHART_TYPES = ("bar", "line", "area", "pie", "doughnut", "hbar")
SCENE_TYPES = ("title", "text", "stat", "chart", "list", "quote")

CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"
TAILWIND = "https://cdn.tailwindcss.com"


def _text(value, limit: int = 300) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(re.sub(r"[,\s₹$€£%]", "", str(value)))
    except (TypeError, ValueError):
        return None


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _json(data) -> str:
    """JSON safe to put inside a <script> tag."""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _fill(template: str, **values) -> str:
    for key, val in values.items():
        template = template.replace(f"__{key.upper()}__", val)
    return template


def _clean_chart(c) -> dict:
    if not isinstance(c, dict):
        return {}
    labels = [_text(x, 60) for x in _list(c.get("labels"))][:MAX_POINTS]
    series = []
    raw = c.get("series")
    if not raw and c.get("values"):
        raw = [{"name": c.get("title") or "Value", "values": c.get("values")}]
    for s in _list(raw)[:MAX_SERIES]:
        if isinstance(s, dict):
            vals = [_num(v) for v in _list(s.get("values"))][:MAX_POINTS]
            if any(v is not None for v in vals):
                series.append({"name": _text(s.get("name") or "Series", 60), "values": vals})
    if not series:
        return {}
    if not labels:
        labels = [str(i + 1) for i in range(max(len(s["values"]) for s in series))]
    kind = c.get("type") if c.get("type") in CHART_TYPES else "bar"
    return {"title": _text(c.get("title"), 120), "type": kind, "labels": labels, "series": series,
            "unit": _text(c.get("unit"), 12)}


# ---------------------------------------------------------------- dashboards
def clean_dashboard(args: dict) -> dict:
    kpis = []
    for k in _list(args.get("kpis"))[:MAX_KPIS]:
        if isinstance(k, dict) and _text(k.get("label")):
            kpis.append({"label": _text(k.get("label"), 60), "value": _text(k.get("value"), 30),
                         "change": _text(k.get("change"), 20), "note": _text(k.get("note"), 80)})
    charts = [c for c in (_clean_chart(c) for c in _list(args.get("charts"))[:MAX_CHARTS]) if c]
    table = None
    t = args.get("table")
    if isinstance(t, dict) and isinstance(t.get("rows"), list) and t["rows"]:
        cols = [_text(c, 60) for c in _list(t.get("columns"))][:20]
        rows = [[_text(v, 200) for v in r][:20] for r in t["rows"][:MAX_ROWS] if isinstance(r, list)]
        if rows:
            table = {"title": _text(t.get("title"), 120), "columns": cols, "rows": rows}
    if not (kpis or charts or table):
        raise ValueError("Give at least one of 'kpis', 'charts' (with series values) or 'table'")
    return {"title": _text(args.get("title"), 120) or "Dashboard", "subtitle": _text(args.get("subtitle"), 240),
            "kpis": kpis, "charts": charts, "table": table, "insights": [
                _text(x, 300) for x in _list(args.get("insights")) if _text(x)][:6]}


def build_dashboard(spec: dict) -> str:
    return _fill(_DASHBOARD, title=html.escape(spec["title"]), chartjs=CHART_JS, data=_json(spec))


# ------------------------------------------------------------ animated story
def clean_story(args: dict) -> dict:
    scenes = []
    for s in _list(args.get("scenes"))[:MAX_SCENES]:
        if not isinstance(s, dict):
            continue
        kind = s.get("type") if s.get("type") in SCENE_TYPES else "text"
        scene = {"type": kind, "heading": _text(s.get("heading"), 140), "text": _text(s.get("text"), 600),
                 "value": _text(s.get("value"), 30),
                 "items": [_text(x, 160) for x in _list(s.get("items")) if _text(x)][:6]}
        if kind == "chart":
            chart = _clean_chart(s.get("chart") or {})
            if not chart:
                scene["type"] = "text"
            else:
                # The story draws one series as animated bars.
                scene["chart"] = {"labels": chart["labels"][:12], "values": chart["series"][0]["values"][:12],
                                  "unit": chart["unit"]}
        if scene["heading"] or scene["text"] or scene["value"] or scene["items"] or scene.get("chart"):
            scenes.append(scene)
    if not scenes:
        raise ValueError("Give at least one scene with a heading, text, value, items or chart")
    try:
        seconds = min(15.0, max(2.5, float(args.get("seconds_per_scene") or 5)))
    except (TypeError, ValueError):
        seconds = 5.0
    return {"title": _text(args.get("title"), 120) or "Story", "scenes": scenes, "seconds": seconds,
            "theme": args.get("theme") if args.get("theme") in ("dark", "light", "warm") else "dark"}


def build_story(spec: dict) -> str:
    return _fill(_STORY, title=html.escape(spec["title"]), data=_json(spec))


# --------------------------------------------------------- design prototypes
def clean_prototype(args: dict) -> dict:
    screens = []
    for s in _list(args.get("screens"))[:MAX_SCREENS]:
        if isinstance(s, dict) and isinstance(s.get("html"), str) and s["html"].strip():
            name = _text(s.get("name"), 60) or f"Screen {len(screens) + 1}"
            screens.append({"name": name, "html": s["html"][:MAX_SCREEN_HTML]})
    if not screens:
        raise ValueError("Give at least one screen with a 'name' and its 'html'")
    accent = _text(args.get("accent"), 20)
    return {"title": _text(args.get("title"), 120) or "Prototype", "screens": screens,
            "device": "desktop" if args.get("device") == "desktop" else "phone",
            "accent": accent if re.fullmatch(r"#[0-9a-fA-F]{3,8}", accent) else "#4f46e5"}


def build_prototype(spec: dict) -> str:
    return _fill(_PROTOTYPE, title=html.escape(spec["title"]), tailwind=TAILWIND, accent=spec["accent"],
                 data=_json(spec))


# ------------------------------------------------------------------ templates
_DASHBOARD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<script src="__CHARTJS__"></script>
<style>
:root{--bg:#f6f7fb;--card:#fff;--fg:#151a28;--muted:#667085;--line:#e6e8f0;--up:#12805c;--down:#c0392b;
--c1:#4f46e5;--c2:#0ea5a4;--c3:#f59e0b;--c4:#e11d74;--c5:#6366f1;--c6:#64748b}
@media (prefers-color-scheme:dark){:root{--bg:#0e1120;--card:#171b2e;--fg:#eceefa;--muted:#9aa1bd;--line:#272c45;
--up:#4ade80;--down:#f87171;--c1:#8b8cff;--c2:#2dd4bf;--c3:#fbbf24;--c4:#f472b6;--c5:#a5b4fc;--c6:#94a3b8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 18px 40px}
h1{font-size:24px;margin:0;letter-spacing:-.01em}.sub{color:var(--muted);margin:4px 0 0}
.grid{display:grid;gap:14px;margin-top:20px}.kpis{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.charts{grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;min-width:0}
.kpi .label{font-size:13px;color:var(--muted)}.kpi .value{font-size:28px;font-weight:700;margin-top:4px;letter-spacing:-.02em}
.kpi .change{font-size:13px;font-weight:600}.up{color:var(--up)}.down{color:var(--down)}.kpi .note{font-size:12px;color:var(--muted)}
.card h2{font-size:15px;margin:0 0 10px}.chart{position:relative;height:280px}
.insights{margin:20px 0 0;padding:16px 16px 16px 34px}.insights li{margin:4px 0}
.tablewrap{overflow:auto;max-height:520px}table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:var(--card);cursor:pointer;user-select:none;color:var(--muted);font-weight:600}
th:hover{color:var(--fg)}td.num{text-align:right;font-variant-numeric:tabular-nums}
.search{width:100%;max-width:280px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit;margin-bottom:10px}
.kpi{animation:rise .5s ease both}@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.kpi{animation:none}}
</style></head><body><main>
<h1 id="title"></h1><p class="sub" id="subtitle"></p>
<section class="grid kpis" id="kpis"></section>
<section class="grid charts" id="charts"></section>
<ul class="card insights" id="insights" hidden></ul>
<section class="card" id="tablecard" style="margin-top:14px" hidden><h2 id="tabletitle"></h2>
<input class="search" id="search" placeholder="Filter rows" aria-label="Filter rows"><div class="tablewrap"><table id="table"></table></div></section>
</main><script>
const D = __DATA__;
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
$("title").textContent = D.title; $("subtitle").textContent = D.subtitle || ""; document.title = D.title;
D.kpis.forEach((k, i) => {
  const c = el("div", "card kpi"); c.style.animationDelay = (i * 60) + "ms";
  c.append(el("div", "label", k.label), el("div", "value", k.value));
  if (k.change) c.append(el("div", "change " + (/^\\s*[-−▼↓]/.test(k.change) ? "down" : "up"), k.change));
  if (k.note) c.append(el("div", "note", k.note));
  $("kpis").append(c);
});
if (!D.kpis.length) $("kpis").remove();
if (D.insights.length) { const ul = $("insights"); ul.hidden = false; D.insights.forEach((t) => ul.append(el("li", "", t))); }
const css = getComputedStyle(document.documentElement);
const palette = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6"].map((v) => css.getPropertyValue(v).trim());
const muted = css.getPropertyValue("--muted").trim(), line = css.getPropertyValue("--line").trim();
const fmt = (u) => (v) => (typeof v === "number" ? v.toLocaleString() : v) + (u ? " " + u : "");
D.charts.forEach((ch) => {
  const c = el("div", "card"); c.append(el("h2", "", ch.title));
  const box = el("div", "chart"); const cv = document.createElement("canvas"); box.append(cv); c.append(box); $("charts").append(c);
  if (!window.Chart) { box.textContent = "Charts need an internet connection."; return; }
  const round = ch.type === "pie" || ch.type === "doughnut";
  const type = ch.type === "area" ? "line" : ch.type === "hbar" ? "bar" : ch.type;
  const datasets = ch.series.map((s, i) => ({
    label: s.name, data: s.values, borderWidth: round ? 1 : 2, tension: .3, pointRadius: ch.labels.length > 40 ? 0 : 3,
    fill: ch.type === "area", borderColor: round ? css.getPropertyValue("--card").trim() : palette[i % 6],
    backgroundColor: round ? ch.labels.map((_, j) => palette[j % 6]) : ch.type === "area" ? palette[i % 6] + "33" : palette[i % 6],
    borderRadius: type === "bar" ? 6 : 0, maxBarThickness: 46,
  }));
  new Chart(cv, { type, data: { labels: ch.labels, datasets }, options: {
    responsive: true, maintainAspectRatio: false, indexAxis: ch.type === "hbar" ? "y" : "x",
    plugins: { legend: { display: round || datasets.length > 1, labels: { color: muted, boxWidth: 12 } },
      tooltip: { callbacks: { label: (x) => `${x.dataset.label}: ${fmt(ch.unit)(x.raw)}` } } },
    scales: round ? {} : { x: { ticks: { color: muted }, grid: { display: false } },
      y: { ticks: { color: muted, callback: fmt(ch.unit) }, grid: { color: line } } } } });
});
if (!D.charts.length) $("charts").remove();
if (D.table) {
  const t = D.table, card = $("tablecard"); card.hidden = false; $("tabletitle").textContent = t.title || "Data";
  const numeric = (t.columns.length ? t.columns : t.rows[0]).map((_, i) => t.rows.every((r) => r[i] === "" || r[i] == null || !isNaN(parseFloat(String(r[i]).replace(/[,₹$€£%\\s]/g, "")))));
  let rows = t.rows.slice(), sortCol = -1, asc = true;
  const val = (r, i) => numeric[i] ? parseFloat(String(r[i]).replace(/[,₹$€£%\\s]/g, "")) || 0 : String(r[i] || "").toLowerCase();
  const draw = () => {
    const q = $("search").value.toLowerCase(), table = $("table"); table.innerHTML = "";
    if (t.columns.length) { const tr = el("tr"); t.columns.forEach((c, i) => { const th = el("th", "", c + (i === sortCol ? (asc ? " ▲" : " ▼") : ""));
      th.onclick = () => { asc = sortCol === i ? !asc : true; sortCol = i; rows.sort((a, b) => (val(a, i) > val(b, i) ? 1 : -1) * (asc ? 1 : -1)); draw(); }; tr.append(th); });
      const th = el("thead"); th.append(tr); table.append(th); }
    const tb = el("tbody"); rows.filter((r) => !q || r.join(" ").toLowerCase().includes(q)).forEach((r) => {
      const tr = el("tr"); r.forEach((v, i) => tr.append(el("td", numeric[i] ? "num" : "", v))); tb.append(tr); }); table.append(tb);
  };
  $("search").oninput = draw; draw();
}
</script></body></html>"""

_STORY = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#0b0d1a;--bg2:#1c1f4a;--fg:#f4f5ff;--muted:#b8bce0;--accent:#8b8cff;--accent2:#2dd4bf}
.light{--bg:#f7f7fb;--bg2:#e4e6ff;--fg:#141833;--muted:#555b7d;--accent:#4f46e5;--accent2:#0d9488}
.warm{--bg:#1d0f0a;--bg2:#4a1f12;--fg:#fff6ef;--muted:#f0c9b4;--accent:#ffb454;--accent2:#ff7a59}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:radial-gradient(1200px 700px at 20% 10%,var(--bg2),var(--bg));color:var(--fg);
font:18px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow:hidden;user-select:none}
.bars{position:fixed;top:12px;left:12px;right:12px;display:flex;gap:5px;z-index:3}
.bars div{flex:1;height:4px;border-radius:2px;background:color-mix(in srgb,var(--fg) 22%,transparent);overflow:hidden}
.bars span{display:block;height:100%;width:0;background:var(--fg)}
.stage{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:64px 28px 80px}
.scene{max-width:820px;width:100%;text-align:center}
.scene>*{opacity:0;transform:translateY(18px);animation:in .7s cubic-bezier(.2,.7,.2,1) forwards}
.scene>*:nth-child(2){animation-delay:.15s}.scene>*:nth-child(3){animation-delay:.3s}.scene>*:nth-child(4){animation-delay:.45s}
@keyframes in{to{opacity:1;transform:none}}
h1{font-size:clamp(34px,7vw,68px);line-height:1.05;margin:0 0 16px;letter-spacing:-.03em}
h2{font-size:clamp(26px,4.6vw,44px);line-height:1.15;margin:0 0 14px;letter-spacing:-.02em}
p{color:var(--muted);font-size:clamp(17px,2.3vw,22px);margin:0 auto;max-width:640px}
.big{font-size:clamp(64px,15vw,150px);font-weight:800;letter-spacing:-.04em;line-height:1;margin:0 0 12px;
background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
blockquote{font-size:clamp(24px,4vw,38px);line-height:1.3;margin:0 0 16px;font-style:italic}
ul{list-style:none;padding:0;margin:18px auto 0;max-width:600px;text-align:left}
li{padding:12px 16px;margin:8px 0;border-radius:12px;background:color-mix(in srgb,var(--fg) 8%,transparent);opacity:0;
transform:translateX(-14px);animation:in .5s ease forwards}
.chart{display:flex;align-items:flex-end;gap:10px;height:min(42vh,300px);margin:22px auto 0;max-width:700px}
.col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:0}
.bar{width:100%;max-width:64px;border-radius:8px 8px 3px 3px;background:linear-gradient(180deg,var(--accent),var(--accent2));
height:0;transition:height 1.1s cubic-bezier(.2,.7,.2,1)}
.col small{font-size:12px;color:var(--muted);margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.col b{font-size:13px;margin-bottom:4px;opacity:0;transition:opacity .4s .9s}
.controls{position:fixed;bottom:18px;left:0;right:0;display:flex;justify-content:center;gap:10px;z-index:3}
button{font:600 14px system-ui,sans-serif;color:var(--fg);background:color-mix(in srgb,var(--fg) 12%,transparent);
border:1px solid color-mix(in srgb,var(--fg) 20%,transparent);border-radius:999px;padding:9px 16px;cursor:pointer}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tap{position:fixed;top:0;bottom:70px;width:30%;z-index:2}.tap.l{left:0}.tap.r{right:0}
@media (prefers-reduced-motion:reduce){.scene>*,li{animation:none;opacity:1;transform:none}.bar{transition:none}}
</style></head><body>
<div class="bars" id="bars"></div><div class="stage"><div class="scene" id="scene" aria-live="polite"></div></div>
<div class="tap l" id="prev" aria-hidden="true"></div><div class="tap r" id="next" aria-hidden="true"></div>
<div class="controls"><button id="back" aria-label="Previous">‹</button><button id="play">Pause</button>
<button id="fwd" aria-label="Next">›</button></div>
<script>
const D = __DATA__;
document.body.className = D.theme === "dark" ? "" : D.theme; document.title = D.title;
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; };
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const bars = D.scenes.map(() => { const d = el("div"); const s = el("span"); d.append(s); $("bars").append(d); return s; });
let i = 0, playing = true, start = 0, elapsed = 0, raf = 0;
const ms = D.seconds * 1000;
function countUp(node, target) {
  const m = String(target).match(/^(\\D*)(-?[\\d,]*\\.?\\d+)(.*)$/);
  if (!m || reduce) { node.textContent = target; return; }
  const end = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, t0 = performance.now();
  const step = (t) => { const p = Math.min(1, (t - t0) / 1200), e = 1 - Math.pow(1 - p, 3);
    node.textContent = m[1] + (end * e).toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[3];
    if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
function render() {
  const s = D.scenes[i], box = $("scene"); box.innerHTML = "";
  const head = s.type === "title" ? "h1" : "h2";
  if (s.type === "stat" && s.value) { const big = el("div", "big"); box.append(big); countUp(big, s.value); }
  if (s.type === "quote") { box.append(el("blockquote", "", "“" + (s.text || s.heading) + "”")); if (s.text && s.heading) box.append(el("p", "", "— " + s.heading)); }
  else { if (s.heading) box.append(el(head, "", s.heading)); if (s.text) box.append(el("p", "", s.text)); }
  if (s.items.length) { const ul = el("ul"); s.items.forEach((t, j) => { const li = el("li", "", t); li.style.animationDelay = (0.35 + j * 0.25) + "s"; ul.append(li); }); box.append(ul); }
  if (s.chart) {
    const c = el("div", "chart"), vals = s.chart.values.map((v) => v || 0), max = Math.max(...vals, 1);
    s.chart.labels.forEach((l, j) => { const col = el("div", "col"), b = el("b", "", (vals[j] || 0).toLocaleString() + (s.chart.unit ? " " + s.chart.unit : "")),
      bar = el("div", "bar"); col.append(b, bar, el("small", "", l)); c.append(col);
      setTimeout(() => { bar.style.height = Math.max(2, vals[j] / max * 88) + "%"; b.style.opacity = 1; }, 300 + j * 90); });
    box.append(c);
  }
  bars.forEach((b, j) => { b.style.width = j < i ? "100%" : "0"; });
  elapsed = 0; start = performance.now();
}
function tick(t) {
  if (playing) { const p = Math.min(1, (elapsed + t - start) / ms); bars[i].style.width = p * 100 + "%";
    if (p >= 1) { if (i < D.scenes.length - 1) { i++; render(); } else { setPlaying(false); bars[i].style.width = "100%"; $("play").textContent = "Replay"; } } }
  raf = requestAnimationFrame(tick);
}
function setPlaying(on) { if (on === playing) return; if (on) start = performance.now(); else elapsed += performance.now() - start;
  playing = on; $("play").textContent = on ? "Pause" : "Play"; }
const go = (d) => { i = Math.max(0, Math.min(D.scenes.length - 1, i + d)); render(); };
$("next").onclick = $("fwd").onclick = () => go(1); $("prev").onclick = $("back").onclick = () => go(-1);
$("play").onclick = () => { if ($("play").textContent === "Replay") { i = 0; render(); setPlaying(true); } else setPlaying(!playing); };
addEventListener("keydown", (e) => { if (e.key === "ArrowRight") go(1); else if (e.key === "ArrowLeft") go(-1);
  else if (e.key === " ") { e.preventDefault(); $("play").click(); } });
render(); raf = requestAnimationFrame(tick);
</script></body></html>"""

_PROTOTYPE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<script src="__TAILWIND__"></script>
<script>try { tailwind.config = { theme: { extend: { colors: { brand: "__ACCENT__" } } } }; } catch (e) {}</script>
<style>
body{margin:0;background:#eef0f6;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#151a28}
.shell{display:flex;gap:20px;padding:20px;min-height:100vh;align-items:flex-start;justify-content:center}
.nav{width:190px;flex-shrink:0;position:sticky;top:20px}
.nav h1{font-size:15px;margin:0 0 10px}.nav button{display:block;width:100%;text-align:left;padding:8px 10px;margin:2px 0;border-radius:8px;
border:0;background:transparent;font:500 13px inherit;font-family:inherit;color:#475069;cursor:pointer}
.nav button.on{background:#fff;color:#151a28;box-shadow:0 1px 3px rgba(20,25,50,.12)}
.nav p{font-size:11px;color:#7a8199;margin:12px 4px 0}
.device{background:#fff;overflow:hidden;position:relative;box-shadow:0 30px 70px rgba(20,25,60,.18),0 0 0 1px rgba(20,25,60,.06)}
.phone{width:390px;height:780px;border-radius:44px;border:10px solid #111}
.desktop{width:min(1100px,100%);height:700px;border-radius:12px;padding-top:34px}
.desktop:before{content:"";position:absolute;top:0;left:0;right:0;height:34px;background:#f3f4f8;border-bottom:1px solid #e3e5ee}
.desktop:after{content:"";position:absolute;top:12px;left:14px;width:10px;height:10px;border-radius:50%;background:#ff5f57;box-shadow:16px 0 #febc2e,32px 0 #28c840}
.screen{height:100%;overflow:auto;display:none}.screen.on{display:block;animation:fade .25s ease}
@keyframes fade{from{opacity:0}to{opacity:1}}
[data-go]{cursor:pointer}
@media (max-width:720px){.shell{flex-direction:column;align-items:center;padding:12px}.nav{width:100%;position:static;display:flex;flex-wrap:wrap;gap:4px}
.nav h1,.nav p{width:100%}.nav button{width:auto}.phone{width:min(390px,100%);height:720px}.desktop{height:620px}}
</style></head><body>
<div class="shell"><nav class="nav" id="nav" aria-label="Screens"></nav><div class="device" id="device"></div></div>
<script>
const D = __DATA__;
document.title = D.title;
const nav = document.getElementById("nav"), dev = document.getElementById("device");
dev.className = "device " + D.device;
const h = document.createElement("h1"); h.textContent = D.title; nav.append(h);
const buttons = [], screens = [];
D.screens.forEach((s, i) => {
  const b = document.createElement("button"); b.textContent = s.name; b.onclick = () => show(i); nav.append(b); buttons.push(b);
  const sc = document.createElement("div"); sc.className = "screen"; sc.innerHTML = s.html; dev.append(sc); screens.push(sc);
});
const tip = document.createElement("p"); tip.textContent = "Click buttons and links inside the screen to move between screens."; nav.append(tip);
function show(i) { screens.forEach((s, j) => s.classList.toggle("on", j === i)); buttons.forEach((b, j) => b.classList.toggle("on", j === i));
  screens[i].scrollTop = 0; }
dev.addEventListener("click", (e) => {
  const t = e.target.closest("[data-go]"); if (!t) { if (e.target.closest("a[href^='#'],a:not([href])")) e.preventDefault(); return; }
  e.preventDefault(); const name = t.getAttribute("data-go").trim().toLowerCase();
  const j = D.screens.findIndex((s) => s.name.toLowerCase() === name); if (j >= 0) show(j);
});
dev.addEventListener("submit", (e) => { e.preventDefault(); const go = e.target.getAttribute("data-go");
  const j = go ? D.screens.findIndex((s) => s.name.toLowerCase() === go.trim().toLowerCase()) : -1; if (j >= 0) show(j); });
show(0);
</script></body></html>"""
