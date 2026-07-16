<script setup lang="ts">
// Public marketing page (route name 'landing', exempt from the auth guard).
// Editorial style: Mona Sans, warm neutrals, numbered feature presentation
// with a live product panel, and an animated line-field hero background.
// Light/dark follows the app-wide data-theme attribute.
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowRight, Check, Github, Menu, Moon, Plus, Sun, X } from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'
import { signIn, signUp } from '@/services/auth'
import SpiralField from '@/components/landing/SpiralField.vue'
import SweepMark from '@/components/branding/SweepMark.vue'

const GITHUB_URL = 'https://github.com/MurrMurrPlatform/opensweep'

const { theme, toggle: toggleTheme } = useTheme()

const mobileOpen = ref(false)
const scrolled = ref(false)

const logIn = () => signIn('/')
const getStarted = () => signUp('/')

const navLinks = [
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Self-host', href: '#open-source' },
  { label: 'Cloud', href: '#cloud' },
  { label: 'FAQ', href: '#faq' },
]

const marqueeItems = [
  'Claude Code',
  'Codex',
  'opencode',
  'Anthropic API',
  'OpenAI-compatible',
  'Local models',
  'GitHub',
  'Docker Compose',
]

// ── How it works: stacked numbered accordion ────────────────────────────
const steps = [
  {
    title: 'Connect your GitHub',
    body: 'Install the GitHub App and pick a repository. That’s the whole setup. Agents work in throwaway clones and only ever reach your code through pull requests.',
  },
  {
    title: 'Run the predefined agents',
    body: 'Ready-made agents continuously look for bugs, issues, and improvements — and bring you feature ideas, AI news, and popular public repos relevant to your project.',
  },
  {
    title: 'Approve and merge',
    body: 'Everything they find lands on one dashboard. Approve the work you want done and an agent opens a draft PR, then keeps improving it until review passes. You merge.',
  },
]
const activeStep = ref(0)

// ── Flagship features: numbered list + product panel ────────────────────
const FEATURE_INTERVAL = 7000
const features = [
  {
    name: 'Docs that stay current',
    body: 'Agents write and maintain a documentation tree for every repo, and refresh it on every push. Export it to AGENTS.md with one pull request.',
  },
  {
    name: 'Agents on a schedule',
    body: 'The predefined agents sweep your code on a schedule — security, dependencies, dead code — and record exactly what they checked and when.',
  },
  {
    name: 'One findings inbox',
    body: 'Bugs, risks, and ideas arrive as tidy findings with evidence attached — not as chat scroll. Triage them like a to-do list.',
  },
  {
    name: 'From ticket to pull request',
    body: 'Approve a ticket and an agent opens a draft PR, then keeps fixing it until review passes. You review and merge like any other PR.',
  },
  {
    name: 'Bring your own LLM',
    body: 'Use the subscription you already pay for — Claude Code, Codex, or opencode — connect an API key, or point OpenSweep at a local LLM endpoint and run everything free.',
  },
]
const activeFeature = ref(0)
let featureTimer: number | undefined

function startFeatureTimer() {
  window.clearInterval(featureTimer)
  featureTimer = window.setInterval(() => {
    activeFeature.value = (activeFeature.value + 1) % features.length
  }, FEATURE_INTERVAL)
}

function selectFeature(i: number) {
  activeFeature.value = i
  startFeatureTimer()
}

// ── Trust cards ──────────────────────────────────────────────────────────
const trustCards = [
  {
    title: 'Only pull requests',
    body: 'Agents never push to your branches. Every change arrives as a draft PR you review and merge like any other.',
  },
  {
    title: 'Disposable sandboxes',
    body: 'Every run gets a fresh clone that is destroyed when the run ends. Nothing is mounted from your machines.',
  },
  {
    title: 'Freshness stamps',
    body: 'Every document and finding records what was verified, when, and at which revision — so “checked” actually means something.',
  },
  {
    title: 'SHA-bound convergence',
    body: 'Review verdicts bind to the exact commit and roll up into a single opensweep/converged status. Merge when it’s green.',
  },
]

const openSourcePoints = [
  'The full platform — no feature gates, no seat limits',
  'Your code and data stay on your own machines',
  'Local models run at zero cost on your own hardware',
  'One docker compose up and you’re live',
]

const freePlan = [
  'Unlimited repositories and seats',
  'The full dashboard and every agent',
  'Bring your own LLM, or run local models',
  'Self-host with Docker Compose',
  'Community support on GitHub',
]

const cloudPlan = [
  'Everything in Self-Hosted',
  'Hosted, managed, always up to date',
  'Organizations, invitations, and roles',
  'Managed GitHub App — connect in one click',
  'Priority support',
]

const faqs = [
  {
    q: 'What is OpenSweep?',
    a: 'OpenSweep is a dashboard for working with coding agents. Connect your GitHub and run the predefined AI agents — they continuously find bugs, issues, improvements, and feature ideas in your repositories. You approve the work you want done and get a pull request back.',
  },
  {
    q: 'Who is it for?',
    a: 'Developers who work with AI coding agents and want one place to run and review that work — and product owners who want a live view of bugs, improvements, and ideas without digging through chat logs and pull requests.',
  },
  {
    q: 'Will it write to my repositories?',
    a: 'Only through draft pull requests. Agents work in disposable clones of your repo, and every change reaches your branches the same way your team’s does: as a PR you review and merge.',
  },
  {
    q: 'Which AI models can I use?',
    a: 'Whichever you already love. Use your Claude Code, Codex, or opencode subscription, connect an Anthropic or OpenAI-compatible API key, or point OpenSweep at a local LLM endpoint — local models run completely free.',
  },
  {
    q: 'Is the self-hosted version limited?',
    a: 'No. Self-hosted OpenSweep is the full platform — every feature, unlimited repositories and seats, free forever.',
  },
  {
    q: 'When is the Cloud version coming?',
    a: 'We’re building it now. Cloud will add hosting, automatic updates, managed organizations, and one-click GitHub setup. Until then, self-hosting is a single docker compose up.',
  },
]

// ── SEO: title + JSON-LD, restored/removed when leaving the page ─────────
const PAGE_TITLE = 'OpenSweep — the dashboard for working with coding agents'
let jsonLdEl: HTMLScriptElement | null = null
let onScroll: (() => void) | null = null

onMounted(() => {
  document.title = PAGE_TITLE

  jsonLdEl = document.createElement('script')
  jsonLdEl.type = 'application/ld+json'
  jsonLdEl.textContent = JSON.stringify([
    {
      '@context': 'https://schema.org',
      '@type': 'SoftwareApplication',
      name: 'OpenSweep',
      applicationCategory: 'DeveloperApplication',
      operatingSystem: 'Web',
      description:
        'The source-available dashboard for working with coding agents. Connect your GitHub and run predefined AI agents that continuously find bugs, improvements, and feature ideas — then turn approved work into pull requests. Bring your own LLM: agent subscriptions, API keys, or a local endpoint.',
      url: window.location.origin,
      offers: [
        { '@type': 'Offer', name: 'Self-hosted (free)', price: '0', priceCurrency: 'USD' },
      ],
    },
    {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: faqs.map((f) => ({
        '@type': 'Question',
        name: f.q,
        acceptedAnswer: { '@type': 'Answer', text: f.a },
      })),
    },
  ])
  document.head.appendChild(jsonLdEl)

  document.documentElement.style.scrollBehavior = 'smooth'
  onScroll = () => { scrolled.value = window.scrollY > 8 }
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()

  startFeatureTimer()
})

onBeforeUnmount(() => {
  document.title = 'OpenSweep' // in-app tab title stays short
  jsonLdEl?.remove()
  document.documentElement.style.scrollBehavior = ''
  if (onScroll) window.removeEventListener('scroll', onScroll)
  window.clearInterval(featureTimer)
})
</script>

<template>
  <div class="landing min-h-full">
    <!-- ── Nav ─────────────────────────────────────────────────────────── -->
    <header
      class="fixed inset-x-0 top-0 z-50 transition-all duration-300"
      :class="scrolled ? 'lp-header-glass' : 'bg-transparent'"
    >
      <nav class="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5" aria-label="Main">
        <a href="#top" class="flex items-center gap-2.5">
          <SweepMark class="h-7 w-7 text-[var(--lp-ink)]" aria-hidden="true" />
          <span class="lp-display text-[17px]">OpenSweep</span>
        </a>

        <div class="hidden items-center gap-6 md:flex">
          <a
            v-for="link in navLinks"
            :key="link.href"
            :href="link.href"
            class="text-sm font-medium text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]"
          >
            {{ link.label }}
          </a>
        </div>

        <div class="flex items-center gap-2">
          <a
            :href="GITHUB_URL"
            target="_blank"
            rel="noopener"
            class="hidden rounded-full p-2 text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)] sm:block"
            aria-label="OpenSweep on GitHub"
          >
            <Github class="h-[18px] w-[18px]" />
          </a>
          <button
            type="button"
            class="rounded-full p-2 text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]"
            :aria-label="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
            @click="toggleTheme"
          >
            <Sun v-if="theme === 'dark'" class="h-[18px] w-[18px]" />
            <Moon v-else class="h-[18px] w-[18px]" />
          </button>
          <button
            type="button"
            class="hidden px-3 py-2 text-sm font-medium text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)] sm:block"
            @click="logIn"
          >
            Log in
          </button>
          <button type="button" class="lp-btn lp-btn-primary hidden sm:inline-flex" @click="getStarted">
            Get started
          </button>
          <button
            type="button"
            class="rounded-full p-2 text-[var(--lp-muted)] hover:text-[var(--lp-ink)] md:hidden"
            :aria-expanded="mobileOpen"
            aria-label="Toggle menu"
            @click="mobileOpen = !mobileOpen"
          >
            <X v-if="mobileOpen" class="h-5 w-5" />
            <Menu v-else class="h-5 w-5" />
          </button>
        </div>
      </nav>

      <div v-if="mobileOpen" class="lp-header-glass border-t border-[var(--lp-line)] px-5 pb-4 md:hidden">
        <a
          v-for="link in navLinks"
          :key="link.href"
          :href="link.href"
          class="block px-1 py-2.5 text-sm font-medium text-[var(--lp-muted)] hover:text-[var(--lp-ink)]"
          @click="mobileOpen = false"
        >
          {{ link.label }}
        </a>
        <div class="mt-3 flex gap-2 border-t border-[var(--lp-line)] pt-4">
          <button type="button" class="lp-btn lp-btn-outline flex-1" @click="logIn">Log in</button>
          <button type="button" class="lp-btn lp-btn-primary flex-1" @click="getStarted">Get started</button>
        </div>
      </div>
    </header>

    <main id="top">
      <!-- ── Hero ────────────────────────────────────────────────────────── -->
      <section class="relative overflow-hidden">
        <div class="lp-spiral pointer-events-none absolute inset-0" aria-hidden="true">
          <SpiralField :theme="theme" class="h-full w-full" />
        </div>

        <div class="relative mx-auto max-w-[1200px] px-5 pb-16 pt-36 sm:pt-44">
          <a
            :href="GITHUB_URL"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-2 rounded-full border border-[var(--lp-line)] bg-[var(--lp-card)] py-1.5 pl-3.5 pr-3 text-xs font-medium text-[var(--lp-muted)] transition-colors duration-200 hover:border-[var(--lp-line-strong)] hover:text-[var(--lp-ink)]"
          >
            Source-available
            <span class="lp-mono rounded-md bg-[var(--lp-panel)] px-1.5 py-0.5 text-[11px] text-[var(--lp-ink)]">free forever</span>
            <ArrowRight class="h-3 w-3" />
          </a>

          <h1 class="lp-display mt-7 max-w-[17ch] text-[44px] leading-[1.02] sm:text-[64px] lg:text-[72px]">
            The dashboard for<br />coding agents.
            <span class="text-[var(--lp-faint)]">What Linear and Jira should have&nbsp;been.</span>
          </h1>

          <p class="mt-7 max-w-[46ch] text-base leading-relaxed text-[var(--lp-muted)] sm:text-lg">
            Connect your GitHub and run the predefined AI agents. They continuously
            find bugs, improvements, and feature ideas — you approve the ones you
            want and get a pull request back.
          </p>

          <div class="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
            <button type="button" class="lp-btn lp-btn-primary lp-btn-lg group" @click="getStarted">
              Get started free
              <ArrowRight class="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </button>
            <a href="#open-source" class="lp-btn lp-btn-outline lp-btn-lg">Self-host it</a>
          </div>
          <p class="lp-mono mt-5 text-xs text-[var(--lp-faint)]">
            free to self-host · bring your own LLM · Cloud coming soon
          </p>

          <!-- Product panel -->
          <div class="relative mt-20" aria-hidden="true">
            <div class="overflow-hidden rounded-2xl border border-[var(--lp-line)] bg-[var(--lp-card)] shadow-[0_24px_80px_-32px_rgba(20,18,12,0.25)]">
              <div class="flex items-center gap-2 border-b border-[var(--lp-line)] px-5 py-3">
                <span class="h-2.5 w-2.5 rounded-full bg-[var(--lp-line-strong)]" />
                <span class="h-2.5 w-2.5 rounded-full bg-[var(--lp-line-strong)]" />
                <span class="h-2.5 w-2.5 rounded-full bg-[var(--lp-line-strong)]" />
                <span class="lp-mono ml-3 rounded-md bg-[var(--lp-panel)] px-2.5 py-0.5 text-[11px] text-[var(--lp-muted)]">
                  opensweep · acme/api
                </span>
              </div>
              <div class="grid grid-cols-1 text-left sm:grid-cols-[170px_1fr] lg:grid-cols-[170px_1fr_260px]">
                <div class="hidden border-r border-[var(--lp-line)] p-4 sm:block">
                  <div
                    v-for="item in ['Dashboard', 'Findings', 'Tickets', 'Docs', 'Runs', 'Health']"
                    :key="item"
                    class="rounded-lg px-3 py-1.5 text-[13px]"
                    :class="item === 'Findings' ? 'bg-[var(--lp-panel)] font-semibold text-[var(--lp-ink)]' : 'text-[var(--lp-faint)]'"
                  >
                    {{ item }}
                  </div>
                </div>
                <div class="p-5">
                  <div class="mb-3 flex items-center justify-between">
                    <span class="text-[13px] font-semibold text-[var(--lp-ink)]">Findings — open</span>
                    <span class="lp-mono text-[11px] text-[var(--lp-faint)]">rev 4f2a9c1 · 2h ago</span>
                  </div>
                  <div class="space-y-2">
                    <div class="flex items-center gap-3 rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] px-3.5 py-2.5">
                      <span class="lp-mono rounded-md bg-[#e4573d]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#e4573d]">BUG</span>
                      <span class="truncate text-[13px] text-[var(--lp-ink)]">Race in webhook retry queue drops deliveries</span>
                    </div>
                    <div class="flex items-center gap-3 rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] px-3.5 py-2.5">
                      <span class="lp-mono rounded-md bg-[#d99000]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#b97d05]">RISK</span>
                      <span class="truncate text-[13px] text-[var(--lp-ink)]">Token cache has no eviction bound</span>
                    </div>
                    <div class="flex items-center gap-3 rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] px-3.5 py-2.5">
                      <span class="lp-mono rounded-md bg-[var(--n-brand-soft)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--n-brand)]">DOCS</span>
                      <span class="truncate text-[13px] text-[var(--lp-ink)]">Auth flow doc stale since v2.3 refactor</span>
                    </div>
                    <div class="flex items-center gap-3 rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] px-3.5 py-2.5 opacity-60">
                      <span class="lp-mono rounded-md bg-[#3d9a50]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#3d9a50]">FIXED</span>
                      <span class="truncate text-[13px] text-[var(--lp-faint)] line-through">Missing tests for org invitations</span>
                    </div>
                  </div>
                </div>
                <div class="hidden border-l border-[var(--lp-line)] p-5 lg:block">
                  <div class="mb-3 text-[13px] font-semibold text-[var(--lp-ink)]">PR #142 — draft</div>
                  <div class="space-y-2.5">
                    <div class="flex items-center gap-2 text-[13px] text-[var(--lp-muted)]">
                      <Check class="h-3.5 w-3.5 text-[#3d9a50]" /> Implement run
                    </div>
                    <div class="flex items-center gap-2 text-[13px] text-[var(--lp-muted)]">
                      <Check class="h-3.5 w-3.5 text-[#3d9a50]" /> Review verdict
                    </div>
                    <div class="flex items-center gap-2 text-[13px] text-[var(--lp-muted)]">
                      <Check class="h-3.5 w-3.5 text-[#3d9a50]" /> Fix round 1
                    </div>
                    <div class="lp-mono mt-4 inline-flex items-center gap-1.5 rounded-full bg-[#3d9a50]/10 px-2.5 py-1 text-[11px] font-semibold text-[#3d9a50]">
                      <Check class="h-3 w-3" /> opensweep/converged
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ── Works-with marquee ──────────────────────────────────────────── -->
      <section class="border-y border-[var(--lp-line)] py-7">
        <div class="lp-marquee-mask overflow-hidden">
          <div class="lp-marquee flex w-max items-center">
            <div v-for="n in 2" :key="n" class="flex items-center" :aria-hidden="n === 2">
              <template v-for="item in marqueeItems" :key="item">
                <span class="whitespace-nowrap px-6 text-[15px] font-semibold text-[var(--lp-muted)]">{{ item }}</span>
                <span class="lp-mono text-sm text-[var(--lp-faint)]">*</span>
              </template>
            </div>
          </div>
        </div>
      </section>

      <!-- ── How it works: stacked numbered accordion ───────────────────── -->
      <section id="how-it-works" class="scroll-mt-24 px-5 py-28">
        <div class="mx-auto max-w-[1200px]">
          <div class="max-w-[720px]">
            <div v-for="(step, i) in steps" :key="step.title" class="border-b border-[var(--lp-line)] last:border-b-0">
              <button
                type="button"
                class="flex w-full items-baseline gap-3 py-5 text-left transition-colors duration-300"
                :class="activeStep === i ? 'text-[var(--lp-ink)]' : 'text-[var(--lp-faint)] hover:text-[var(--lp-muted)]'"
                :aria-expanded="activeStep === i"
                @click="activeStep = i"
              >
                <span class="lp-display flex-1 text-[26px] leading-tight sm:text-[34px]">{{ step.title }}</span>
                <sup class="lp-mono shrink-0 text-xs" :class="activeStep === i ? 'text-[var(--n-brand)]' : ''">
                  0{{ i + 1 }}
                </sup>
              </button>
              <div
                class="grid transition-[grid-template-rows] duration-300 ease-out"
                :class="activeStep === i ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
              >
                <div class="overflow-hidden">
                  <p class="max-w-[52ch] pb-6 text-[15px] leading-relaxed text-[var(--lp-muted)]">{{ step.body }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ── Flagship features: list + product panel ────────────────────── -->
      <section id="features" class="scroll-mt-24 border-t border-[var(--lp-line)] bg-[var(--lp-panel)] px-5 py-28">
        <div class="mx-auto max-w-[1200px]">
          <h2 class="lp-display text-[34px] leading-[1.08] sm:text-[44px]">
            One dashboard.<br />
            <span class="text-[var(--lp-faint)]">Your whole dev workflow.</span>
          </h2>

          <div class="mt-14 grid gap-10 lg:grid-cols-[360px_1fr] lg:gap-16">
            <div>
              <div v-for="(feature, i) in features" :key="feature.name" class="border-b border-[var(--lp-line)] last:border-b-0">
                <button
                  type="button"
                  class="flex w-full items-baseline justify-between gap-3 py-4 text-left transition-colors duration-200"
                  :class="activeFeature === i ? 'text-[var(--lp-ink)]' : 'text-[var(--lp-faint)] hover:text-[var(--lp-muted)]'"
                  :aria-pressed="activeFeature === i"
                  @click="selectFeature(i)"
                >
                  <span class="text-[19px] font-semibold tracking-tight">{{ feature.name }}</span>
                  <sup class="lp-mono text-xs" :class="activeFeature === i ? 'text-[var(--n-brand)]' : ''">0{{ i + 1 }}</sup>
                </button>
                <div v-if="activeFeature === i">
                  <div class="h-[2px] w-full overflow-hidden rounded bg-[var(--lp-line)]">
                    <div
                      :key="activeFeature"
                      class="lp-progress h-full bg-[var(--n-brand)]"
                      :style="{ animationDuration: `${FEATURE_INTERVAL}ms` }"
                    />
                  </div>
                  <p class="pb-5 pt-4 text-sm leading-relaxed text-[var(--lp-muted)]">{{ feature.body }}</p>
                </div>
              </div>
            </div>

            <!-- Feature panel -->
            <div class="min-h-[440px] rounded-2xl border border-[var(--lp-line)] bg-[var(--lp-card)] p-6 sm:p-8">
              <!-- 01 Living documentation -->
              <div v-if="activeFeature === 0" class="grid gap-6 sm:grid-cols-[220px_1fr]">
                <div>
                  <p class="lp-mono mb-3 text-[11px] uppercase tracking-wider text-[var(--lp-faint)]">docs / acme-api</p>
                  <div class="space-y-1">
                    <div v-for="doc in ['architecture', 'auth', 'billing', 'webhooks', 'deployment']" :key="doc"
                      class="lp-mono flex items-center justify-between rounded-lg px-3 py-2 text-[13px]"
                      :class="doc === 'auth' ? 'bg-[var(--lp-panel)] text-[var(--lp-ink)]' : 'text-[var(--lp-muted)]'">
                      {{ doc }}
                      <span v-if="doc === 'auth'" class="rounded-md bg-[#d99000]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#b97d05]">updating</span>
                      <span v-else class="text-[10px] text-[#3d9a50]">fresh</span>
                    </div>
                  </div>
                </div>
                <div class="rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] p-5">
                  <p class="text-[15px] font-semibold text-[var(--lp-ink)]">Authentication flow</p>
                  <p class="lp-mono mt-1 text-[11px] text-[var(--lp-faint)]">watch: back_end/auth/** · checked at 4f2a9c1</p>
                  <div class="mt-4 space-y-2">
                    <div class="h-2 w-full rounded bg-[var(--lp-line)]" />
                    <div class="h-2 w-[86%] rounded bg-[var(--lp-line)]" />
                    <div class="h-2 w-[72%] rounded bg-[var(--lp-line)]" />
                    <div class="h-2 w-[64%] rounded bg-[var(--lp-line)]" />
                  </div>
                  <div class="lp-mono mt-5 inline-flex items-center gap-1.5 rounded-full border border-[var(--lp-line)] px-2.5 py-1 text-[11px] text-[var(--lp-muted)]">
                    <ArrowRight class="h-3 w-3" /> export AGENTS.md — PR #87 opened
                  </div>
                </div>
              </div>

              <!-- 02 Autonomous investigations -->
              <div v-else-if="activeFeature === 1" class="space-y-3">
                <p class="lp-mono mb-4 text-[11px] uppercase tracking-wider text-[var(--lp-faint)]">scheduled investigations</p>
                <div class="rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] p-4">
                  <div class="flex items-center justify-between">
                    <span class="text-[14px] font-semibold text-[var(--lp-ink)]">Nightly security sweep</span>
                    <span class="lp-mono rounded-md bg-[#3d9a50]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#3d9a50]">completed</span>
                  </div>
                  <p class="lp-mono mt-2 text-[11px] text-[var(--lp-faint)]">checked 214 files · rev 4f2a9c1 · 3 findings filed</p>
                </div>
                <div class="rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] p-4">
                  <div class="flex items-center justify-between">
                    <span class="text-[14px] font-semibold text-[var(--lp-ink)]">Dependency audit</span>
                    <span class="lp-mono inline-flex items-center gap-1.5 rounded-md bg-[var(--n-brand-soft)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--n-brand)]">
                      <span class="lp-pulse h-1.5 w-1.5 rounded-full bg-[var(--n-brand)]" /> running
                    </span>
                  </div>
                  <p class="lp-mono mt-2 text-[11px] text-[var(--lp-faint)]">asking: which pinned versions have known CVEs?</p>
                </div>
                <div class="rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] p-4 opacity-70">
                  <div class="flex items-center justify-between">
                    <span class="text-[14px] font-semibold text-[var(--lp-ink)]">Dead code sweep</span>
                    <span class="lp-mono rounded-md bg-[var(--lp-panel)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--lp-muted)]">queued</span>
                  </div>
                  <p class="lp-mono mt-2 text-[11px] text-[var(--lp-faint)]">every Sunday · 02:00 UTC</p>
                </div>
              </div>

              <!-- 03 Findings inbox -->
              <div v-else-if="activeFeature === 2" class="space-y-3">
                <p class="lp-mono mb-4 text-[11px] uppercase tracking-wider text-[var(--lp-faint)]">findings — triaged, with evidence</p>
                <div class="rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] p-4">
                  <div class="flex items-center gap-3">
                    <span class="lp-mono rounded-md bg-[#e4573d]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#e4573d]">BUG</span>
                    <span class="flex-1 text-[14px] font-medium text-[var(--lp-ink)]">Race in webhook retry queue drops deliveries</span>
                    <span class="lp-btn lp-btn-outline !px-3 !py-1 !text-[11px]">Promote to ticket</span>
                  </div>
                  <p class="lp-mono mt-2.5 text-[11px] text-[var(--lp-faint)]">evidence: back_end/webhooks/retry.py:142 · reproduced in sandbox</p>
                </div>
                <div class="rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] p-4">
                  <div class="flex items-center gap-3">
                    <span class="lp-mono rounded-md bg-[#d99000]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#b97d05]">RISK</span>
                    <span class="flex-1 text-[14px] font-medium text-[var(--lp-ink)]">Token cache has no eviction bound</span>
                  </div>
                  <p class="lp-mono mt-2.5 text-[11px] text-[var(--lp-faint)]">evidence: memory growth ~4MB/day at current traffic</p>
                </div>
                <div class="rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] p-4">
                  <div class="flex items-center gap-3">
                    <span class="lp-mono rounded-md bg-[var(--n-brand-soft)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--n-brand)]">TEST</span>
                    <span class="flex-1 text-[14px] font-medium text-[var(--lp-ink)]">Org invitation expiry path is untested</span>
                  </div>
                  <p class="lp-mono mt-2.5 text-[11px] text-[var(--lp-faint)]">evidence: 0 tests reference OrgInvitation.expires_at</p>
                </div>
              </div>

              <!-- 04 Tickets that ship -->
              <div v-else-if="activeFeature === 3">
                <p class="lp-mono mb-4 text-[11px] uppercase tracking-wider text-[var(--lp-faint)]">approved ticket → draft PR</p>
                <div class="rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] p-5">
                  <div class="flex items-center justify-between gap-3">
                    <span class="text-[15px] font-semibold text-[var(--lp-ink)]">fix: bound token cache eviction</span>
                    <span class="lp-mono text-[11px] text-[var(--lp-faint)]">PR #142</span>
                  </div>
                  <div class="mt-5 space-y-2.5">
                    <div class="flex items-center gap-2 text-[13px] text-[var(--lp-muted)]">
                      <Check class="h-3.5 w-3.5 text-[#3d9a50]" /> Implement run — draft PR opened
                    </div>
                    <div class="flex items-center gap-2 text-[13px] text-[var(--lp-muted)]">
                      <Check class="h-3.5 w-3.5 text-[#3d9a50]" /> Review verdict — 2 issues found
                    </div>
                    <div class="flex items-center gap-2 text-[13px] text-[var(--lp-muted)]">
                      <Check class="h-3.5 w-3.5 text-[#3d9a50]" /> Fix round 1 — issues resolved
                    </div>
                    <div class="flex items-center gap-2 text-[13px] text-[var(--lp-muted)]">
                      <Check class="h-3.5 w-3.5 text-[#3d9a50]" /> Review verdict — clean
                    </div>
                  </div>
                  <div class="mt-6 flex items-center justify-between border-t border-[var(--lp-line)] pt-4">
                    <span class="lp-mono inline-flex items-center gap-1.5 rounded-full bg-[#3d9a50]/10 px-2.5 py-1 text-[11px] font-semibold text-[#3d9a50]">
                      <Check class="h-3 w-3" /> opensweep/converged
                    </span>
                    <span class="lp-btn lp-btn-primary !px-4 !py-1.5 !text-[12px]">Merge</span>
                  </div>
                </div>
              </div>

              <!-- 05 Any model, any agent -->
              <div v-else class="space-y-3">
                <p class="lp-mono mb-4 text-[11px] uppercase tracking-wider text-[var(--lp-faint)]">llm providers</p>
                <div
                  v-for="provider in [
                    { name: 'Claude Code', kind: 'CLI agent', cost: 'subscription' },
                    { name: 'Anthropic API', kind: 'API', cost: 'metered' },
                    { name: 'Codex · opencode', kind: 'CLI agents', cost: 'subscription' },
                    { name: 'opencode → MLX (local)', kind: 'local model', cost: '$0.00 / run' },
                  ]"
                  :key="provider.name"
                  class="flex items-center justify-between rounded-xl border border-[var(--lp-line)] bg-[var(--lp-bg)] px-4 py-3.5"
                >
                  <div class="flex items-center gap-3">
                    <span class="h-2 w-2 rounded-full bg-[var(--n-brand)]" />
                    <span class="text-[14px] font-medium text-[var(--lp-ink)]">{{ provider.name }}</span>
                    <span class="lp-mono text-[11px] text-[var(--lp-faint)]">{{ provider.kind }}</span>
                  </div>
                  <span
                    class="lp-mono text-[11px]"
                    :class="provider.cost.startsWith('$0') ? 'font-semibold text-[#3d9a50]' : 'text-[var(--lp-muted)]'"
                  >{{ provider.cost }}</span>
                </div>
                <p class="lp-mono pt-1 text-[11px] text-[var(--lp-faint)]">local models are never metered — the whole loop runs free</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ── Trust grid ──────────────────────────────────────────────────── -->
      <section class="border-t border-[var(--lp-line)] px-5 py-28">
        <div class="mx-auto max-w-[1200px]">
          <h2 class="lp-display max-w-[24ch] text-[34px] leading-[1.08] sm:text-[44px]">
            Sandboxed, evidence-stamped, and only ever a pull request
          </h2>

          <div class="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <article
              v-for="(card, i) in trustCards"
              :key="card.title"
              class="rounded-2xl border border-[var(--lp-line)] bg-[var(--lp-card)] p-6"
            >
              <div class="lp-mono flex h-24 items-center justify-center rounded-xl bg-[var(--lp-panel)] px-3 text-center text-[12px] text-[var(--lp-muted)]">
                <span v-if="i === 0">main ← draft PR #142</span>
                <span v-else-if="i === 1">clone → run → PR → destroy</span>
                <span v-else-if="i === 2" class="inline-flex items-center gap-1.5">
                  <Check class="h-3.5 w-3.5 text-[#3d9a50]" /> checked at 4f2a9c1 · 2h ago
                </span>
                <span v-else class="inline-flex items-center gap-1.5 font-semibold text-[#3d9a50]">
                  <Check class="h-3.5 w-3.5" /> opensweep/converged
                </span>
              </div>
              <h3 class="mt-5 text-[16px] font-semibold tracking-tight text-[var(--lp-ink)]">{{ card.title }}</h3>
              <p class="mt-2 text-sm leading-relaxed text-[var(--lp-muted)]">{{ card.body }}</p>
            </article>
          </div>
        </div>
      </section>

      <!-- ── Open source ─────────────────────────────────────────────────── -->
      <section id="open-source" class="scroll-mt-24 border-t border-[var(--lp-line)] bg-[var(--lp-panel)] px-5 py-28">
        <div class="mx-auto grid max-w-[1200px] items-center gap-12 lg:grid-cols-2 lg:gap-20">
          <div>
            <h2 class="lp-display text-[34px] leading-[1.08] sm:text-[44px]">
              Free forever.<br /><span class="text-[var(--lp-faint)]">Yours forever.</span>
            </h2>
            <p class="mt-6 max-w-[46ch] text-[15px] leading-relaxed text-[var(--lp-muted)]">
              OpenSweep is source-available and runs anywhere — a VPS, your homelab, your laptop.
              Bring your own LLM subscription or a local model, and the whole platform
              costs exactly nothing.
            </p>
            <ul class="mt-8 space-y-3.5">
              <li v-for="point in openSourcePoints" :key="point" class="flex items-start gap-3 text-[15px] text-[var(--lp-ink)]">
                <Check class="mt-1 h-4 w-4 shrink-0 text-[#3d9a50]" />
                {{ point }}
              </li>
            </ul>
            <a :href="GITHUB_URL" target="_blank" rel="noopener" class="lp-btn lp-btn-outline lp-btn-lg mt-10">
              <Github class="h-4 w-4" />
              View on GitHub
            </a>
          </div>

          <div class="overflow-hidden rounded-2xl border border-[var(--lp-line)] bg-[var(--lp-card)]">
            <div class="flex items-center gap-2 border-b border-[var(--lp-line)] px-5 py-3">
              <span class="h-2.5 w-2.5 rounded-full bg-[var(--lp-line-strong)]" />
              <span class="h-2.5 w-2.5 rounded-full bg-[var(--lp-line-strong)]" />
              <span class="h-2.5 w-2.5 rounded-full bg-[var(--lp-line-strong)]" />
              <span class="lp-mono ml-2 text-[11px] text-[var(--lp-faint)]">terminal</span>
            </div>
            <pre class="lp-mono overflow-x-auto p-6 text-[13px] leading-relaxed text-[var(--lp-muted)]"><code><span class="text-[var(--lp-faint)]">$</span> git clone {{ GITHUB_URL }}.git
<span class="text-[var(--lp-faint)]">$</span> cd opensweep && ./start.sh

<span class="text-[#3d9a50]">✓</span> opensweep ready — open http://localhost:5174</code></pre>
          </div>
        </div>
      </section>

      <!-- ── Editions: open source now, cloud coming soon ────────────────── -->
      <section id="cloud" class="scroll-mt-24 border-t border-[var(--lp-line)] px-5 py-28">
        <div class="mx-auto max-w-[1200px]">
          <h2 class="lp-display text-[34px] leading-[1.08] sm:text-[44px]">
            Self-host it today.<br /><span class="text-[var(--lp-faint)]">Cloud is on the way.</span>
          </h2>

          <div class="mt-14 grid max-w-[900px] gap-4 lg:grid-cols-2">
            <div class="flex flex-col rounded-2xl border border-[var(--lp-ink)] bg-[var(--lp-card)] p-8">
              <div class="flex items-baseline justify-between">
                <h3 class="text-lg font-semibold tracking-tight text-[var(--lp-ink)]">Self-Hosted</h3>
                <span class="lp-mono rounded-full bg-[var(--lp-panel)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--lp-ink)]">
                  available now
                </span>
              </div>
              <p class="mt-1 text-sm text-[var(--lp-muted)]">Self-hosted or local. No gates, no limits.</p>
              <p class="mt-7">
                <span class="lp-display text-[52px]">$0</span>
                <span class="lp-mono ml-2 text-xs text-[var(--lp-faint)]">free forever</span>
              </p>
              <ul class="mt-8 flex-1 space-y-3">
                <li v-for="item in freePlan" :key="item" class="flex items-start gap-3 text-sm text-[var(--lp-ink)]">
                  <Check class="mt-0.5 h-4 w-4 shrink-0 text-[#3d9a50]" />
                  {{ item }}
                </li>
              </ul>
              <a :href="GITHUB_URL" target="_blank" rel="noopener" class="lp-btn lp-btn-outline mt-9 justify-center">
                <Github class="h-4 w-4" />
                Deploy from GitHub
              </a>
            </div>

            <div class="relative flex flex-col rounded-2xl border border-[var(--lp-line)] bg-[var(--lp-card)] p-8">
              <div class="flex items-baseline justify-between">
                <h3 class="text-lg font-semibold tracking-tight text-[var(--lp-ink)]">Cloud</h3>
                <span class="lp-mono rounded-full bg-[var(--lp-panel)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--lp-ink)]">
                  coming soon
                </span>
              </div>
              <p class="mt-1 text-sm text-[var(--lp-muted)]">Hosted and managed. Zero ops for your team.</p>
              <p class="mt-7">
                <span class="lp-display text-[52px]">Soon</span>
                <span class="lp-mono ml-2 text-xs text-[var(--lp-faint)]">pricing to be announced</span>
              </p>
              <ul class="mt-8 flex-1 space-y-3">
                <li v-for="item in cloudPlan" :key="item" class="flex items-start gap-3 text-sm text-[var(--lp-ink)]">
                  <Check class="mt-0.5 h-4 w-4 shrink-0 text-[#3d9a50]" />
                  {{ item }}
                </li>
              </ul>
              <p class="lp-mono mt-9 text-center text-[11px] text-[var(--lp-faint)]">
                we’re building it — self-host today and your workflow carries over
              </p>
            </div>
          </div>
        </div>
      </section>

      <!-- ── FAQ ─────────────────────────────────────────────────────────── -->
      <section id="faq" class="scroll-mt-24 border-t border-[var(--lp-line)] px-5 py-28">
        <div class="mx-auto grid max-w-[1200px] gap-10 lg:grid-cols-[380px_1fr]">
          <h2 class="lp-display text-[34px] leading-[1.08] sm:text-[44px]">
            Questions,<br /><span class="text-[var(--lp-faint)]">answered.</span>
          </h2>

          <div>
            <details v-for="faq in faqs" :key="faq.q" class="lp-faq group border-b border-[var(--lp-line)]">
              <summary class="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[16px] font-semibold tracking-tight text-[var(--lp-ink)]">
                {{ faq.q }}
                <Plus class="h-4 w-4 shrink-0 text-[var(--lp-faint)] transition-transform duration-200 group-open:rotate-45" />
              </summary>
              <p class="max-w-[64ch] pb-6 text-[15px] leading-relaxed text-[var(--lp-muted)]">{{ faq.a }}</p>
            </details>
          </div>
        </div>
      </section>

      <!-- ── Final CTA ───────────────────────────────────────────────────── -->
      <section class="px-5 pb-28">
        <div class="mx-auto max-w-[1200px] rounded-3xl bg-[var(--lp-ink)] px-8 py-20 text-center sm:px-16">
          <h2 class="lp-display mx-auto max-w-[18ch] text-[34px] leading-[1.08] text-[var(--lp-bg)] sm:text-[48px]">
            Stop maintaining. Start merging.
          </h2>
          <p class="mx-auto mt-5 max-w-[44ch] text-[15px] leading-relaxed text-[var(--lp-bg)] opacity-70">
            Connect your GitHub and the predefined agents file their first
            findings today — free, on your own hardware.
          </p>
          <div class="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <button type="button" class="lp-btn lp-btn-inverse lp-btn-lg" @click="getStarted">
              Create your account
              <ArrowRight class="h-4 w-4" />
            </button>
            <a :href="GITHUB_URL" target="_blank" rel="noopener" class="lp-btn lp-btn-ghost lp-btn-lg">
              <Github class="h-4 w-4" />
              Star on GitHub
            </a>
          </div>
        </div>
      </section>
    </main>

    <!-- ── Footer ──────────────────────────────────────────────────────── -->
    <footer class="relative overflow-hidden border-t border-[var(--lp-line)] px-5 pb-40 pt-16">
      <div class="relative z-10 mx-auto grid max-w-[1200px] gap-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div class="flex items-center gap-2.5">
            <SweepMark class="h-6 w-6 text-[var(--lp-ink)]" aria-hidden="true" />
            <span class="lp-display text-base">OpenSweep</span>
          </div>
          <p class="mt-4 max-w-xs text-sm leading-relaxed text-[var(--lp-faint)]">
            The source-available dashboard for working with coding agents.
            Free self-hosted — Cloud coming soon.
          </p>
          <p class="lp-mono mt-4 text-[11px] text-[var(--lp-faint)]">
            © {{ new Date().getFullYear() }} OpenSweep. Built in the open.
          </p>
        </div>

        <nav aria-label="Product">
          <p class="lp-mono text-[11px] uppercase tracking-widest text-[var(--lp-faint)]">Product</p>
          <ul class="mt-4 space-y-2.5 text-sm">
            <li><a href="#features" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]">Features</a></li>
            <li><a href="#how-it-works" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]">How it works</a></li>
            <li><a href="#cloud" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]">Cloud</a></li>
            <li><a href="#faq" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]">FAQ</a></li>
          </ul>
        </nav>

        <nav aria-label="Self-hosted">
          <p class="lp-mono text-[11px] uppercase tracking-widest text-[var(--lp-faint)]">Self-hosted</p>
          <ul class="mt-4 space-y-2.5 text-sm">
            <li><a :href="GITHUB_URL" target="_blank" rel="noopener" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]">GitHub</a></li>
            <li><a :href="`${GITHUB_URL}#run-locally-with-docker`" target="_blank" rel="noopener" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]">Self-hosting guide</a></li>
            <li><a :href="`${GITHUB_URL}/issues`" target="_blank" rel="noopener" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]">Issues &amp; support</a></li>
          </ul>
        </nav>

        <nav aria-label="Account">
          <p class="lp-mono text-[11px] uppercase tracking-widest text-[var(--lp-faint)]">Account</p>
          <ul class="mt-4 space-y-2.5 text-sm">
            <li>
              <button type="button" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]" @click="logIn">Log in</button>
            </li>
            <li>
              <button type="button" class="text-[var(--lp-muted)] transition-colors duration-200 hover:text-[var(--lp-ink)]" @click="getStarted">Create account</button>
            </li>
          </ul>
        </nav>
      </div>

      <div class="lp-watermark" aria-hidden="true">OpenSweep</div>
    </footer>
  </div>
</template>

<style lang="scss">
/* Not scoped: everything is namespaced under .landing / lp-* so it cannot
   leak into the app, and theming can key off the html[data-theme] attr. */

.landing {
  --lp-bg: #fdfdfb;
  --lp-panel: #f6f5f1;
  --lp-card: #ffffff;
  --lp-ink: #21201c;
  --lp-muted: #6d6a62;
  --lp-faint: #9d9a90;
  --lp-line: rgba(33, 32, 28, 0.1);
  --lp-line-strong: rgba(33, 32, 28, 0.22);
  --lp-btn-bg: #21201c;
  --lp-btn-fg: #fdfdfb;

  font-family: 'Mona Sans', 'Manrope', ui-sans-serif, system-ui, sans-serif;
  background: var(--lp-bg);
  color: var(--lp-ink);
  font-feature-settings: 'ss01' on;
}

[data-theme='dark'] .landing {
  --lp-bg: #131211;
  --lp-panel: #1a1917;
  --lp-card: #191816;
  --lp-ink: #f2f1ec;
  --lp-muted: #a5a29a;
  --lp-faint: #767369;
  --lp-line: rgba(242, 241, 236, 0.09);
  --lp-line-strong: rgba(242, 241, 236, 0.2);
  --lp-btn-bg: #f2f1ec;
  --lp-btn-fg: #161514;
}

.landing .lp-display {
  font-weight: 560;
  letter-spacing: -0.03em;
}

.landing .lp-mono {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}

.landing .lp-header-glass {
  background: color-mix(in srgb, var(--lp-bg) 82%, transparent);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--lp-line);
}

/* Buttons */
.landing .lp-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border-radius: 9999px;
  padding: 0.55rem 1.15rem;
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  transition: opacity 0.2s, background-color 0.2s, border-color 0.2s, transform 0.2s;
  cursor: pointer;
}

.landing .lp-btn-lg {
  padding: 0.75rem 1.5rem;
  font-size: 0.9375rem;
}

.landing .lp-btn-primary {
  background: var(--lp-btn-bg);
  color: var(--lp-btn-fg);

  &:hover {
    opacity: 0.86;
  }
}

.landing .lp-btn-outline {
  border: 1px solid var(--lp-line-strong);
  color: var(--lp-ink);
  background: transparent;

  &:hover {
    background: var(--lp-panel);
  }
}

/* On the inverted CTA band */
.landing .lp-btn-inverse {
  background: var(--lp-bg);
  color: var(--lp-ink);

  &:hover {
    opacity: 0.88;
  }
}

.landing .lp-btn-ghost {
  border: 1px solid color-mix(in srgb, var(--lp-bg) 30%, transparent);
  color: var(--lp-bg);

  &:hover {
    background: color-mix(in srgb, var(--lp-bg) 10%, transparent);
  }
}

/* Hero spiral: centered, fading softly at the edges and toward the
   product panel at the bottom so the text stays readable */
.landing .lp-spiral {
  mask-image: radial-gradient(60% 52% at 66% 30%, black 45%, transparent 80%);
  -webkit-mask-image: radial-gradient(60% 52% at 66% 30%, black 45%, transparent 80%);
}

/* Marquee */
.landing .lp-marquee {
  animation: lp-marquee 36s linear infinite;
}

.landing .lp-marquee-mask {
  mask-image: linear-gradient(to right, transparent, black 8%, black 92%, transparent);
  -webkit-mask-image: linear-gradient(to right, transparent, black 8%, black 92%, transparent);
}

@keyframes lp-marquee {
  to {
    transform: translateX(-50%);
  }
}

/* Feature auto-advance progress */
.landing .lp-progress {
  width: 0;
  animation: lp-fill linear forwards;
}

@keyframes lp-fill {
  to {
    width: 100%;
  }
}

.landing .lp-pulse {
  animation: lp-pulse 1.4s ease-in-out infinite;
}

@keyframes lp-pulse {
  50% {
    opacity: 0.3;
  }
}

.landing .lp-faq summary::-webkit-details-marker {
  display: none;
}

/* Giant footer watermark */
.landing .lp-watermark {
  position: absolute;
  bottom: -0.32em;
  left: 50%;
  transform: translateX(-50%);
  font-weight: 650;
  letter-spacing: -0.05em;
  font-size: clamp(80px, 12.5vw, 190px);
  line-height: 1;
  color: var(--lp-ink);
  opacity: 0.045;
  user-select: none;
  pointer-events: none;
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .landing .lp-marquee {
    animation: none;
  }

  .landing .lp-progress {
    animation: none;
    width: 100%;
  }
}
</style>
