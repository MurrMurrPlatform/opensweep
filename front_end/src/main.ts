import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from '@/App.vue'
import AuthConfigErrorView from '@/views/AuthConfigErrorView.vue'
import { authEnabled } from '@/services/auth'
import router from '@/router'
import '@/styles/index.scss'

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
