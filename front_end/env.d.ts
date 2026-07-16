/// <reference types="vite/client" />

declare module '*.vue' {
  import { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL: string
  readonly VITE_APP_NAME: string
  // Zitadel OIDC login — both empty = auth disabled (services/auth.ts).
  readonly VITE_ZITADEL_AUTHORITY: string
  readonly VITE_ZITADEL_CLIENT_ID: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
