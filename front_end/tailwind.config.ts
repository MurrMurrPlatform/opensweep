import type { Config } from 'tailwindcss'

export default {
  darkMode: ['variant', ['&:where([data-theme="dark"], [data-theme="dark"] *)', '&:where(.dark, .dark *)']],
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
  	extend: {
  		colors: {
  			bg: 'var(--n-bg)',
  			'bg-elevated': 'var(--n-bg-elevated)',
  			surface: 'var(--n-surface)',
  			'surface-2': 'var(--n-surface-2)',
  			'surface-3': 'var(--n-surface-3)',
  			'surface-muted': 'var(--n-surface-muted)',
  			'text-1': 'var(--n-text-1)',
  			'text-2': 'var(--n-text-2)',
  			'text-3': 'var(--n-text-3)',
  			'text-inverse': 'var(--n-text-inverse)',
  			divider: 'var(--n-divider)',
  			'border-soft': 'var(--n-border)',
  			'border-strong': 'var(--n-border-strong)',
  			brand: 'var(--n-brand)',
  			'brand-600': 'var(--n-brand-600)',
  			'brand-400': 'var(--n-brand-400)',
  			'brand-soft': 'var(--n-brand-soft)',
  			good: 'var(--n-good)',
  			warn: 'var(--n-warn)',
  			bad: 'var(--n-bad)',
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			sidebar: {
  				DEFAULT: 'hsl(var(--sidebar-background))',
  				foreground: 'hsl(var(--sidebar-foreground))',
  				primary: 'hsl(var(--sidebar-primary))',
  				'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
  				accent: 'hsl(var(--sidebar-accent))',
  				'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
  				border: 'hsl(var(--sidebar-border))',
  				ring: 'hsl(var(--sidebar-ring))'
  			}
  		},
  		borderRadius: {
  			xl: 'calc(var(--radius) + 4px)',
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)',
  			pill: 'var(--n-radius-pill)'
  		},
  		transitionTimingFunction: {
  			opensweep: 'cubic-bezier(.2,.7,.2,1)'
  		},
  		transitionDuration: {
  			fast: '180ms',
  			base: '280ms',
  			slow: '500ms'
  		},
  		spacing: {
  			sidebar: 'var(--n-sidebar-w)'
  		},
  		fontFamily: {
  			sans: [
  				'Manrope',
  				'ui-sans-serif',
  				'system-ui',
  				'-apple-system',
  				'Segoe UI',
  				'Roboto',
  				'sans-serif'
  			],
  			mono: [
  				'JetBrains Mono',
  				'ui-monospace',
  				'SFMono-Regular',
  				'Menlo',
  				'monospace'
  			],
  			display: [
  				'Bricolage Grotesque',
  				'Manrope',
  				'ui-sans-serif',
  				'system-ui',
  				'sans-serif'
  			]
  		},
  		boxShadow: {
  			panel: 'var(--n-panel-shadow)',
  			floating: 'var(--n-floating-shadow)',
  			glass: 'var(--n-glass-shadow)'
  		},
  		keyframes: {
  			'collapsible-down': {
  				from: { height: '0' },
  				to: { height: 'var(--reka-collapsible-content-height)' }
  			},
  			'collapsible-up': {
  				from: { height: 'var(--reka-collapsible-content-height)' },
  				to: { height: '0' }
  			},
  			'accordion-down': {
  				from: { height: '0' },
  				to: { height: 'var(--reka-accordion-content-height)' }
  			},
  			'accordion-up': {
  				from: { height: 'var(--reka-accordion-content-height)' },
  				to: { height: '0' }
  			},
  			'fade-in-up': {
  				from: { opacity: '0', transform: 'translateY(6px)' },
  				to: { opacity: '1', transform: 'translateY(0)' }
  			},
  			'scale-in': {
  				from: { opacity: '0', transform: 'scale(0.97)' },
  				to: { opacity: '1', transform: 'scale(1)' }
  			},
  			shimmer: {
  				from: { backgroundPosition: '200% 0' },
  				to: { backgroundPosition: '-200% 0' }
  			}
  		},
  		animation: {
  			'collapsible-down': 'collapsible-down 200ms cubic-bezier(.2,.7,.2,1)',
  			'collapsible-up': 'collapsible-up 200ms cubic-bezier(.2,.7,.2,1)',
  			'accordion-down': 'accordion-down 200ms cubic-bezier(.2,.7,.2,1)',
  			'accordion-up': 'accordion-up 200ms cubic-bezier(.2,.7,.2,1)',
  			'fade-in-up': 'fade-in-up 320ms cubic-bezier(.2,.7,.2,1) both',
  			'scale-in': 'scale-in 180ms cubic-bezier(.2,.7,.2,1) both',
  			shimmer: 'shimmer 1.8s linear infinite'
  		}
  	}
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config
