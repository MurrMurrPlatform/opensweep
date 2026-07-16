// Zitadel OIDC login (Authorization Code + PKCE via oidc-client-ts).
//
// Zitadel is the ONLY supported user auth: VITE_ZITADEL_AUTHORITY +
// VITE_ZITADEL_CLIENT_ID must be set at build time. Without them main.ts
// mounts AuthConfigErrorView instead of the app (mirroring the backend's
// fail-hard startup guard), so `authEnabled === false` never reaches the
// router or any view.
//
// The router guard (router/guards.ts) redirects unauthenticated navigations
// to Zitadel and returns through /auth/callback (views/AuthCallbackView.vue).
// The access token is a Zitadel JWT — the backend verifies it against the
// issuer's JWKS (back_end/infrastructure/oidc.py) and maps project roles
// (viewer/maintainer/admin) onto the User node.

import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'

const authority = import.meta.env.VITE_ZITADEL_AUTHORITY || ''
const clientId = import.meta.env.VITE_ZITADEL_CLIENT_ID || ''

export const authEnabled = Boolean(authority && clientId)

let manager: UserManager | null = null
// Kept in sync via oidc events so api.ts can read it synchronously.
let cachedToken = ''

function getManager(): UserManager {
  if (!manager) {
    manager = new UserManager({
      authority,
      client_id: clientId,
      redirect_uri: `${window.location.origin}/auth/callback`,
      post_logout_redirect_uri: window.location.origin,
      // offline_access → refresh token → silent renew without iframes
      // ("Refresh Token" must be checked on the Zitadel app).
      // projects:roles asserts viewer/maintainer/admin into the JWT;
      // resourceowner asserts the user's org — the backend tenancy root.
      scope:
        'openid profile email offline_access urn:zitadel:iam:org:projects:roles urn:zitadel:iam:user:resourceowner',
      userStore: new WebStorageStateStore({ store: window.localStorage }),
      automaticSilentRenew: true,
    })
    manager.events.addUserLoaded((user) => {
      cachedToken = user.access_token || ''
    })
    manager.events.addUserUnloaded(() => {
      cachedToken = ''
    })
  }
  return manager
}

/** Load the stored session (if any) and warm the token cache. */
export async function loadStoredUser(): Promise<User | null> {
  if (!authEnabled) return null
  const user = await getManager().getUser()
  if (user && !user.expired) {
    cachedToken = user.access_token || ''
    return user
  }
  return null
}

/** Synchronous accessor for api.ts — empty string when signed out/disabled. */
export function accessToken(): string {
  return cachedToken
}

export async function signIn(returnTo?: string): Promise<void> {
  await getManager().signinRedirect({
    state: { returnTo: returnTo || window.location.pathname + window.location.search },
  })
}

/** Zitadel registration — OIDC `prompt=create` lands on the sign-up form. */
export async function signUp(returnTo?: string): Promise<void> {
  await getManager().signinRedirect({
    prompt: 'create',
    state: { returnTo: returnTo || '/' },
  })
}

/** Finish the redirect on /auth/callback; returns the path to restore. */
export async function completeSignIn(): Promise<string> {
  const user = await getManager().signinRedirectCallback()
  cachedToken = user.access_token || ''
  const state = user.state as { returnTo?: string } | undefined
  return state?.returnTo || '/'
}

export async function signOut(): Promise<void> {
  if (!authEnabled) return
  cachedToken = ''
  await getManager().signoutRedirect()
}
