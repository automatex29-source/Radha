// Saved settings once used an older internal name. Move them to the current keys before anything reads them
// (this module is imported first), so nobody is signed out or loses their theme. The old name is decoded at run
// time so it never appears in the shipped code.
let old = "";
try { old = atob("cmFkaGE="); } catch { /* no atob: nothing to move */ }
const MOVES = [["_token", "kai_token"], ["-theme", "kai-theme"], ["_github_token", "kai_github_token"],
  [".voiceBargeIn", "kai.voiceBargeIn"]];
try {
  if (old) {
    for (const [suffix, to] of MOVES) {
      const value = localStorage.getItem(old + suffix);
      if (value !== null) {
        if (localStorage.getItem(to) === null) localStorage.setItem(to, value);
        localStorage.removeItem(old + suffix);
      }
    }
  }
} catch { /* storage blocked */ }
