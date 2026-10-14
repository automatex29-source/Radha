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
                         "change": _text(k.get("change"), 20), "note": _text(k.get("note"), 80),
                         "trend": [v for v in (_num(x) for x in _list(k.get("trend"))[:40]) if v is not None]})
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet">
<script src="__CHARTJS__"></script>
<style>
:root{color-scheme:light;--bg:#f5f6fb;--surface:#ffffff;--surface-2:#f7f8fc;--ink:#12162a;--ink-2:#4b5167;--ink-3:#7c8299;
--line:#eceef5;--grid:#eff1f6;--brand:#5b4ff0;--brand-2:#9b5cf6;--brand-soft:#efedff;
--up:#0f7a4f;--up-bg:#e3f5ec;--down:#c2332f;--down-bg:#fdebea;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948;
--shadow:0 1px 2px rgba(18,22,42,.04),0 8px 24px rgba(18,22,42,.06)}
.dark{color-scheme:dark;--bg:#0d0f1a;--surface:#161a2b;--surface-2:#1b2034;--ink:#eef0fa;--ink-2:#b4b9cf;--ink-3:#868ca6;
--line:#252a40;--grid:#21263a;--brand:#8b80ff;--brand-2:#b98bff;--brand-soft:#221f45;
--up:#4ad391;--up-bg:#0f2e22;--down:#ff8a84;--down-bg:#3a1a1c;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.25)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.5 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:1200px;margin:0 auto;padding:0 20px 44px}
header{position:relative;margin:0 -20px 4px;padding:30px 20px 26px;overflow:hidden}
header:before{content:"";position:absolute;inset:0;background:radial-gradient(600px 220px at 0% 0%,color-mix(in srgb,var(--brand) 16%,transparent),transparent 70%),
radial-gradient(500px 200px at 100% 0%,color-mix(in srgb,var(--brand-2) 12%,transparent),transparent 70%);pointer-events:none}
.head{position:relative;display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap}
.eyebrow{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--brand);background:var(--brand-soft);
padding:3px 10px;border-radius:999px;margin-bottom:10px}
.eyebrow:before{content:"";width:6px;height:6px;border-radius:50%;background:linear-gradient(135deg,var(--brand),var(--brand-2))}
h1{font:800 clamp(24px,3.4vw,32px)/1.15 "Plus Jakarta Sans",Inter,sans-serif;margin:0;letter-spacing:-.025em}
.sub{color:var(--ink-2);margin:6px 0 0;max-width:720px;font-size:15px}
.grow{flex:1;min-width:240px}
.theme{border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:10px;height:36px;padding:0 12px;
font:500 13px Inter,sans-serif;cursor:pointer;box-shadow:var(--shadow)}
.theme:hover{color:var(--ink)}
.grid{display:grid;gap:16px;margin-top:16px}
.kpis{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.charts{grid-template-columns:repeat(12,1fr)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px 18px 16px;min-width:0;box-shadow:var(--shadow)}
.kpi{position:relative;overflow:hidden;animation:rise .45s ease both}
.kpi .label{font-size:13px;font-weight:500;color:var(--ink-2)}
.kpi .row{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;margin-top:8px}
.kpi .value{font:700 30px/1.05 "Plus Jakarta Sans",Inter,sans-serif;letter-spacing:-.03em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .meta{display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap}
.pill{display:inline-flex;align-items:center;gap:3px;font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px}
.pill.up{color:var(--up);background:var(--up-bg)}.pill.down{color:var(--down);background:var(--down-bg)}
.pill.flat{color:var(--ink-2);background:var(--surface-2)}
.kpi .note{font-size:12px;color:var(--ink-3)}
.spark{width:92px;height:34px;flex-shrink:0}
.kpi:first-child{background:linear-gradient(135deg,var(--brand),var(--brand-2));border-color:transparent;color:#fff}
.kpi:first-child .label,.kpi:first-child .note{color:rgba(255,255,255,.82)}
.kpi:first-child .pill{background:rgba(255,255,255,.18);color:#fff}
.chartcard{grid-column:span 6}.chartcard.wide{grid-column:span 12}
.chead{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:12px}
.chead h2{font:700 15px/1.3 "Plus Jakarta Sans",Inter,sans-serif;margin:0;letter-spacing:-.01em}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink-2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.legend i{width:10px;height:10px;border-radius:3px;display:inline-block}
.chart{position:relative;height:290px}.round .chart{height:250px}
.center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
.center b{font:700 22px "Plus Jakarta Sans",Inter,sans-serif;letter-spacing:-.02em}.center small{font-size:12px;color:var(--ink-3)}
.insights h2{font:700 15px "Plus Jakarta Sans",Inter,sans-serif;margin:0 0 12px}
.insights ol{list-style:none;margin:0;padding:0;display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.insights li{display:flex;gap:10px;align-items:flex-start;padding:12px;border-radius:12px;background:var(--surface-2);color:var(--ink);font-size:14px}
.insights li b{flex-shrink:0;width:22px;height:22px;border-radius:7px;display:grid;place-items:center;font-size:12px;color:#fff;
background:linear-gradient(135deg,var(--brand),var(--brand-2))}
.tbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px}.tbar h2{flex:1;margin:0;font:700 15px "Plus Jakarta Sans",Inter,sans-serif}
.count{font-size:12px;color:var(--ink-3)}
.search{width:240px;max-width:100%;padding:8px 12px 8px 32px;border:1px solid var(--line);border-radius:10px;background:var(--surface-2) no-repeat 10px center;
background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' fill='none' stroke='%237c8299' stroke-width='2' stroke-linecap='round' viewBox='0 0 24 24'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='m20 20-3.5-3.5'/%3E%3C/svg%3E");
color:var(--ink);font:inherit;outline:none}.search:focus{border-color:var(--brand)}
.tablewrap{overflow:auto;max-height:540px;border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:10px 14px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}tbody tr:hover td{background:var(--surface-2)}
th{position:sticky;top:0;background:var(--surface-2);cursor:pointer;user-select:none;color:var(--ink-2);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
th:hover{color:var(--ink)}th .arrow{color:var(--brand)}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
body{background:radial-gradient(900px 500px at 10% -10%,color-mix(in srgb,var(--brand) 10%,transparent),transparent 60%),
radial-gradient(800px 500px at 110% 10%,color-mix(in srgb,var(--brand-2) 9%,transparent),transparent 60%),var(--bg);background-attachment:fixed}
.card{border-radius:18px;background:linear-gradient(180deg,color-mix(in srgb,var(--surface) 100%,#fff 0%),var(--surface));
box-shadow:inset 0 1px 0 rgba(255,255,255,.7),0 1px 1px rgba(18,22,42,.04),0 4px 8px rgba(18,22,42,.04),0 18px 36px -12px rgba(48,40,140,.16);
transform:perspective(900px) rotateX(var(--rx,0deg)) rotateY(var(--ry,0deg)) translateZ(0);transition:transform .25s ease,box-shadow .25s ease;will-change:transform}
.dark .card{box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 1px 1px rgba(0,0,0,.3),0 4px 8px rgba(0,0,0,.25),0 22px 40px -14px rgba(0,0,0,.6)}
.card.lift{box-shadow:inset 0 1px 0 rgba(255,255,255,.7),0 2px 4px rgba(18,22,42,.05),0 12px 20px rgba(18,22,42,.06),0 30px 50px -16px rgba(48,40,140,.24)}
.dark .card.lift{box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 2px 4px rgba(0,0,0,.3),0 14px 24px rgba(0,0,0,.3),0 34px 60px -18px rgba(0,0,0,.7)}
.kpi:first-child{box-shadow:inset 0 1px 0 rgba(255,255,255,.35),0 18px 36px -12px color-mix(in srgb,var(--brand) 55%,transparent)}
.kpi:first-child:after{content:"";position:absolute;inset:0;background:radial-gradient(260px 120px at 85% -20%,rgba(255,255,255,.35),transparent 70%);pointer-events:none}
.smart{display:flex;gap:7px;align-items:flex-start;margin:-4px 0 12px;font-size:12.5px;color:var(--ink-2);line-height:1.45}
.smart:before{content:"✦";flex-shrink:0;width:18px;height:18px;border-radius:6px;display:grid;place-items:center;font-size:10px;color:#fff;
background:linear-gradient(135deg,var(--brand),var(--brand-2));margin-top:-1px}
.auto{font-size:11px;font-weight:600;color:var(--brand);background:var(--brand-soft);padding:2px 8px;border-radius:999px;margin-left:8px;vertical-align:2px}
@media (hover:none),(prefers-reduced-motion:reduce){.card{transform:none!important}}
@media (max-width:860px){.chartcard{grid-column:span 12}}
@media (max-width:560px){.kpis{grid-template-columns:1fr 1fr;gap:10px}.kpi{padding:14px}.kpi .value{font-size:22px}.spark{display:none}
.kpi .note{display:none}main{padding:0 14px 32px}header{margin:0 -14px 4px;padding:24px 14px 18px}.grid{gap:12px}}
@media (prefers-reduced-motion:reduce){.kpi{animation:none}}
</style></head><body><main>
<header><div class="head"><div class="grow"><div class="eyebrow">Dashboard</div><h1 id="title"></h1><p class="sub" id="subtitle"></p></div>
<button class="theme" id="theme" type="button">Dark mode</button></div></header>
<section class="grid kpis" id="kpis"></section>
<section class="grid charts" id="charts"></section>
<section class="card insights" id="insights" style="margin-top:16px" hidden><h2>Key takeaways</h2><ol id="insightlist"></ol></section>
<section class="card" id="tablecard" style="margin-top:16px" hidden><div class="tbar"><h2 id="tabletitle"></h2><span class="count" id="count"></span>
<input class="search" id="search" placeholder="Search rows" aria-label="Search rows"></div><div class="tablewrap"><table id="table"></table></div></section>
</main><script>
const D = __DATA__;
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const svg = (tag, attrs) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
let dark = matchMedia("(prefers-color-scheme: dark)").matches;
try { const saved = localStorage.getItem("krish-dash-theme"); if (saved) dark = saved === "dark"; } catch (e) {}
$("title").textContent = D.title; document.title = D.title;
if (D.subtitle) $("subtitle").textContent = D.subtitle; else $("subtitle").remove();
const charts = [];
function trendOf(change) { const c = String(change || "").trim(); if (!c) return "";
  if (/^[-−▼↓]/.test(c)) return "down"; if (/^(0+([.,]0+)?%?|±.*|flat|no change)$/i.test(c)) return "flat"; return "up"; }
function sparkline(values, color) {
  const v = values.filter((x) => typeof x === "number"); if (v.length < 2) return null;
  const w = 92, h = 34, min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  const pts = v.map((x, i) => [(i / (v.length - 1)) * (w - 6) + 3, h - 4 - ((x - min) / span) * (h - 8)]);
  const s = svg("svg", { viewBox: `0 0 ${w} ${h}`, class: "spark", "aria-hidden": "true" });
  s.append(svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
  const last = pts[pts.length - 1]; s.append(svg("circle", { cx: last[0], cy: last[1], r: 3, fill: color }));
  return s;
}
function drawKpis() {
  const box = $("kpis"); box.innerHTML = "";
  if (!D.kpis.length) { box.hidden = true; return; }
  D.kpis.forEach((k, i) => {
    const c = el("div", "card kpi"); c.style.animationDelay = (i * 60) + "ms"; tilt(c);
    if (!k.change && k.trend && k.trend.length > 1) { k.change = signed(pct(k.trend[0], k.trend[k.trend.length - 1])); k.note = k.note || "over the period"; }
    c.append(el("div", "label", k.label));
    const row = el("div", "row"); row.append(el("div", "value", k.value));
    const sp = k.trend && sparkline(k.trend, i === 0 ? "#fff" : css("--s1")); if (sp) row.append(sp);
    c.append(row);
    if (k.change || k.note) { const m = el("div", "meta"); const t = trendOf(k.change);
      if (k.change) m.append(el("span", "pill " + t, (t === "up" ? "▲ " : t === "down" ? "▼ " : "") + k.change.replace(/^[▲▼↑↓]\\s*/, "")));
      if (k.note) m.append(el("span", "note", k.note)); c.append(m); }
    box.append(c);
  });
}
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const compact = (v) => typeof v !== "number" ? v : Math.abs(v) >= 1e7 ? (v / 1e6).toFixed(1).replace(/\\.0$/, "") + "M"
  : Math.abs(v) >= 1e4 ? (v / 1e3).toFixed(1).replace(/\\.0$/, "") + "K" : v.toLocaleString();
// ---- Smart reading of the data: trends, peaks, leaders and unusual jumps, worked out on the page.
const pct = (a, b) => (a ? Math.round(((b - a) / Math.abs(a)) * 1000) / 10 : 0);
const signed = (p) => (p > 0 ? "+" : "") + p + "%";
function analyse(ch) {
  const notes = [], fmt = (v) => compact(v) + (ch.unit ? " " + ch.unit : "");
  const s0 = ch.series[0], vals = s0.values.map((v) => (typeof v === "number" ? v : null));
  const known = vals.map((v, i) => [v, i]).filter((p) => p[0] !== null);
  if (known.length < 2) return notes;
  const max = known.reduce((a, b) => (b[0] > a[0] ? b : a)), min = known.reduce((a, b) => (b[0] < a[0] ? b : a));
  if (ch.type === "pie" || ch.type === "doughnut") {
    const total = known.reduce((a, p) => a + p[0], 0) || 1, share = Math.round((max[0] / total) * 100);
    notes.push(`${ch.labels[max[1]]} is the biggest share at ${share}%` + (known.length > 2 ? `, ${ch.labels[min[1]]} the smallest at ${Math.round((min[0] / total) * 100)}%.` : "."));
    return notes;
  }
  if (ch.type === "line" || ch.type === "area") {
    const first = known[0], last = known[known.length - 1], change = pct(first[0], last[0]);
    notes.push(`${s0.name} ${change >= 0 ? "rose" : "fell"} ${signed(change)} from ${ch.labels[first[1]]} to ${ch.labels[last[1]]}, peaking at ${fmt(max[0])} in ${ch.labels[max[1]]}.`);
    const steps = known.slice(1).map((p, i) => [pct(known[i][0], p[0]), p[1]]);
    if (steps.length >= 4) {
      const mean = steps.reduce((a, s) => a + s[0], 0) / steps.length;
      const sd = Math.sqrt(steps.reduce((a, s) => a + (s[0] - mean) ** 2, 0) / steps.length);
      const odd = steps.filter((s) => sd > 0 && Math.abs(s[0] - mean) > 2 * sd).sort((a, b) => Math.abs(b[0]) - Math.abs(a[0]))[0];
      if (odd) notes.push(`Unusual ${odd[0] > 0 ? "jump" : "drop"} in ${ch.labels[odd[1]]} (${signed(odd[0])}).`);
    }
    if (ch.series[1]) { const other = ch.series[1].values, a = vals[last[1]], b = other[last[1]];
      if (typeof b === "number") notes.push(`${s0.name} is ${signed(pct(b, a))} vs ${ch.series[1].name} at ${ch.labels[last[1]]}.`); }
    return notes;
  }
  if (ch.series[1]) {
    const later = ch.series[ch.series.length - 1], earlier = ch.series[ch.series.length - 2];
    const growth = ch.labels.map((l, i) => [pct(earlier.values[i], later.values[i]), l]).filter((g) => isFinite(g[0]));
    const best = growth.reduce((a, b) => (b[0] > a[0] ? b : a)), worst = growth.reduce((a, b) => (b[0] < a[0] ? b : a));
    notes.push(`${best[1]} grew most (${signed(best[0])} ${earlier.name} to ${later.name})` + (worst[0] < 0 ? `; ${worst[1]} fell ${signed(worst[0])}.` : "."));
  } else {
    const ratio = min[0] > 0 ? Math.round((max[0] / min[0]) * 10) / 10 : 0;
    notes.push(`${ch.labels[max[1]]} leads with ${fmt(max[0])}` + (ratio >= 1.5 ? `, ${ratio}× ${ch.labels[min[1]]}.` : "."));
  }
  return notes;
}
// ---- 3D drawing for Chart.js: extruded bars and doughnuts, glowing lines with a fading fill, a marked peak.
function shade(hex, amt) { const n = parseInt(hex.slice(1), 16); const f = (c) => Math.max(0, Math.min(255, Math.round(c + (amt < 0 ? c : 255 - c) * amt)));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`; }
const DEPTH = 7;
const depth3d = { id: "depth3d",
  beforeDatasetDraw(chart, args) {
    const meta = args.meta, ds = chart.data.datasets[args.index], ctx = chart.ctx;
    if (meta.type === "doughnut" || meta.type === "pie") {
      meta.data.forEach((arc, j) => { const base = ds.baseColors[j], o = arc.options.backgroundColor;
        ctx.save(); arc.options.backgroundColor = shade(base, -0.35);
        for (let k = DEPTH + 3; k > 0; k--) { ctx.translate(0, 1); arc.draw(ctx); }
        ctx.restore(); arc.options.backgroundColor = o; });
    }
    if (meta.type === "line") { ctx.save(); ctx.shadowColor = ds.borderColor + "66"; ctx.shadowBlur = 14; ctx.shadowOffsetY = 8; }
  },
  afterDatasetDraw(chart, args) {
    const meta = args.meta, ds = chart.data.datasets[args.index], ctx = chart.ctx, d = DEPTH;
    if (meta.type === "line") { ctx.restore();
      if (args.index === 0 && ds.peak != null && meta.data[ds.peak]) { const p = meta.data[ds.peak];
        ctx.save(); ctx.fillStyle = ds.borderColor; ctx.strokeStyle = chart.options.surface; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(p.x, p.y, 5.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        const label = "Peak " + ds.peakLabel; ctx.font = "600 11px Inter, sans-serif"; const w = ctx.measureText(label).width + 14;
        const x = Math.min(Math.max(p.x - w / 2, chart.chartArea.left), chart.chartArea.right - w), y = Math.max(p.y - 32, chart.chartArea.top - 6);
        ctx.fillStyle = chart.options.ink; ctx.beginPath(); ctx.roundRect(x, y, w, 20, 6); ctx.fill();
        ctx.fillStyle = chart.options.surface; ctx.textBaseline = "middle"; ctx.fillText(label, x + 7, y + 10.5); ctx.restore(); }
    }
    if (meta.type !== "bar") return;
    const horizontal = chart.options.indexAxis === "y";
    meta.data.forEach((bar, j) => { if (bar.hidden) return; const c = ds.baseColor;
      const p = bar.getProps(["x", "y", "base", "width", "height"], true);
      ctx.save();
      if (!horizontal) { const l = p.x - p.width / 2, r = p.x + p.width / 2, t = Math.min(p.y, p.base), b = Math.max(p.y, p.base);
        ctx.fillStyle = shade(c, -0.3); ctx.beginPath(); ctx.moveTo(r, t); ctx.lineTo(r + d, t - d); ctx.lineTo(r + d, b - d); ctx.lineTo(r, b); ctx.closePath(); ctx.fill();
        ctx.fillStyle = shade(c, 0.35); ctx.beginPath(); ctx.moveTo(l, t); ctx.lineTo(l + d, t - d); ctx.lineTo(r + d, t - d); ctx.lineTo(r, t); ctx.closePath(); ctx.fill();
      } else { const t = p.y - p.height / 2, b = p.y + p.height / 2, l = Math.min(p.x, p.base), r = Math.max(p.x, p.base);
        ctx.fillStyle = shade(c, 0.35); ctx.beginPath(); ctx.moveTo(l, t); ctx.lineTo(l + d, t - d); ctx.lineTo(r + d, t - d); ctx.lineTo(r, t); ctx.closePath(); ctx.fill();
        ctx.fillStyle = shade(c, -0.3); ctx.beginPath(); ctx.moveTo(r, t); ctx.lineTo(r + d, t - d); ctx.lineTo(r + d, b - d); ctx.lineTo(r, b); ctx.closePath(); ctx.fill(); }
      ctx.restore(); });
  } };
function frontGradient(chart, color, horizontal) {
  const a = chart.chartArea; if (!a) return color;
  const g = horizontal ? chart.ctx.createLinearGradient(a.left, 0, a.right, 0) : chart.ctx.createLinearGradient(0, a.bottom, 0, a.top);
  g.addColorStop(0, shade(color, -0.12)); g.addColorStop(1, shade(color, 0.12)); return g;
}
function fadeFill(chart, color) { const a = chart.chartArea; if (!a) return color + "22";
  const g = chart.ctx.createLinearGradient(0, a.top, 0, a.bottom); g.addColorStop(0, color + "55"); g.addColorStop(1, color + "00"); return g; }
// ---- Cards tilt a little towards the pointer, for depth.
function tilt(card) {
  card.addEventListener("pointermove", (e) => { if (e.pointerType !== "mouse") return; const r = card.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5, k = card.classList.contains("chartcard") ? 2 : 5;
    card.style.setProperty("--ry", (x * k).toFixed(2) + "deg"); card.style.setProperty("--rx", (-y * k).toFixed(2) + "deg"); card.classList.add("lift"); });
  card.addEventListener("pointerleave", () => { card.style.setProperty("--ry", "0deg"); card.style.setProperty("--rx", "0deg"); card.classList.remove("lift"); });
}
function drawCharts() {
  charts.forEach((c) => c.destroy()); charts.length = 0;
  const box = $("charts"); box.innerHTML = "";
  if (!D.charts.length) { box.hidden = true; return; }
  const palette = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"].map(css);
  const ink2 = css("--ink-2"), ink3 = css("--ink-3"), grid = css("--grid"), surface = css("--surface");
  // Two charts per row; with an odd count the first line or bar chart gets the full width.
  const wideAt = D.charts.length % 2 ? Math.max(0, D.charts.findIndex((c) => !["pie", "doughnut"].includes(c.type))) : -1;
  D.charts.forEach((ch, n) => {
    const round = ch.type === "pie" || ch.type === "doughnut";
    const c = el("div", "card chartcard" + (round ? " round" : "") + (n === wideAt ? " wide" : ""));
    const head = el("div", "chead"); head.append(el("h2", "", ch.title || "Chart"));
    const names = round ? ch.labels : ch.series.map((s) => s.name);
    if (names.length > 1) { const lg = el("div", "legend");
      names.slice(0, 8).forEach((nm, i) => { const s = el("span"); const sw = el("i"); sw.style.background = palette[i % 8]; s.append(sw, document.createTextNode(nm)); lg.append(s); });
      head.append(lg); }
    c.append(head); tilt(c);
    const notes = analyse(ch); ch.notes = notes; if (notes.length) c.append(el("p", "smart", notes.join(" ")));
    const box2 = el("div", "chart"); const cv = document.createElement("canvas"); box2.append(cv); c.append(box2); box.append(c);
    if (!window.Chart) { box2.textContent = "Charts need an internet connection."; return; }
    if (round) { const total = ch.series[0].values.reduce((a, b) => a + (b || 0), 0);
      const mid = el("div", "center"); mid.append(el("b", "", compact(total) + (ch.unit ? " " + ch.unit : "")), el("small", "", "Total")); box2.append(mid); }
    const type = ch.type === "area" ? "line" : ch.type === "hbar" ? "bar" : ch.type;
    const peakIdx = ch.series[0].values.reduce((m, v, i, a) => (typeof v === "number" && (m < 0 || v > a[m]) ? i : m), -1);
    const datasets = ch.series.map((s, i) => ({ baseColor: palette[i % 8], baseColors: ch.labels.map((_, j) => palette[j % 8]),
      peak: i === 0 && peakIdx >= 0 ? peakIdx : null, peakLabel: peakIdx >= 0 ? compact(ch.series[0].values[peakIdx]) + (ch.unit ? " " + ch.unit : "") : "",
      label: s.name, data: s.values, borderWidth: type === "bar" ? 0 : 2, tension: .35, spanGaps: true,
      pointRadius: 0, pointHoverRadius: 5, pointHoverBorderWidth: 2, pointHoverBorderColor: surface, pointBackgroundColor: palette[i % 8],
      fill: ch.type === "area" ? "origin" : false, borderColor: round ? surface : palette[i % 8],
      backgroundColor: round ? ch.labels.map((_, j) => palette[j % 8])
        : ch.type === "area" ? (ctx) => fadeFill(ctx.chart, palette[i % 8])
        : type === "bar" ? (ctx) => frontGradient(ctx.chart, palette[i % 8], ch.type === "hbar") : palette[i % 8],
      borderRadius: 0, borderSkipped: "start", maxBarThickness: 26, categoryPercentage: .62, barPercentage: .8,
      hoverOffset: round ? 4 : 0, spacing: round ? 2 : 0,
    }));
    const fmt = (v) => compact(v) + (ch.unit ? " " + ch.unit : "");
    const tooltip = { backgroundColor: css("--ink"), titleColor: surface, bodyColor: surface, padding: 10, cornerRadius: 10, boxPadding: 4,
      usePointStyle: true, titleFont: { family: "Inter", weight: "600" }, bodyFont: { family: "Inter" },
      callbacks: { label: (x) => ` ${round ? x.label : x.dataset.label}: ${fmt(x.raw)}` } };
    const axis = { ticks: { color: ink3, font: { family: "Inter", size: 12 }, maxRotation: 0, autoSkipPadding: 12 }, border: { display: false } };
    charts.push(new Chart(cv, { type, data: { labels: ch.labels, datasets }, plugins: [depth3d], options: {
      surface, ink: css("--ink"), layout: { padding: { top: round ? 4 : 14, right: 10, bottom: round ? 12 : 0 } },
      responsive: true, maintainAspectRatio: false, indexAxis: ch.type === "hbar" ? "y" : "x", cutout: ch.type === "doughnut" ? "70%" : 0,
      interaction: round ? {} : { mode: "index", intersect: false }, animation: { duration: 700 },
      plugins: { legend: { display: false }, tooltip },
      scales: round ? {} : {
        x: { ...axis, grid: { display: ch.type === "hbar", color: grid }, ticks: ch.type === "hbar" ? { ...axis.ticks, callback: fmt } : axis.ticks },
        y: { ...axis, beginAtZero: type === "bar", grid: { display: ch.type !== "hbar", color: grid, drawTicks: false },
             ticks: ch.type === "hbar" ? { ...axis.ticks, padding: 8 } : { ...axis.ticks, padding: 8, callback: fmt } } } } }));
  });
}
function drawInsights() {
  const list = $("insightlist"); list.innerHTML = "";
  let items = D.insights.slice(), auto = false;
  if (!items.length) { items = D.charts.map((ch) => (ch.notes || [])[0]).filter(Boolean).slice(0, 4); auto = true; }
  if (!items.length) return;
  $("insights").hidden = false; const h = $("insights").querySelector("h2"); h.textContent = "Key takeaways";
  if (auto) h.append(el("span", "auto", "Spotted automatically"));
  items.forEach((t, i) => { const li = el("li"); li.append(el("b", "", String(i + 1)), el("span", "", t)); list.append(li); });
}
if (D.table) {
  const t = D.table; $("tablecard").hidden = false; $("tabletitle").textContent = t.title || "Data";
  const clean = (x) => String(x == null ? "" : x).replace(/[,₹$€£%\\s]/g, "");
  const numeric = (t.columns.length ? t.columns : t.rows[0]).map((_, i) => t.rows.some((r) => clean(r[i]) !== "") && t.rows.every((r) => clean(r[i]) === "" || !isNaN(parseFloat(clean(r[i])))));
  let rows = t.rows.slice(), sortCol = -1, asc = true;
  const val = (r, i) => numeric[i] ? parseFloat(clean(r[i])) || 0 : String(r[i] || "").toLowerCase();
  const draw = () => {
    const q = $("search").value.toLowerCase(), table = $("table"); table.innerHTML = "";
    if (t.columns.length) { const tr = el("tr"); t.columns.forEach((c, i) => { const th = el("th", numeric[i] ? "num" : "", c);
      if (i === sortCol) th.append(el("span", "arrow", asc ? " ↑" : " ↓"));
      th.onclick = () => { asc = sortCol === i ? !asc : !numeric[i]; sortCol = i; rows.sort((a, b) => (val(a, i) > val(b, i) ? 1 : val(a, i) < val(b, i) ? -1 : 0) * (asc ? 1 : -1)); draw(); }; tr.append(th); });
      const th = el("thead"); th.append(tr); table.append(th); }
    const shown = rows.filter((r) => !q || r.join(" ").toLowerCase().includes(q));
    const tb = el("tbody"); shown.forEach((r) => { const tr = el("tr"); r.forEach((v, i) => tr.append(el("td", numeric[i] ? "num" : "", v))); tb.append(tr); }); table.append(tb);
    $("count").textContent = shown.length === rows.length ? `${rows.length} rows` : `${shown.length} of ${rows.length} rows`;
  };
  $("search").oninput = draw; draw();
}
function applyTheme() { document.documentElement.classList.toggle("dark", dark); $("theme").textContent = dark ? "Light mode" : "Dark mode"; drawKpis(); drawCharts(); drawInsights(); }
$("theme").onclick = () => { dark = !dark; try { localStorage.setItem("krish-dash-theme", dark ? "dark" : "light"); } catch (e) {} applyTheme(); };
applyTheme();
</script></body></html>"""

_STORY = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#070914;--bg2:#1b1650;--fg:#f5f6ff;--muted:#b9bde3;--accent:#8b80ff;--accent2:#2dd4bf;--accent3:#f472b6;--glass:rgba(255,255,255,.07);--edge:rgba(255,255,255,.14)}
.light{--bg:#eef0fb;--bg2:#d9dcff;--fg:#12162a;--muted:#4c5274;--accent:#5b4ff0;--accent2:#0d9488;--accent3:#db2777;--glass:rgba(255,255,255,.65);--edge:rgba(20,25,60,.1)}
.warm{--bg:#140805;--bg2:#4a1a0e;--fg:#fff6ef;--muted:#f2cdb8;--accent:#ffb454;--accent2:#ff7a59;--accent3:#ffd166;--glass:rgba(255,255,255,.07);--edge:rgba(255,255,255,.14)}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:radial-gradient(1100px 700px at 50% 120%,var(--bg2),var(--bg) 70%);color:var(--fg);overflow:hidden;user-select:none;
font:18px/1.5 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
/* 3D world: floating orbs and a moving grid floor */
.orb{position:fixed;border-radius:50%;filter:blur(60px);opacity:.55;animation:float 14s ease-in-out infinite alternate;pointer-events:none}
.o1{width:380px;height:380px;background:var(--accent);top:-120px;left:-80px}.o2{width:320px;height:320px;background:var(--accent2);bottom:-100px;right:-60px;animation-delay:-5s}
.o3{width:220px;height:220px;background:var(--accent3);top:30%;right:18%;opacity:.3;animation-delay:-9s}
@keyframes float{to{transform:translate(60px,40px) scale(1.15)}}
.floor{position:fixed;left:-50%;right:-50%;bottom:-10%;height:55%;perspective:420px;pointer-events:none;opacity:.5}
.floor div{position:absolute;inset:0;transform:rotateX(72deg);transform-origin:bottom;
background-image:linear-gradient(var(--edge) 1px,transparent 1px),linear-gradient(90deg,var(--edge) 1px,transparent 1px);background-size:60px 60px;
animation:roll 4s linear infinite;mask-image:linear-gradient(to top,#000 10%,transparent 85%);-webkit-mask-image:linear-gradient(to top,#000 10%,transparent 85%)}
@keyframes roll{to{background-position:0 60px}}
.bars{position:fixed;top:14px;left:16px;right:16px;display:flex;gap:6px;z-index:3}
.bars div{flex:1;height:4px;border-radius:2px;background:color-mix(in srgb,var(--fg) 20%,transparent);overflow:hidden}
.bars span{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--accent2))}
.top{position:fixed;top:28px;left:18px;right:18px;display:flex;justify-content:space-between;font-size:12px;color:var(--muted);z-index:3;font-weight:500}
.stage{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:70px 24px 90px;perspective:1200px}
.scene{max-width:880px;width:100%;text-align:center;transform-style:preserve-3d;animation:enter .9s cubic-bezier(.2,.8,.2,1) both}
@keyframes enter{from{opacity:0;transform:translateZ(-260px) rotateX(14deg)}to{opacity:1;transform:none}}
.scene>*{opacity:0;transform:translateY(22px);animation:in .8s cubic-bezier(.2,.7,.2,1) forwards}
.scene>*:nth-child(2){animation-delay:.18s}.scene>*:nth-child(3){animation-delay:.34s}.scene>*:nth-child(4){animation-delay:.5s}
@keyframes in{to{opacity:1;transform:none}}
.kicker{display:inline-block;font-size:12px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:14px}
h1{font:800 clamp(38px,7.5vw,78px)/1.02 "Plus Jakarta Sans",Inter,sans-serif;margin:0 0 18px;letter-spacing:-.035em;
background:linear-gradient(100deg,var(--fg) 30%,var(--accent) 50%,var(--fg) 70%);background-size:250% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;
animation:in .8s forwards,sweep 3.5s 1s ease-in-out forwards}
@keyframes sweep{from{background-position:100% 0}to{background-position:0 0}}
h2{font:800 clamp(28px,4.8vw,48px)/1.12 "Plus Jakarta Sans",Inter,sans-serif;margin:0 0 14px;letter-spacing:-.025em}
p{color:var(--muted);font-size:clamp(17px,2.2vw,21px);margin:0 auto;max-width:660px}
.glass{background:var(--glass);border:1px solid var(--edge);border-radius:28px;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
box-shadow:0 40px 80px -30px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.18)}
.statcard{display:inline-flex;flex-direction:column;align-items:center;padding:34px 48px 28px;margin-bottom:18px;transform:rotateX(8deg);transform-style:preserve-3d}
.big{font:800 clamp(68px,15vw,150px)/1 "Plus Jakarta Sans",Inter,sans-serif;letter-spacing:-.045em;
background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent;
filter:drop-shadow(0 18px 30px color-mix(in srgb,var(--accent) 45%,transparent))}
.ring{width:150px;height:150px;margin:0 auto 6px}.ring circle{fill:none;stroke-width:12}.ring .track{stroke:var(--edge)}
.ring .fill{stroke:url(#rg);stroke-linecap:round;transform:rotate(-90deg);transform-origin:center;transition:stroke-dashoffset 1.4s cubic-bezier(.2,.7,.2,1)}
blockquote{font:700 clamp(24px,3.8vw,38px)/1.3 "Plus Jakarta Sans",Inter,sans-serif;margin:0;padding:44px 40px 30px;position:relative;letter-spacing:-.015em}
blockquote:before{content:"“";position:absolute;top:-34px;left:24px;font-size:120px;line-height:1;color:var(--accent);opacity:.8}
.who{margin-top:16px;font-size:16px}
ul{list-style:none;padding:0;margin:22px auto 0;max-width:620px;text-align:left;perspective:900px}
li{display:flex;gap:14px;align-items:center;padding:15px 18px;margin:10px 0;opacity:0;transform:rotateX(-70deg);transform-origin:top;animation:flip .6s cubic-bezier(.2,.8,.2,1) forwards}
li b{flex-shrink:0;width:30px;height:30px;border-radius:10px;display:grid;place-items:center;font-size:14px;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2))}
@keyframes flip{to{opacity:1;transform:none}}
.chart{display:flex;align-items:flex-end;justify-content:center;gap:clamp(14px,3vw,30px);height:min(40vh,300px);margin:28px auto 0;max-width:760px;
padding:0 18px 0 6px;transform:rotateX(10deg);transform-style:preserve-3d}
.col{flex:1;max-width:70px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:0}
.bar3d{position:relative;width:100%;height:0;transition:height 1.2s cubic-bezier(.2,.7,.2,1);background:linear-gradient(180deg,var(--accent),color-mix(in srgb,var(--accent) 55%,var(--accent2)))}
.bar3d:before{content:"";position:absolute;left:0;right:0;top:-12px;height:12px;transform:skewX(-45deg);transform-origin:bottom left;
background:color-mix(in srgb,var(--accent) 60%,#fff)}
.bar3d:after{content:"";position:absolute;top:0;bottom:0;right:-12px;width:12px;transform:skewY(-45deg);transform-origin:top left;
background:color-mix(in srgb,var(--accent) 55%,#000)}
.col.top1 .bar3d{background:linear-gradient(180deg,var(--accent2),color-mix(in srgb,var(--accent2) 60%,var(--accent)))}
.col.top1 .bar3d:before{background:color-mix(in srgb,var(--accent2) 60%,#fff)}.col.top1 .bar3d:after{background:color-mix(in srgb,var(--accent2) 55%,#000)}
.col small{font-size:12px;color:var(--muted);margin-top:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.col b{font-size:13px;margin-bottom:18px;opacity:0;transition:opacity .4s 1s}
.smart{display:inline-flex;gap:8px;align-items:center;margin-top:26px;padding:9px 16px;border-radius:999px;font-size:15px;color:var(--fg)}
.smart:before{content:"✦";color:var(--accent2)}
.controls{position:fixed;bottom:20px;left:0;right:0;display:flex;justify-content:center;gap:10px;z-index:3}
button{font:600 14px Inter,system-ui,sans-serif;color:var(--fg);background:var(--glass);backdrop-filter:blur(10px);border:1px solid var(--edge);border-radius:999px;
padding:10px 18px;cursor:pointer;min-width:44px}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tap{position:fixed;top:40px;bottom:80px;width:30%;z-index:2}.tap.l{left:0}.tap.r{right:0}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.scene>*,li{opacity:1;transform:none}}
</style></head><body>
<div class="orb o1"></div><div class="orb o2"></div><div class="orb o3"></div><div class="floor"><div></div></div>
<div class="bars" id="bars"></div><div class="top"><span id="name"></span><span id="pos"></span></div>
<div class="stage"><div class="scene" id="scene" aria-live="polite"></div></div>
<div class="tap l" id="prev" aria-hidden="true"></div><div class="tap r" id="next" aria-hidden="true"></div>
<div class="controls"><button id="back" aria-label="Previous">‹</button><button id="play">Pause</button>
<button id="fwd" aria-label="Next">›</button><button id="full" aria-label="Full screen">⤢</button></div>
<script>
const D = __DATA__;
document.body.className = D.theme === "dark" ? "" : D.theme; document.title = D.title;
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; };
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
$("name").textContent = D.title;
const bars = D.scenes.map(() => { const d = el("div"); const s = el("span"); d.append(s); $("bars").append(d); return s; });
let i = 0, playing = true, start = 0, elapsed = 0;
const ms = D.seconds * 1000;
function countUp(node, target) {
  const m = String(target).match(/^(\\D*)(-?[\\d,]*\\.?\\d+)(.*)$/);
  if (!m || reduce) { node.textContent = target; return; }
  const end = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, t0 = performance.now();
  const step = (t) => { const p = Math.min(1, (t - t0) / 1400), e = 1 - Math.pow(1 - p, 3);
    node.textContent = m[1] + (end * e).toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[3];
    if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
// A one-line reading of a chart scene, worked out from its numbers.
function smartNote(c) {
  const v = c.values.map((x) => (typeof x === "number" ? x : 0)); if (v.length < 2) return "";
  const maxI = v.indexOf(Math.max(...v)), first = v[0], last = v[v.length - 1];
  const rising = v.every((x, j) => j === 0 || x >= v[j - 1]);
  const change = first ? Math.round(((last - first) / Math.abs(first)) * 100) : 0;
  if (rising && change) return `Up ${change}% from ${c.labels[0]} to ${c.labels[v.length - 1]}, every step higher`;
  if (change) return `${change > 0 ? "Up" : "Down"} ${Math.abs(change)}% overall, highest in ${c.labels[maxI]}`;
  return `Highest in ${c.labels[maxI]}`;
}
function render() {
  const s = D.scenes[i], box = $("scene"); box.innerHTML = "";
  box.style.animation = "none"; void box.offsetWidth; box.style.animation = "";
  $("pos").textContent = `${i + 1} / ${D.scenes.length}`;
  if (s.type === "title") { box.append(el("span", "kicker", D.title === s.heading ? "Story" : D.title)); if (s.heading) box.append(el("h1", "", s.heading)); if (s.text) box.append(el("p", "", s.text)); }
  else if (s.type === "stat") {
    const card = el("div", "glass statcard"), pctMatch = /^\\s*(\\d{1,3}(\\.\\d+)?)\\s*%\\s*$/.exec(s.value || "");
    if (pctMatch && +pctMatch[1] <= 100) {
      const ns = "http://www.w3.org/2000/svg", sv = document.createElementNS(ns, "svg"); sv.setAttribute("viewBox", "0 0 150 150"); sv.setAttribute("class", "ring");
      sv.innerHTML = '<defs><linearGradient id="rg" x1="0" x2="1"><stop offset="0" stop-color="var(--accent)"/><stop offset="1" stop-color="var(--accent2)"/></linearGradient></defs><circle class="track" cx="75" cy="75" r="62"/><circle class="fill" cx="75" cy="75" r="62"/>';
      const f = sv.querySelector(".fill"), len = 2 * Math.PI * 62; f.style.strokeDasharray = len; f.style.strokeDashoffset = len;
      setTimeout(() => { f.style.strokeDashoffset = len * (1 - pctMatch[1] / 100); }, 250); card.append(sv);
    }
    const big = el("div", "big"); card.append(big); countUp(big, s.value || "");
    box.append(card); if (s.heading) box.append(el("h2", "", s.heading)); if (s.text) box.append(el("p", "", s.text));
  } else if (s.type === "quote") {
    const q = el("div", "glass"); const bq = el("blockquote", "", s.text || s.heading); q.append(bq);
    if (s.text && s.heading) q.append(el("p", "who", "— " + s.heading)); q.style.paddingBottom = "26px"; box.append(q);
  } else {
    if (s.heading) box.append(el("h2", "", s.heading)); if (s.text) box.append(el("p", "", s.text));
  }
  if (s.items.length) { const ul = el("ul"); s.items.forEach((t, j) => { const li = el("li", "glass"); li.style.borderRadius = "16px";
    li.style.animationDelay = (0.35 + j * 0.22) + "s"; li.append(el("b", "", String(j + 1)), el("span", "", t)); ul.append(li); }); box.append(ul); }
  if (s.chart) {
    const c = el("div", "chart"), vals = s.chart.values.map((v) => v || 0), max = Math.max(...vals, 1), top = vals.indexOf(Math.max(...vals));
    s.chart.labels.forEach((l, j) => { const col = el("div", "col" + (j === top ? " top1" : "")), b = el("b", "", (vals[j] || 0).toLocaleString() + (s.chart.unit ? " " + s.chart.unit : "")),
      bar = el("div", "bar3d"); col.append(b, bar, el("small", "", l)); c.append(col);
      setTimeout(() => { bar.style.height = Math.max(2, vals[j] / max * 82) + "%"; b.style.opacity = 1; }, 350 + j * 110); });
    box.append(c);
    const note = smartNote(s.chart); if (note && !s.text) box.append(el("div", "glass smart", note));
  }
  bars.forEach((b, j) => { b.style.width = j < i ? "100%" : "0"; });
  elapsed = 0; start = performance.now();
}
function tick(t) {
  if (playing) { const p = Math.min(1, (elapsed + t - start) / ms); bars[i].style.width = p * 100 + "%";
    if (p >= 1) { if (i < D.scenes.length - 1) { i++; render(); } else { setPlaying(false); bars[i].style.width = "100%"; $("play").textContent = "Replay"; } } }
  requestAnimationFrame(tick);
}
function setPlaying(on) { if (on === playing) return; if (on) start = performance.now(); else elapsed += performance.now() - start;
  playing = on; $("play").textContent = on ? "Pause" : "Play"; }
const go = (d) => { i = Math.max(0, Math.min(D.scenes.length - 1, i + d)); render(); };
$("next").onclick = $("fwd").onclick = () => go(1); $("prev").onclick = $("back").onclick = () => go(-1);
$("play").onclick = () => { if ($("play").textContent === "Replay") { i = 0; render(); setPlaying(true); } else setPlaying(!playing); };
$("full").onclick = () => { try { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); } catch (e) {} };
addEventListener("keydown", (e) => { if (e.key === "ArrowRight") go(1); else if (e.key === "ArrowLeft") go(-1);
  else if (e.key === " ") { e.preventDefault(); $("play").click(); } });
render(); requestAnimationFrame(tick);
</script></body></html>"""

_PROTOTYPE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="__TAILWIND__"></script>
<script>try { tailwind.config = { theme: { extend: { colors: { brand: "__ACCENT__" }, fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] } } } }; } catch (e) {}</script>
<style>
body{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#151a28;min-height:100vh;
background:radial-gradient(900px 600px at 70% 0%,color-mix(in srgb,__ACCENT__ 14%,transparent),transparent 65%),radial-gradient(700px 500px at 0% 100%,rgba(99,102,241,.10),transparent 60%),#eef0f7}
.shell{display:flex;gap:28px;padding:28px 20px;min-height:100vh;align-items:flex-start;justify-content:center;perspective:1800px}
.nav{width:190px;flex-shrink:0;position:sticky;top:20px}
.nav h1{font-size:16px;font-weight:700;margin:0 0 10px}.nav button{display:block;width:100%;text-align:left;padding:8px 10px;margin:2px 0;border-radius:8px;
border:0;background:transparent;font:500 13px inherit;font-family:inherit;color:#475069;cursor:pointer}
.nav button.on{background:#fff;color:#151a28;box-shadow:0 1px 3px rgba(20,25,50,.12),0 6px 16px -6px rgba(20,25,50,.18)}
.nav button.on:before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:__ACCENT__;margin-right:8px;vertical-align:2px}
.view{display:flex;gap:4px;margin-top:14px}.view button{width:auto;flex:1;text-align:center;border:1px solid #dfe2ec;background:#fff8;font-size:12px}
.nav p{font-size:11px;color:#7a8199;margin:12px 4px 0}
.device{background:#fff;overflow:hidden;position:relative;transition:transform .6s cubic-bezier(.2,.7,.2,1);transform-style:preserve-3d;
box-shadow:0 2px 4px rgba(20,25,60,.06),0 30px 60px -20px rgba(20,25,60,.35),0 70px 120px -40px rgba(60,50,160,.35)}
.device.tilt{transform:rotateY(-18deg) rotateX(8deg) rotateZ(1deg)}
.phone{width:390px;height:800px;border-radius:52px;border:11px solid #0d0f17;padding-top:44px;padding-bottom:22px;
box-shadow:0 0 0 2px #2a2e3c,0 2px 4px rgba(20,25,60,.06),0 30px 60px -20px rgba(20,25,60,.35),0 70px 120px -40px rgba(60,50,160,.35)}
.statusbar{position:absolute;top:0;left:0;right:0;height:44px;display:flex;align-items:center;justify-content:space-between;padding:0 26px;font:600 14px Inter,sans-serif;z-index:5;background:inherit}
.island{position:absolute;top:10px;left:50%;width:110px;height:30px;margin-left:-55px;border-radius:20px;background:#0d0f17;z-index:6}
.homebar{position:absolute;bottom:7px;left:50%;width:130px;height:5px;margin-left:-65px;border-radius:3px;background:#151a28;opacity:.85;z-index:6}
.desktop{width:min(1100px,100%);height:700px;border-radius:14px;padding-top:38px}
.desktop:before{content:"";position:absolute;top:0;left:0;right:0;height:38px;background:#f3f4f8;border-bottom:1px solid #e3e5ee}
.desktop:after{content:"";position:absolute;top:14px;left:16px;width:10px;height:10px;border-radius:50%;background:#ff5f57;box-shadow:16px 0 #febc2e,32px 0 #28c840}
.screen{height:100%;overflow:auto;display:none}.screen.on{display:block;animation:fade .25s ease}
@keyframes fade{from{opacity:0}to{opacity:1}}
[data-go]{cursor:pointer}
@media (max-width:720px){.shell{flex-direction:column;align-items:center;padding:12px}.nav{width:100%;position:static;display:flex;flex-wrap:wrap;gap:4px}
.nav h1,.nav p{width:100%}.nav button{width:auto}.phone{width:min(390px,100%);height:740px}.device.tilt{transform:none}.view{display:none}.desktop{height:620px}}
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
if (D.device === "phone") {
  const bar = document.createElement("div"); bar.className = "statusbar"; bar.innerHTML = "<span>9:41</span><span>●●● ▮</span>";
  const island = document.createElement("div"); island.className = "island"; const home = document.createElement("div"); home.className = "homebar";
  dev.append(bar, island, home);
}
const view = document.createElement("div"); view.className = "view";
[["Flat", false], ["3D view", true]].forEach(([label, on]) => { const b = document.createElement("button"); b.textContent = label;
  b.onclick = () => dev.classList.toggle("tilt", on); view.append(b); });
const tip = document.createElement("p"); tip.textContent = "Click buttons and links inside the screen to move between screens."; nav.append(tip, view);
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
