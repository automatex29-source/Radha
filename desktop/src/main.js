// Krish AI desktop app: krishai.net in its own window, with a tray icon, a keyboard shortcut that opens Krish
// from anywhere, "start with my computer", and updates that install themselves (see updates.js).
const { app, BrowserWindow, Menu, Tray, globalShortcut, ipcMain, nativeImage, nativeTheme, Notification, shell, session } = require("electron");
const path = require("path");
const fs = require("fs");
const updates = require("./updates");

const APP_URL = process.env.KRISH_URL || "https://krishai.net";
const APP_ORIGIN = new URL(APP_URL).origin;
const IS_MAC = process.platform === "darwin";
const SHORTCUT = IS_MAC ? "Command+Option+K" : "Control+Alt+K";
const SHORTCUT_LABEL = IS_MAC ? "⌥⌘K" : "Ctrl + Alt + K";
// Pop-ups that must stay inside the app because they report back to the page that opened them:
// Google sign-in, and Razorpay's bank and card pages.
const POPUP_HOSTS = [/^accounts\.google\.com$/, /(^|\.)razorpay\.com$/];

let win = null;
let tray = null;
let quitting = false;

// ---------------------------------------------------------------- one copy only
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => show());
}
app.setAppUserModelId("net.krishai.desktop");

// ---------------------------------------------------------------- small saved settings
const prefsFile = () => path.join(app.getPath("userData"), "prefs.json");
function readPrefs() {
  try { return JSON.parse(fs.readFileSync(prefsFile(), "utf8")); } catch { return {}; }
}
function savePrefs(patch) {
  const next = { ...readPrefs(), ...patch };
  try { fs.writeFileSync(prefsFile(), JSON.stringify(next)); } catch { /* not important */ }
  return next;
}

const isAppUrl = (url) => { try { return new URL(url).origin === APP_ORIGIN; } catch { return false; } };
const isPopupUrl = (url) => {
  if (!url || url === "about:blank") return true;
  try { const h = new URL(url).hostname; return POPUP_HOSTS.some((re) => re.test(h)); } catch { return false; }
};
const openOutside = (url) => { if (/^(https?|mailto|tel):/i.test(url)) shell.openExternal(url); };

// ---------------------------------------------------------------- the window
function createWindow() {
  const prefs = readPrefs();
  const bounds = prefs.bounds || {};
  win = new BrowserWindow({
    width: bounds.width || 1200,
    height: bounds.height || 800,
    x: bounds.x, y: bounds.y,
    minWidth: 380, minHeight: 520,
    title: "Krish AI",
    icon: path.join(__dirname, "..", "build", "icon.png"),
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#0b0d14" : "#ffffff",
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
    },
  });
  if (prefs.maximized) win.maximize();

  win.once("ready-to-show", () => {
    if (!process.argv.includes("--hidden")) win.show();
  });

  // Remember where the window was.
  const remember = () => {
    if (!win || win.isDestroyed() || win.isMinimized()) return;
    savePrefs({ maximized: win.isMaximized(), ...(win.isMaximized() ? {} : { bounds: win.getBounds() }) });
  };
  win.on("resize", remember);
  win.on("move", remember);

  // Closing the window keeps Krish in the tray, so the shortcut still works.
  win.on("close", (e) => {
    if (quitting) return;
    e.preventDefault();
    win.hide();
    if (!IS_MAC && !readPrefs().toldAboutTray && Notification.isSupported()) {
      savePrefs({ toldAboutTray: true });
      new Notification({
        title: "Krish is still here",
        body: `Krish keeps running in the tray. Press ${SHORTCUT_LABEL} to open it, or right-click the tray icon to quit.`,
      }).show();
    }
  });

  const wc = win.webContents;

  // Links to other sites open in the normal browser; sign-in and payment pop-ups stay in the app.
  wc.setWindowOpenHandler(({ url }) => {
    if (isAppUrl(url)) { win.loadURL(url); return { action: "deny" }; }
    if (isPopupUrl(url)) {
      return { action: "allow", overrideBrowserWindowOptions: { width: 520, height: 680, autoHideMenuBar: true, parent: win } };
    }
    openOutside(url);
    return { action: "deny" };
  });
  // Full-page moves away from Krish (connecting Gmail, Notion and so on) stay in the window, because those
  // sign-ins come back to Krish. Anything that isn't a web page goes to the system.
  wc.on("will-navigate", (e, url) => {
    if (!/^https?:/i.test(url)) { e.preventDefault(); openOutside(url); }
  });

  // No internet, or krishai.net is waking up: show a friendly page that tries again.
  wc.on("did-fail-load", (_e, code, _desc, url, isMainFrame) => {
    if (!isMainFrame || code === -3 /* cancelled */) return;
    win.loadFile(path.join(__dirname, "offline.html"), { query: { to: isAppUrl(url) ? url : APP_URL } });
  });

  // Right-click: copy, paste and spelling suggestions, like a browser.
  wc.on("context-menu", (_e, p) => {
    const items = [];
    for (const word of p.dictionarySuggestions.slice(0, 4)) items.push({ label: word, click: () => wc.replaceMisspelling(word) });
    if (p.misspelledWord) items.push({ label: "Add to dictionary", click: () => wc.session.addWordToSpellCheckerDictionary(p.misspelledWord) }, { type: "separator" });
    if (p.linkURL && !isAppUrl(p.linkURL)) items.push({ label: "Open link in browser", click: () => openOutside(p.linkURL) }, { type: "separator" });
    if (p.isEditable) items.push({ role: "cut" }, { role: "copy" }, { role: "paste" }, { type: "separator" }, { role: "selectAll" });
    else if (p.selectionText) items.push({ role: "copy" });
    else items.push({ label: "Back", enabled: wc.navigationHistory.canGoBack(), click: () => wc.navigationHistory.goBack() },
      { label: "Reload", click: () => wc.reload() });
    Menu.buildFromTemplate(items).popup();
  });

  win.loadURL(APP_URL);
}

function show() {
  if (!win || win.isDestroyed()) { createWindow(); win.once("ready-to-show", () => win.show()); return; }
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}
function toggle() {
  if (win && win.isVisible() && win.isFocused()) win.hide();
  else show();
}
function goHome(pathname = "/") {
  show();
  win.loadURL(new URL(pathname, APP_URL).toString());
}

// ---------------------------------------------------------------- start with the computer
const startsAtLogin = () => app.getLoginItemSettings({ args: ["--hidden"] }).openAtLogin;
function setStartAtLogin(on) {
  app.setLoginItemSettings({ openAtLogin: Boolean(on), openAsHidden: true, args: ["--hidden"] });
  savePrefs({ startAtLogin: Boolean(on) });
  buildTray();
  return startsAtLogin();
}

// ---------------------------------------------------------------- tray
function trayImage() {
  const dir = path.join(__dirname, "..", "build");
  if (IS_MAC) {
    const img = nativeImage.createFromPath(path.join(dir, "trayTemplate.png"));
    img.setTemplateImage(true);
    return img;
  }
  // A white chakra on a dark taskbar, a black one on a light taskbar.
  const dark = nativeTheme.shouldUseDarkColorsForSystemIntegratedUI ?? nativeTheme.shouldUseDarkColors;
  return nativeImage.createFromPath(path.join(dir, `${dark ? "tray-light" : "tray"}-32.png`)).resize({ width: 16, height: 16 });
}

function buildTray() {
  if (!tray) {
    tray = new Tray(trayImage());
    tray.setToolTip(`Krish AI (${SHORTCUT_LABEL})`);
    tray.on("click", () => (IS_MAC ? tray.popUpContextMenu() : toggle()));
    nativeTheme.on("updated", () => tray && tray.setImage(trayImage()));
  }
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open Krish", accelerator: SHORTCUT, click: show },
    { label: "New chat", click: () => goHome("/") },
    { type: "separator" },
    ...(process.platform === "linux" ? [] : [
      { label: "Start with my computer", type: "checkbox", checked: startsAtLogin(), click: (item) => setStartAtLogin(item.checked) }]),
    { label: "Check for updates", click: () => updates.check(true) },
    { type: "separator" },
    { label: `Krish AI ${app.getVersion()}`, enabled: false },
    { label: "Quit Krish", click: () => { quitting = true; app.quit(); } },
  ]));
}

// ---------------------------------------------------------------- the page can ask a few things
function fromApp(e) { return isAppUrl(e.senderFrame?.url || ""); }
ipcMain.handle("krish:info", (e) => (fromApp(e) ? {
  version: app.getVersion(), platform: process.platform, shortcut: SHORTCUT_LABEL,
  startAtLogin: startsAtLogin(), update: updates.state(),
} : null));
ipcMain.handle("krish:start-at-login", (e, on) => (fromApp(e) ? setStartAtLogin(on) : null));
ipcMain.handle("krish:check-updates", (e) => (fromApp(e) ? updates.check(true) : null));
ipcMain.handle("krish:install-update", (e) => (fromApp(e) ? updates.install() : null));

// ---------------------------------------------------------------- start
if (app.hasSingleInstanceLock()) {
  app.whenReady().then(() => {
    // Look like plain Chrome, so Google sign-in doesn't refuse the app.
    const ua = session.defaultSession.getUserAgent().split(" ")
      .filter((part) => !/^(Electron|KrishAI|krish-desktop)\//i.test(part)).join(" ");
    session.defaultSession.setUserAgent(ua);
    app.userAgentFallback = ua;

    // The microphone (voice mode), notifications and the clipboard, only for Krish itself.
    session.defaultSession.setPermissionRequestHandler((wc, permission, done, details) => {
      const allowed = ["media", "notifications", "clipboard-read", "clipboard-sanitized-write", "fullscreen", "fileSystem"];
      done(isAppUrl(details.requestingUrl || wc.getURL()) && allowed.includes(permission));
    });

    // First run: start with the computer, as most people expect from a tray app. They can turn it off.
    if (readPrefs().startAtLogin === undefined && app.isPackaged) setStartAtLogin(true);

    createWindow();
    buildTray();
    if (!globalShortcut.register(SHORTCUT, toggle)) console.warn(`Shortcut ${SHORTCUT} is taken by another app`);
    updates.start(() => win);
  });
}

app.on("activate", show); // Mac: clicking the Dock icon
app.on("before-quit", () => { quitting = true; });
app.on("will-quit", () => globalShortcut.unregisterAll());
app.on("window-all-closed", () => { /* stay in the tray */ });
