<script setup lang="ts">
/**
 * Assistant-bubble activity indicator: a shimmering label ("Thinking",
 * "Running Bash", …) followed by three softly fading dots. Falls back to a
 * steady pulse when the user prefers reduced motion.
 */
withDefaults(defineProps<{ label?: string }>(), { label: 'Thinking' })
</script>

<template>
  <div
    class="rounded-md rounded-bl-sm bg-muted border px-4 py-3"
    role="status"
    aria-label="Agent is working"
  >
    <span class="flex items-center gap-2">
      <span class="shimmer text-xs font-medium">{{ label }}</span>
      <span class="flex items-center gap-1" aria-hidden="true">
        <span class="dot" />
        <span class="dot" style="animation-delay: 0.2s" />
        <span class="dot" style="animation-delay: 0.4s" />
      </span>
    </span>
  </div>
</template>

<style scoped>
.shimmer {
  animation: shimmer-slide 2.2s linear infinite;
  background: linear-gradient(
    90deg,
    hsl(var(--muted-foreground)) 0%,
    hsl(var(--muted-foreground)) 38%,
    hsl(var(--foreground)) 50%,
    hsl(var(--muted-foreground)) 62%,
    hsl(var(--muted-foreground)) 100%
  );
  background-clip: text;
  -webkit-background-clip: text;
  background-size: 200% 100%;
  color: transparent;
}

@keyframes shimmer-slide {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.dot {
  animation: dot-fade 1.2s ease-in-out infinite;
  background: hsl(var(--muted-foreground));
  border-radius: 9999px;
  height: 3px;
  width: 3px;
}

@keyframes dot-fade {
  0%,
  100% {
    opacity: 0.25;
  }
  50% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .shimmer {
    animation: steady-pulse 2s ease-in-out infinite;
    background: none;
    color: hsl(var(--muted-foreground));
  }

  .dot {
    animation: none;
    opacity: 0.6;
  }

  @keyframes steady-pulse {
    0%,
    100% {
      opacity: 0.55;
    }
    50% {
      opacity: 1;
    }
  }
}
</style>
