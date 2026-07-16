import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    eyebrow?: string
  }
}

export {}
