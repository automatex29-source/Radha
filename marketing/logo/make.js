const { chakra, wordmark, fonts } = require('/mnt/project-files/marketing/pipeline/mk/brand.js');
// metallic chakra: same geometry, gradient ink + glow
const metal = (size,id)=>chakra(size,id,`url(#m${id})`).replace('<defs>',`<defs><linearGradient id="m${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".35" stop-color="#E9E4DC"/><stop offset=".6" stop-color="#B9B2A8"/><stop offset="1" stop-color="#F7F1E8"/></linearGradient>`);
const card=(W,H,s,transparent)=>`<html><head><style>${fonts}*{margin:0}body{width:${W}px;height:${H}px;overflow:hidden;background:${transparent?'transparent':'#05060A'};display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:Inter;color:#F5F5F5;position:relative}
.glow{position:absolute;left:50%;top:${transparent?50:44}%;width:${1100*s}px;height:${1100*s}px;transform:translate(-50%,-50%);background:radial-gradient(circle,rgba(255,138,30,.38) 0%,rgba(255,110,20,.12) 35%,rgba(0,0,0,0) 65%)}
.rays{position:absolute;left:50%;top:44%;width:${1800*s}px;height:${1800*s}px;transform:translate(-50%,-50%);background:repeating-conic-gradient(rgba(255,160,60,.07) 0 4deg,transparent 4deg 15deg);-webkit-mask:radial-gradient(circle,#000 10%,transparent 60%)}
.grain{position:absolute;inset:0;opacity:.08;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='.9'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)'/%3E%3C/svg%3E")}
.c svg{filter:drop-shadow(0 0 ${18*s}px rgba(255,138,30,.65)) drop-shadow(0 ${10*s}px ${30*s}px rgba(0,0,0,.6))}
.w{margin-top:${50*s}px;filter:drop-shadow(0 0 ${14*s}px rgba(255,138,30,.35))}
.t{margin-top:${34*s}px;font-size:${44*s}px;color:#D4D4D8;letter-spacing:.01em}
.p{margin-top:${44*s}px;background:linear-gradient(180deg,#FFA040,#FF7A10);color:#111;border-radius:${60*s}px;padding:${20*s}px ${52*s}px;letter-spacing:.22em;font-weight:800;font-size:${28*s}px;box-shadow:0 0 ${30*s}px rgba(255,138,30,.5)}
</style></head><body>${transparent?'':'<div class="rays"></div><div class="glow"></div><div class="grain"></div>'}
<div class="c" style="position:relative">${metal(Math.round(300*s),'a')}</div><div class="w" style="position:relative">${wordmark(Math.round(150*s))}</div>
${transparent?'':`<div class="t" style="position:relative">Your saarthi for every task</div><div class="p" style="position:relative">COMING SOON</div>`}</body></html>`;
(async()=>{const {chromium}=require('playwright');const b=await chromium.launch();
for(const [n,W,H,s,tr] of [['krish-ai-endcard-16x9',1920,1080,0.95,0],['krish-ai-endcard-9x16',1080,1920,1.15,0],['krish-ai-logo-transparent',1400,1000,1.4,1]]){
const p=await b.newPage({viewport:{width:W,height:H},deviceScaleFactor:2});await p.setContent(card(W,H,s,tr),{waitUntil:'networkidle'});await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
await p.screenshot({path:n+'.png',omitBackground:!!tr});}
await b.close();})();
