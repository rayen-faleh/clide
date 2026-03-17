<script setup lang="ts">
import type { RewardEntry } from '@/stores/agent'

defineProps<{ reward: RewardEntry }>()
</script>

<template>
  <div class="reward-message">
    <span class="reward-icon">&#127829;</span>
    <span class="reward-text">
      You gave <strong>{{ reward.amount }}</strong> pizza{{ reward.amount !== 1 ? 's' : '' }}: "{{
        reward.reason
      }}"
    </span>
  </div>
</template>

<style scoped>
.reward-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  margin: 4px 0;
  background: rgba(255, 152, 0, 0.08);
  border-left: 3px solid #ff9800;
  border-radius: 4px;
  font-size: 0.85rem;
  color: #ffb74d;
}
.reward-icon {
  font-size: 1.1rem;
}
.reward-text strong {
  color: #ffa726;
}
</style>
