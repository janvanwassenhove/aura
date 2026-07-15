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
})
