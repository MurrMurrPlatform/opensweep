import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from '@/App.vue'
import AuthConfigErrorView from '@/views/AuthConfigErrorView.vue'
import { authEnabled } from '@/services/auth'
import router from '@/router'
import '@/styles/index.scss'

// A production deploy replaces every hashed chunk under /assets, so a tab
// opened before the deploy fails to lazy-load route chunks (the server
// returns 404 for the old hashes). Vite reports this as vite:preloadError;
// reload to pick up the new index.html. Rate-limited so a genuinely broken
// deploy can't put the tab in a reload loop.
const CHUNK_RELOAD_AT = 'opensweep:chunk-reload-at'
window.addEventListener('vite:preloadError', (event) => {
  const lastReload = Number(sessionStorage.getItem(CHUNK_RELOAD_AT) ?? 0)
  if (Date.now() - lastReload < 10_000) return
  sessionStorage.setItem(CHUNK_RELOAD_AT, String(Date.now()))
  event.preventDefault()
  window.location.reload()
})

// Zitadel OIDC is the only supported auth — without it, refuse to boot the
// app shell and explain how to configure it (mirrors the backend's
// fail-hard startup guard in infrastructure/production_guards.py).
if (!authEnabled) {
  createApp(AuthConfigErrorView).mount('#app')
} else {
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.mount('#app')
}
