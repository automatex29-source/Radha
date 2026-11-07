const { chakra, wordmark, fonts, endCard, run } = require('/mnt/project-files/marketing/pipeline/mk/brand.js');
const lines = [["📄","Yeh form kaise bharun?"],["💻","Kal presentation hai…"],["🏪","Dukaan ka poster kaun banayega?"],["📱","Beta, yeh message kaise bhejte hain?"],["😰","Interview mein kya bolun?"],["📚","6 chapters, 1 raat"],["🧾","GST bill samajh nahi aa raha"],["✉️","Leave ka email kaise likhun?"],["🍲","Mehmaan 20, plan zero"],["📊","Boss ko report chahiye, abhi"],["🎂","Didi ki shaadi ka speech?"],["🗓️","Is hafte 6 deadlines"],["🏥","Report mein kya likha hai?"],["✈️","Trip plan kaun karega?"],["📝","Resume mein kya likhun?"],["💸","Budget phir se khatam"],["🧮","Maths ka homework"],["📦","Orders ka hisaab"],["🗣️","English mein kaise bolun?"],["😵","Sab kuch ek saath"]];
let tt=0.3, gap=0.85; const times=[]; for(const l of lines){times.push(+tt.toFixed(2)); tt+=gap; gap=Math.max(0.17,gap*0.86);} // ends ~ <10s
let seed=7; const rnd=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
const pos=lines.map((_,i)=>[80+rnd()*420, 260+((i*397)%1300)+rnd()*60, -6+rnd()*12]);
// light dots: along 24 spokes + scatter
const dots=[]; for(let s=0;s<24;s++){const a=s/24*2*Math.PI; for(let r=70;r<1150;r+=34+rnd()*20){dots.push([540+Math.cos(a)*r+(rnd()-.5)*18,960+Math.sin(a)*r+(rnd()-.5)*18,r]);}}
for(let i=0;i<420;i++){const a=rnd()*2*Math.PI,r=60+rnd()*1150; dots.push([540+Math.cos(a)*r,960+Math.sin(a)*r,r]);}
const S={total:26,times,pos,dots,end:20.6};
const html=`<!doctype html><html><head><meta charset="utf-8"><style>${fonts}*{margin:0;box-sizing:border-box}body{width:1080px;height:1920px;background:#030407;overflow:hidden;font-family:Inter;color:#F5F5F5;position:relative}
.b{position:absolute;display:flex;align-items:center;gap:20px;background:rgba(20,24,34,.92);border:2px solid #2A2F3A;border-radius:30px;padding:26px 34px;font-size:44px;font-weight:600;white-space:nowrap;box-shadow:0 0 60px rgba(120,160,255,.10);opacity:0}
.b span{font-size:52px}
#stage{position:absolute;inset:0}
#cv{position:absolute;inset:0}
#spark{position:absolute;left:540px;top:960px;width:0;height:0}
#spark i{position:absolute;left:-14px;top:-14px;width:28px;height:28px;border-radius:50%;background:#FFB15A;box-shadow:0 0 40px 18px rgba(255,138,30,.85),0 0 160px 60px rgba(255,110,20,.35)}
.t{position:absolute;left:0;right:0;text-align:center;font-family:Sora;font-weight:800;letter-spacing:-.04em;opacity:0;text-shadow:0 4px 40px #000}
#t1,#t2,#t3{top:300px;font-size:92px;line-height:1.1}#t4{top:1330px;font-size:130px;line-height:1.05;color:#FF8A1E}
#vig{position:absolute;inset:0;background:radial-gradient(circle at 50% 50%,transparent 40%,rgba(0,0,0,.75))}
</style></head><body><div id="stage">${lines.map((l,i)=>`<div class="b" id="b${i}"><span>${l[0]}</span>${l[1]}</div>`).join('')}</div>
<canvas id="cv" width="1080" height="1920"></canvas><div id="spark"><i></i></div>
<div class="t" id="t1">Saal bhar ki<br>bhaag-daud…</div><div class="t" id="t2">Aaj sab<br>ek taraf.</div><div class="t" id="t3">Bas diye, mithai<br>aur apne log.</div><div class="t" id="t4">Shubh<br>Deepavali 🪔</div>
<div id="vig"></div>${endCard(wordmark(160),'Your saarthi for every task','Happy Diwali from EmpireX')}</body></html>`;
function render(t,S){const cl=x=>Math.min(1,Math.max(0,x));const back=x=>{x=cl(x);return 1+2.7*Math.pow(x-1,3)+1.7*Math.pow(x-1,2)};
 const st=document.getElementById('stage');
 // bubbles phase
 if(t<10){st.style.display='block';const shake=t>6?(t-6)*3.5:0;st.style.transform=`translate(${Math.sin(t*53)*shake}px,${Math.cos(t*41)*shake}px)`;
  S.times.forEach((ti,i)=>{const e=document.getElementById('b'+i),u=t-ti;const [x,y,r]=S.pos[i];
   if(u<0){e.style.opacity=0;return;} const newest=S.times.filter(z=>z<=t).length-1; const age=newest-i;
   e.style.left=Math.max(40,Math.min(x,1040-e.offsetWidth))+'px';e.style.top=y+'px';e.style.opacity=Math.min(cl(u/.12),age>3?0.35:1);e.style.transform=`rotate(${r}deg) scale(${back(u/.3)})`;});
 } else st.style.display='none';
 // spark + lights
 const sp=document.querySelector('#spark i');const cv=document.getElementById('cv'),c=cv.getContext('2d');c.clearRect(0,0,1080,1920);
 if(t>=10.6&&t<S.end){const u=t-10.6;sp.style.opacity=1;const sc=u<1.6?back(u/0.6):1+0.08*Math.sin(u*6);sp.style.transform=`scale(${sc*(1+Math.max(0,u-1.6)*0.6)})`;
  if(u>1.6){const R=(u-1.6)*190; for(const [x,y,r] of S.dots){if(r>R)continue;const a=cl((R-r)/120);c.globalAlpha=a;c.fillStyle='#FF9A3C';c.shadowColor='#FF8A1E';c.shadowBlur=14;c.beginPath();c.arc(x,y,3.4,0,7);c.fill();}}
 } else sp.style.opacity=0;
 const show=(id,a,b)=>{const e=document.getElementById(id);const v=t<a?0:t<b?cl((t-a)/.35)*cl((b-t)/.3):0;e.style.opacity=v;e.style.transform=`translateY(${(1-cl((t-a)/.4))*30}px)`;};
 show('t1',11.4,13.7);show('t2',13.8,16.1);show('t3',16.2,18.6);show('t4',18.4,S.end+0.2);
 window.endAnim(t,S.end);}
run(html,render,S,process.argv[2]||'frames');
