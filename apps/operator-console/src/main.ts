import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import OverlayView from './views/OverlayView.vue'

// U265: `#overlay` mounts the presentation overlay INSTEAD of the console.
// It is the same app at the same origin — character choice, brain URL and WS
// wiring come along for free — but rendered bare: no shell, no header,
// transparent ground, so the window that hosts it (Electron's click-through
// overlay, or a plain browser window) shows the slides through it.
const isOverlay = window.location.hash.startsWith('#overlay')

const app = createApp(isOverlay ? OverlayView : App)
app.use(createPinia())
app.mount('#app')
