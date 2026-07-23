// AURA preload — the only bridge between the console (renderer) and Electron.
// Exposes window controls for the custom title bar; nothing else.
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('aura', {
  isElectron: true,
  minimize: () => ipcRenderer.send('win:minimize'),
  toggleMaximize: () => ipcRenderer.send('win:toggleMaximize'),
  close: () => ipcRenderer.send('win:close'),
  // U75: the console tells Electron when AURA controls the screen so the
  // overlay (glowing cursor ring + abort banner) can show.
  screenControl: (active) => ipcRenderer.send('aura:screen-control', !!active),
  // U95: restart the brain child process (loads new code / config).
  restartBrain: () => ipcRenderer.invoke('aura:restart-brain'),
  // U170: real app version for the About dialog (stamped per release build).
  appVersion: () => ipcRenderer.invoke('aura:app-version'),
  // U178: manual update check that reports WHY nothing happened.
  checkUpdate: () => ipcRenderer.invoke('aura:check-update'),
  // U197: the update downloads itself in the background; the console only
  // hears about it once it is staged and installing is instant.
  onUpdateReady: (cb) => {
    const handler = (_e, info) => cb(info)
    ipcRenderer.on('aura:update-ready', handler)
    return () => ipcRenderer.removeListener('aura:update-ready', handler)
  },
  installUpdate: () => ipcRenderer.invoke('aura:install-update'),
  dismissUpdate: (tag) => ipcRenderer.invoke('aura:dismiss-update', tag),
})
