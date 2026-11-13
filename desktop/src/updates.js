// Updates. New versions are published to the "desktop-latest" release on GitHub by .github/workflows/desktop.yml.
// Windows and Linux download the update quietly and install it the next time Krish restarts.
// macOS only installs updates by itself for apps signed with a paid Apple certificate, so until Krish has one
// the Mac app says a new version is ready and opens the download.
const { app, dialog, Notification, shell } = require("electron");

const MAC_DOWNLOAD = "https://github.com/automatex29-source/Radha/releases/download/desktop-latest/Krish-AI-Mac.dmg";
const EVERY = 4 * 60 * 60 * 1000;

let updater = null;
let current = { status: "idle" }; // idle | checking | none | available | downloading | ready | error
let getWindow = () => null;
let userAsked = false;

function set(next) {
  current = { ...current, ...next };
  const win = getWindow();
  if (win && !win.isDestroyed()) win.webContents.send("krish:update", current);
}

function notify(title, body, onClick) {
  if (!Notification.isSupported()) return;
  const n = new Notification({ title, body });
  if (onClick) n.on("click", onClick);
  n.show();
}

function start(windowGetter) {
  getWindow = windowGetter;
  if (!app.isPackaged) return; // nothing to update while developing
  try {
    ({ autoUpdater: updater } = require("electron-updater"));
  } catch { return; }
  const isMac = process.platform === "darwin";
  updater.autoDownload = !isMac;
  updater.autoInstallOnAppQuit = true;
  updater.logger = null;

  updater.on("checking-for-update", () => set({ status: "checking" }));
  updater.on("update-not-available", () => {
    set({ status: "none" });
    if (userAsked) dialog.showMessageBox({ type: "info", message: "Krish is up to date", detail: `You have the newest version, ${app.getVersion()}.` });
    userAsked = false;
  });
  updater.on("update-available", (info) => {
    set({ status: isMac ? "available" : "downloading", version: info.version });
    if (isMac) {
      notify("A new Krish is ready", `Version ${info.version} is out. Click to download it.`, () => shell.openExternal(MAC_DOWNLOAD));
      if (userAsked) shell.openExternal(MAC_DOWNLOAD);
    }
    userAsked = false;
  });
  updater.on("download-progress", (p) => set({ status: "downloading", percent: Math.round(p.percent || 0) }));
  updater.on("update-downloaded", (info) => {
    set({ status: "ready", version: info.version });
    notify("Krish update ready", `Version ${info.version} will be installed the next time Krish starts. Click to restart now.`, install);
  });
  updater.on("error", (err) => {
    set({ status: "error", message: "Couldn't check for updates. Check your internet connection." });
    if (userAsked) dialog.showMessageBox({ type: "warning", message: "Couldn't check for updates", detail: String(err?.message || err).slice(0, 300) });
    userAsked = false;
  });

  setTimeout(() => check(false), 10_000);
  setInterval(() => check(false), EVERY);
}

function check(asked) {
  if (!updater) {
    if (asked) dialog.showMessageBox({ type: "info", message: "Updates are off in this copy of Krish", detail: "This happens when Krish runs from its source code." });
    return current;
  }
  userAsked = Boolean(asked);
  if (current.status === "available" && process.platform === "darwin" && asked) { shell.openExternal(MAC_DOWNLOAD); return current; }
  updater.checkForUpdates().catch(() => {});
  return current;
}

function install() {
  if (process.platform === "darwin") { shell.openExternal(MAC_DOWNLOAD); return current; }
  if (updater && current.status === "ready") setImmediate(() => updater.quitAndInstall(true, true));
  return current;
}

module.exports = { start, check, install, state: () => current };
