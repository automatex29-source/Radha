// Runs one of an app's server functions (api/<name>.js) for appbackend.py, inside the sandbox.
// The function gets (input, ctx). Everything ctx can do (database, AI, email, outside APIs) is a call back to
// the server over stdin/stdout, where it is checked; the sandbox itself has no network and no database.
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
import path from "node:path";

const MARK = "\x1eR";
const write = process.stdout.write.bind(process.stdout);
const send = (m) => write(MARK + JSON.stringify(m) + "\n");
const show = (x) => {
  if (typeof x === "string") return x;
  if (x instanceof Error) return x.stack || x.message;
  try { return JSON.stringify(x); } catch { return String(x); }
};
for (const level of ["log", "info", "warn", "error", "debug"]) {
  console[level] = (...a) => process.stderr.write(`[${level}] ${a.map(show).join(" ")}\n`);
}

class AppError extends Error {
  constructor(message, status) { super(message); this.status = status || 400; }
}

let seq = 0;
const waiting = new Map();
const call = (op, args) => new Promise((resolve, reject) => {
  const id = ++seq;
  waiting.set(id, { resolve, reject });
  send({ t: "call", id, op, args });
});

const rl = createInterface({ input: process.stdin });
rl.on("line", (line) => {
  let m;
  try { m = JSON.parse(line); } catch { return; }
  if (m.t === "start") { start(m); return; }
  const w = waiting.get(m.id);
  if (!w) return;
  waiting.delete(m.id);
  if (m.ok) w.resolve(m.result); else w.reject(new AppError(m.error, m.status));
});

async function start(m) {
  try {
    const mod = await import(pathToFileURL(path.resolve(m.file)).href);
    const fn = typeof mod.default === "function" ? mod.default : (mod.handler || mod.main);
    if (typeof fn !== "function") throw new AppError(`${m.file} must export a default async function (input, ctx)`, 500);
    const db = {
      list: (c, o) => call("list", [c, o || {}]),
      get: (c, id) => call("get", [c, id]),
      find: (c, where) => call("find", [c, where || {}]),
      count: (c, where) => call("count", [c, where || {}]),
      add: (c, data, o) => call("add", [c, data, o || {}]),
      update: (c, id, data) => call("update", [c, id, data]),
      remove: (c, id) => call("remove", [c, id]),
    };
    const ctx = {
      user: m.user || null,
      isAdmin: !!(m.user && m.user.isAdmin),
      db,
      ai: (prompt, o) => call("ai", [String(prompt), o || {}]),
      notify: (msg) => call("notify", [msg || {}]),
      fetch: (url, o) => call("fetch", [String(url), o || {}]),
      fail: (message, status) => { throw new AppError(String(message), status || 400); },
      requireUser: () => { if (!m.user) throw new AppError("Please log in first", 401); return m.user; },
      requireAdmin: () => { if (!(m.user && m.user.isAdmin)) throw new AppError("Only the app's admins can do this", 403); return m.user; },
    };
    const result = await fn(m.input === undefined ? null : m.input, ctx);
    send({ t: "done", ok: true, result: result === undefined ? null : result });
  } catch (e) {
    const status = e && Number.isInteger(e.status) && e.status >= 400 && e.status < 600 ? e.status : 500;
    const stack = e && e.stack ? String(e.stack).split("\n").slice(0, 5).join("\n") : "";
    send({ t: "done", ok: false, error: (e && e.message) || String(e), status, stack });
  }
}
