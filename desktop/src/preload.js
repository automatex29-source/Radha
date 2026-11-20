// Lets krishai.net know it's running inside the desktop app, and ask it a few things (version, updates,
// start with the computer). Nothing else from the computer is reachable from the page.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("krishDesktop", {
  isDesktop: true,
  platform: process.platform,
  info: () => ipcRenderer.invoke("krish:info"),
  setStartAtLogin: (on) => ipcRenderer.invoke("krish:start-at-login", Boolean(on)),
  checkForUpdates: () => ipcRenderer.invoke("krish:check-updates"),
  installUpdate: () => ipcRenderer.invoke("krish:install-update"),
  onUpdate: (fn) => {
    const listener = (_e, state) => fn(state);
    ipcRenderer.on("krish:update", listener);
    return () => ipcRenderer.removeListener("krish:update", listener);
  },
});
