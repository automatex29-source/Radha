const { chakra, wordmark, fonts } = require('/mnt/project-files/marketing/pipeline/mk/brand.js');
const fs=require('fs');
const W=1080, H=+(process.env.H||1350), T=+(process.env.T||0);
let seed=11; const rnd=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
const sparks=Array.from({length:140},()=>[rnd()*W,rnd()*H*0.62,1+rnd()*3.2,rnd()*6.28,0.5+rnd()]);
const bursts=[[220,H*0.16,'#FFB15A'],[860,H*0.12,'#FFD29A'],[540,H*0.07,'#FF8A1E'],[120,H*0.36,'#FFD29A'],[960,H*0.33,'#FFB15A']];
const diya=(x,s)=>`<div class="diya" style="left:${x}px;transform:scale(${s})"><div class="fl"></div><div class="bowl"></div></div>`;
const html=`<!doctype html><html><head><meta charset="utf-8"><style>${fonts}*{margin:0;box-sizing:border-box}
body{width:${W}px;height:${H}px;overflow:hidden;position:relative;font-family:Inter;color:#F5F5F5;background:radial-gradient(ellipse at 50% 78%,#3a1604 0%,#170905 38%,#07080B 75%)}
#cv{position:absolute;inset:0}
.rang{position:absolute;left:50%;top:${H*0.5}px;transform:translate(-50%,-50%);opacity:.18}
.c{position:absolute;left:0;right:0;text-align:center}
#hi{top:${H*0.30}px;font-family:'Noto Sans Devanagari';font-size:64px;color:#FFD29A;letter-spacing:.02em}
#big{top:${H*0.30+95}px;font-family:Sora;font-weight:800;font-size:150px;line-height:.98;letter-spacing:-.045em;text-shadow:0 0 60px rgba(255,138,30,.55)}
#big em{font-style:normal;color:#FF8A1E}
#wish{top:${H*0.30+430}px;font-size:40px;line-height:1.45;color:#E7E2DA;padding:0 120px}
.diyas{position:absolute;left:0;right:0;top:${H-(H>1500?560:390)}px;height:140px}
.diya{position:absolute;width:120px;height:120px;transform-origin:50% 100%}
.bowl{position:absolute;bottom:0;left:0;width:120px;height:52px;border-radius:0 0 60px 60px;background:linear-gradient(#E8742A,#8A3410);box-shadow:0 0 50px rgba(255,138,30,.45)}
.fl{position:absolute;left:44px;bottom:44px;width:32px;height:62px;border-radius:50% 50% 50% 50%/62% 62% 38% 38%;background:radial-gradient(circle at 50% 75%,#FFF6D6 0,#FFD24A 35%,#FF8A1E 70%,transparent 72%);filter:drop-shadow(0 0 22px #FFB13A) drop-shadow(0 0 50px rgba(255,138,30,.8))}
#sign{position:absolute;left:0;right:0;bottom:${H>1500?230:70}px;display:flex;align-items:center;justify-content:center;gap:26px;font-size:34px;color:#A1A1AA}
#sign b{font-family:Sora;font-weight:800;color:#F5F5F5;font-size:44px;letter-spacing:.06em}
#sign i{width:2px;height:54px;background:#3A3F4A}
</style></head><body><canvas id="cv" width="${W}" height="${H}"></canvas>
<div class="rang">${chakra(980,'rg','#FF8A1E')}</div>
<div class="c" id="hi">शुभ दीपावली</div>
<div class="c" id="big">Happy<br><em>Diwali</em> 🪔</div>
<div class="c" id="wish">May your home be full of light, your heart full of joy, and your year full of good news.</div>
<div class="diyas">${diya(150,.9)}${diya(330,1.05)}${diya(480,1.25)}${diya(650,1.05)}${diya(830,.9)}</div>
<div id="sign"><span>With love from</span><b>EMPIREX</b><i></i>${wordmark(48)}</div>
<script>window.S=${JSON.stringify({sparks,bursts})};
window.draw=function(t){const c=document.getElementById('cv').getContext('2d');c.clearRect(0,0,${W},${H});
for(const [x,y,r,ph,sp] of S.sparks){const a=.35+.65*Math.abs(Math.sin(ph+t*2.2*sp));c.globalAlpha=a;c.fillStyle='#FFD29A';c.shadowColor='#FF8A1E';c.shadowBlur=12;c.beginPath();c.arc(x,y,r,0,7);c.fill();}
S.bursts.forEach(([x,y,col],i)=>{const per=2.4,u=((t+i*0.53)%per)/per;const R=40+u*190;const n=26;c.globalAlpha=(1-u)*(t===0?0:1)+(t===0?.9:0);c.fillStyle=col;c.shadowColor=col;c.shadowBlur=16;
 const RR=t===0?150:R;for(let k=0;k<n;k++){const a=k/n*6.283;for(let j=0;j<3;j++){const rr=RR*(1-j*.13);c.beginPath();c.arc(x+Math.cos(a)*rr,y+Math.sin(a)*rr+(t===0?0:u*u*40),3.2-j*.8,0,7);c.fill();}}});
c.globalAlpha=1;document.querySelectorAll('.fl').forEach((f,i)=>{f.style.transform='scaleY('+(1+.08*Math.sin(t*9+i*1.7))+') scaleX('+(1+.05*Math.sin(t*7+i))+')';});
document.querySelector('.rang').style.transform='translate(-50%,-50%) rotate('+(t*6)+'deg)';}</script></body></html>`;
(async()=>{const {chromium}=require('playwright');const br=await chromium.launch();const p=await br.newPage({viewport:{width:W,height:H}});
await p.setContent(html,{waitUntil:'networkidle'});await p.evaluate(()=>document.fonts.ready);
const out=process.argv[2];
if(!T){await p.evaluate(()=>draw(0));await p.screenshot({path:out,type:'jpeg',quality:94});}
else{fs.mkdirSync(out,{recursive:true});for(let f=0;f<T*30;f++){await p.evaluate(t=>draw(t),f/30);await p.screenshot({path:`${out}/f${String(f).padStart(4,'0')}.jpg`,type:'jpeg',quality:90});}}
await br.close();})();
