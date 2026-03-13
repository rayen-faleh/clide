<script setup lang="ts">
import { computed } from 'vue'
import type { AgentState } from '@/types/messages'

const props = defineProps<{
  state: AgentState
}>()

const stateConfig: Record<AgentState, { color: string; pulse: string }> = {
  sleeping: { color: '#6b7280', pulse: 'none' },
  idle: { color: '#22c55e', pulse: 'pulse-slow' },
  thinking: { color: '#3b82f6', pulse: 'pulse-medium' },
  conversing: { color: '#eab308', pulse: 'pulse-fast' },
  working: { color: '#f97316', pulse: 'pulse-fast' },
}

const config = computed(() => stateConfig[props.state] ?? stateConfig.idle)
</script>

<template>
  <div class="state-indicator">
    <div
      class="state-dot"
      :class="config.pulse"
      :style="{ backgroundColor: config.color, boxShadow: `0 0 8px ${config.color}80` }"
    ></div>
    <span class="state-name">{{ state }}</span>
  </div>
</template>

<style scoped>
.state-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.state-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.state-name {
  font-size: 13px;
  color: var(--color-text-secondary);
  text-transform: capitalize;
}

.pulse-slow {
  animation: pulse 3s ease-in-out infinite;
}

.pulse-medium {
  animation: pulse 1.5s ease-in-out infinite;
}

.pulse-fast {
  animation: pulse 0.8s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.3);
  }
}
</style>
