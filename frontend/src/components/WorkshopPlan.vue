<script setup lang="ts">
import type { WorkshopPlan } from '@/stores/workshop'

defineProps<{
  plan: WorkshopPlan
  currentStep: number
}>()

function stepIcon(status: string): string {
  switch (status) {
    case 'completed':
      return '\u2705'
    case 'in_progress':
      return '\u25B6'
    case 'skipped':
      return '\u23ED'
    default:
      return '\u25A1'
  }
}
</script>

<template>
  <div class="plan-container">
    <div class="plan-header">
      <h3 class="plan-title">Plan</h3>
    </div>
    <div class="plan-objective"><strong>Objective:</strong> {{ plan.objective }}</div>
    <div class="plan-approach"><strong>Approach:</strong> {{ plan.approach }}</div>
    <div class="plan-steps">
      <div
        v-for="(step, index) in plan.steps"
        :key="step.id"
        class="plan-step"
        :class="{ active: index === currentStep && step.status === 'in_progress' }"
      >
        <span class="step-icon">{{ stepIcon(step.status) }}</span>
        <div class="step-content">
          <span class="step-desc">{{ index + 1 }}. {{ step.description }}</span>
          <span v-if="step.resultSummary" class="step-result">{{ step.resultSummary }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.plan-title {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text, #e5e7eb);
  margin: 0;
}
.plan-objective,
.plan-approach {
  font-size: 0.8rem;
  color: var(--color-text-secondary, #9ca3af);
  line-height: 1.4;
}
.plan-objective strong,
.plan-approach strong {
  color: var(--color-text, #e5e7eb);
}
.plan-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.plan-step {
  display: flex;
  gap: 8px;
  padding: 8px;
  border-radius: 6px;
  font-size: 0.8rem;
  color: var(--color-text-secondary, #9ca3af);
  transition: background 0.2s;
}
.plan-step.active {
  background: rgba(59, 130, 246, 0.1);
  color: var(--color-text, #e5e7eb);
}
.step-icon {
  font-size: 0.9rem;
  flex-shrink: 0;
}
.step-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.step-desc {
  line-height: 1.3;
}
.step-result {
  font-size: 0.7rem;
  color: var(--color-text-secondary, #6b7280);
  font-style: italic;
}
</style>
