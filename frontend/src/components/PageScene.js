import { Wand2, FileText, Download, Sparkles, Zap, Clock, Bot, Mail, Bell, FolderKanban, Search, Newspaper, Globe, Wind, HeartHandshake } from "lucide-react";

/**
 * A small looping animation that shows what each page does: a page writing itself, a slide
 * whose chart grows, an app building next to its code, and so on. Everything is sized in
 * container units, so the scene scales with whatever box it sits in.
 */
const Tag = ({ icon: Icon, children, className = "", style }) => (
  <div className={`ks-tag ks-glass ${className}`} style={style}><Icon />{children}</div>
);

const DOC_LINES = [[10, 40, true], [16, 78], [21, 70], [26, 74], [31, 50], [40, 76, false, true], [45, 72, false, true],
  [50, 60, false, true], [59, 74], [64, 66], [69, 40]];

function Docs() {
  return (
    <>
      <div className="ks-paper ks-glass">
        {DOC_LINES.map(([top, w, title, hl], i) => (
          <div key={i} className={`ks-ln ${hl ? "ks-hl" : ""}`} style={{ top: `${top}%`, width: `${w}%`, height: title ? "4%" : undefined }}>
            <i style={{ animationDelay: `${i * 0.25}s` }} />
          </div>
        ))}
        <div className="ks-caret" style={{ left: "52%", top: "66%" }} />
      </div>
      <Tag icon={Wand2} className="ks-bob" style={{ left: "56%", top: "46%" }}>Make it formal</Tag>
      <Tag icon={FileText} className="ks-bob" style={{ left: "8%", top: "62%", animationDelay: ".6s" }}>Word</Tag>
      <Tag icon={Download} className="ks-bob" style={{ left: "72%", top: "12%", animationDelay: "1.2s" }}>PDF</Tag>
    </>
  );
}

function Decks() {
  return (
    <>
      <div className="ks-slide ks-glass ks-b1" />
      <div className="ks-slide ks-glass ks-b2" />
      <div className="ks-slide ks-glass ks-bob">
        <div className="ks-sl-title" /><div className="ks-sl-sub" />
        {[38, 55, 46, 70, 62].map((h, i) => (
          <div key={i} className="ks-bar" style={{ left: `${8 + i * 10}%`, height: `${h * 0.55}%`, animationDelay: `${i * 0.15}s` }} />
        ))}
        <div className="ks-donut" />
      </div>
      <Tag icon={Sparkles} className="ks-bob" style={{ left: "30%", top: "84%" }}>Designing slide 4 of 10</Tag>
    </>
  );
}

const CODE = ["#f472b6", "#60a5fa", "#a78bfa", "#34d399", "#fbbf24", "#60a5fa", "#f472b6", "#94a3b8"];
const BLOCKS = [[6, 14, 88, 8, 0, 0.35], [6, 27, 56, 26, 0.3, 1], [66, 27, 28, 26, 0.5, 0.55],
  [6, 58, 27, 30, 0.8, 0.45], [36.5, 58, 27, 30, 1, 0.45], [67, 58, 27, 30, 1.2, 0.45]];

function Apps() {
  return (
    <>
      <div className="ks-win ks-glass">
        <div className="ks-dots"><b /><b /><b /></div>
        {BLOCKS.map(([l, t, w, h, d, o], i) => (
          <div key={i} className="ks-blk" style={{ left: `${l}%`, top: `${t}%`, width: `${w}%`, height: `${h}%`, animationDelay: `${d}s`, "--o": o }} />
        ))}
      </div>
      <div className="ks-code">
        <div className="ks-rows">
          {[...CODE, ...CODE].map((c, i) => <b key={i} style={{ width: `${40 + (i * 23) % 55}%`, background: c }} />)}
        </div>
      </div>
      <div className="ks-tag ks-live"><Zap />Live</div>
    </>
  );
}

function Automations() {
  return (
    <>
      <svg className="ks-wire" viewBox="0 0 160 100" preserveAspectRatio="none" aria-hidden="true">
        <path id="ks-p1" d="M24 47 L 80 47" />
        <path id="ks-p2" d="M80 47 L 136 47" />
        <circle r="2" className="ks-pulse"><animateMotion dur="2.4s" repeatCount="indefinite"><mpath href="#ks-p1" /></animateMotion></circle>
        <circle r="2" className="ks-pulse ks-pulse-2"><animateMotion dur="2.4s" begin="1.2s" repeatCount="indefinite"><mpath href="#ks-p2" /></animateMotion></circle>
      </svg>
      <div className="ks-node" style={{ left: "15%" }}><div className="ks-ib"><Clock /></div><span>Every day, 9 AM</span></div>
      <div className="ks-node" style={{ left: "50%" }}><div className="ks-ib ks-main"><Bot /></div><span>Krish does the work</span></div>
      <div className="ks-node" style={{ left: "85%" }}><div className="ks-ib"><Mail /></div><span>Email to you</span></div>
      <Tag icon={Bell} className="ks-bob" style={{ left: "34%", top: "80%" }}>Sent 9:00 AM · done</Tag>
    </>
  );
}

function Projects() {
  return (
    <>
      <div className="ks-ftab" /><div className="ks-fback" />
      {[28, 42, 56].map((l, i) => (
        <div key={l} className="ks-file ks-glass" style={{ left: `${l}%`, animationDelay: `${i * 1.2}s` }}>
          <b style={{ width: "70%" }} /><b /><b style={{ width: "85%" }} /><b style={{ width: "55%" }} />
        </div>
      ))}
      <div className="ks-ffront"><FolderKanban />My project</div>
      <Tag icon={Search} className="ks-bob" style={{ left: "62%", top: "8%" }}>Found in 3 files</Tag>
    </>
  );
}

function Discover() {
  return (
    <>
      <div className="ks-globe">
        <i /><i style={{ animationDelay: "-2s" }} /><i style={{ animationDelay: "-4s" }} />
        <em style={{ top: "30%" }} /><em style={{ top: "50%" }} /><em style={{ top: "70%" }} />
      </div>
      <div className="ks-orbit">
        <Tag icon={Newspaper} style={{ left: "-30cqw", top: "-14cqw" }}>Top stories</Tag>
        <Tag icon={Sparkles} style={{ left: "16cqw", top: "6cqw" }}>Explained simply</Tag>
        <Tag icon={Globe} style={{ left: "-12cqw", top: "22cqw" }}>India + world</Tag>
      </div>
    </>
  );
}

function Counsellor() {
  return (
    <>
      <div className="ks-ring" /><div className="ks-ring" style={{ animationDelay: "-2.5s" }} /><div className="ks-orb" />
      <Tag icon={Wind} className="ks-bob" style={{ left: "8%", top: "22%" }}>Breathe in… 4</Tag>
      <Tag icon={HeartHandshake} className="ks-bob" style={{ left: "62%", top: "62%", animationDelay: "1s" }}>I'm here for you</Tag>
    </>
  );
}

const SCENES = { docs: Docs, decks: Decks, apps: Apps, automations: Automations, projects: Projects, discover: Discover, counsellor: Counsellor };

export default function PageScene({ name, className = "" }) {
  const Scene = SCENES[name];
  if (!Scene) return null;
  return (
    <div className={`ks-scene ks-${name} ${className}`} aria-hidden="true">
      <Scene />
    </div>
  );
}
