<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  mood: string
  intensity: number
}>()

const moodColors: Record<string, string> = {
  curious: '#3b82f6',
  excited: '#f97316',
  contemplative: '#a855f7',
  playful: '#ec4899',
  focused: '#06b6d4',
  content: '#22c55e',
  inspired: '#eab308',
  amused: '#f43e5e',
  neutral: '#6b7280',
  melancholy: '#6366f1',
  frustrated: '#ef4444',
  tired: '#78716c',
}

const color = computed(() => moodColors[props.mood] ?? '#6b7280')

const indicatorSize = computed(() => {
  const base = 32
  const extra = props.intensity * 16
  return `${base + extra}px`
})

const glowOpacity = computed(() => props.intensity * 0.6)
</script>

<template>
  <div class="mood-display">
    <div
      class="mood-indicator"
      :style="{
        width: indicatorSize,
        height: indicatorSize,
        backgroundColor: color,
        boxShadow: `0 0 ${intensity * 20}px ${color}${Math.round(glowOpacity * 255)
          .toString(16)
          .padStart(2, '0')}`,
      }"
    ></div>
    <span class="mood-name">{{ mood }}</span>
  </div>
</template>

<style scoped>
.mood-display {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mood-indicator {
  border-radius: 50%;
  transition:
    width 0.5s ease,
    height 0.5s ease,
    background-color 0.5s ease,
    box-shadow 0.5s ease;
}

.mood-name {
  font-size: 13px;
  color: var(--color-text-secondary);
  text-transform: capitalize;
}
</style>
