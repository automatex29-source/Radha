const { chromium } = require('playwright');
const out = '/home/user/Radha/marketing/howto';
const chakra = (size) => `<svg viewBox="-2 -2 104 104" width="${size}" height="${size}"><defs><radialGradient id="g" cx="38%" cy="35%" r="70%"><stop offset="0" stop-color="#FFD29A"/><stop offset=".45" stop-color="#FF8A1E"/><stop offset="1" stop-color="#E85A0C"/></radialGradient></defs><g fill="#F5F5F5" stroke="#F5F5F5">${Array.from({ length: 12 }, (_, i) => `<path d="M45 20C47 11 53 6 61 5C58 9 56.5 14 56 20Z" transform="rotate(${i * 30} 50 50)"/>`).join('')}<circle cx="50" cy="50" r="31" fill="none" stroke-width="6"/></g><circle cx="50" cy="50" r="11" fill="url(#g)"/></svg>`;
const wm = fs => `<span style="font-family:Sora;font-weight:700;letter-spacing:-.045em;font-size:${fs}px;color:#F5F5F5;white-space:nowrap">Kr<span style="position:relative">ı<span style="position:absolute;left:50%;top:.02em;width:.21em;height:.21em;border-radius:50%;background:#FF8A1E;transform:translateX(-50%)"></span></span>sh <span style="color:#FF8A1E">AI</span></span>`;
const css = `@import url('https://fonts.googleapis.com/css2?family=Sora:wght@600;700;800&family=Inter:wght@500;600;700&display=block');*{margin:0;box-sizing:border-box}
body{background:#07080B;color:#F5F5F5;font-family:Inter;position:relative;overflow:hidden}
.glow{position:absolute;width:1300px;height:1300px;border-radius:50%;background:radial-gradient(circle,rgba(255,138,30,.30),transparent 62%);filter:blur(30px)}
.grid{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px);background-size:72px 72px}
.wrap{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:0 90px;gap:44px}
.kick{font-weight:700;letter-spacing:.28em;font-size:30px;color:#FF8A1E;text-transform:uppercase;background:rgba(255,255,255,.07);border-radius:40px;padding:14px 32px}
h1{font-family:Sora;font-weight:800;letter-spacing:-.045em;line-height:1.04;font-size:112px}h1 em{font-style:normal;color:#FF8A1E}
p{font-size:46px;line-height:1.4;color:#A1A1AA;font-weight:500}
.pill{background:#FF8A1E;color:#111;border-radius:50px;padding:22px 52px;letter-spacing:.2em;font-weight:700;font-size:30px;text-transform:uppercase}
.list{display:flex;flex-direction:column;gap:26px;width:100%}.list div{display:flex;align-items:center;gap:30px;background:#14161C;border:2px solid #24272F;border-radius:28px;padding:34px 40px;font-size:44px;font-weight:600;text-align:left}.list span{font-size:64px}
.top{position:absolute;top:120px;left:0;right:0;display:flex;justify-content:center;align-items:center;gap:14px}`;
const page = (w, h, body) => `<!doctype html><html><head><meta charset="utf-8"><style>${css}body{width:${w}px;height:${h}px}</style></head><body><div class="glow" style="left:${w/2-650}px;top:${h/2-650}px"></div><div class="grid"></div>${body}</body></html>`;
const top = `<div class="top">${chakra(56)}${wm(44)}</div>`;
const story = (b) => page(1080, 1920, top + `<div class="wrap">${b}</div>`);
const ex = (n, title, say, get) => story(`<div class="kick">How to use · ${n}</div><h1 style="font-size:92px">${title}</h1><div class="list"><div style="flex-direction:column;align-items:flex-start;gap:14px"><span style="font-size:30px;color:#FF8A1E;letter-spacing:.2em;font-weight:700">YOU SAY</span><span style="font-size:46px">${say}</span></div><div style="flex-direction:column;align-items:flex-start;gap:14px;border-color:#FF8A1E"><span style="font-size:30px;color:#FF8A1E;letter-spacing:.2em;font-weight:700">KRISH AI GIVES YOU</span><span style="font-size:44px">${get}</span></div></div>`);
const items = {
  'howto-1': story(`<div class="kick">How to use</div><h1 style="font-size:100px">Just <em>say it.</em></h1><div class="list"><div><span>1️⃣</span>Type or speak your task</div><div><span>2️⃣</span>Hindi, English or Hinglish</div><div><span>3️⃣</span>Get finished work back</div></div><p>No tech words. Talk the way you talk.</p>`),
  'howto-2': ex('01', 'Slides in <em>one line</em>', '"Bhai, climate change pe 10 slide ki PPT bana do"', '📊 A full deck with slides, speaker notes and design'),
  'howto-3': ex('02', 'Notes for <em>exam night</em>', '"Kal exam hai. Chapter 5 ke short notes do"', '📚 Key points, diagrams and a quick revision list'),
  'howto-4': ex('03', 'A plan for <em>your week</em>', '"Is hafte 6 deadlines hain. Plan bana do"', '🗓️ Every deadline in order, day by day'),
  'howto-cover': page(1080, 1920, `<div class="wrap">${chakra(420)}</div>`),
};
(async () => { const b = await chromium.launch(); const p = await b.newPage({viewport:{width:1080,height:1920}});
  for (const [k, h] of Object.entries(items)) { await p.setContent(h, { waitUntil: 'networkidle' }); await p.evaluate(() => document.fonts.ready); await p.screenshot({ path: `${out}/${k}.png` }); }
  await b.close(); })();
