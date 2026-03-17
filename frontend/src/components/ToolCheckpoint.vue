<script setup lang="ts">
import { ref } from 'vue'
import type { CheckpointEntry } from '@/stores/agent'

defineProps<{ checkpoint: CheckpointEntry }>()
const expanded = ref(false)
</script>

<template>
  <div class="checkpoint-card" @click="expanded = !expanded">
    <div class="checkpoint-header">
      <span class="checkpoint-icon">&#10227;</span>
      <span class="checkpoint-label">Phase {{ checkpoint.phase }} checkpoint</span>
      <span class="checkpoint-toggle">{{ expanded ? '\u25BC' : '\u25B6' }}</span>
    </div>
    <div v-if="expanded" class="checkpoint-content">
      {{ checkpoint.content }}
    </div>
  </div>
</template>

<style scoped>
.checkpoint-card {
  background: rgba(100, 181, 246, 0.08);
  border-left: 3px solid #64b5f6;
  border-radius: 4px;
  padding: 8px 12px;
  margin: 4px 0;
  cursor: pointer;
  font-size: 0.85rem;
  transition: background 0.2s;
}
.checkpoint-card:hover {
  background: rgba(100, 181, 246, 0.15);
}
.checkpoint-header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64b5f6;
  font-weight: 500;
}
.checkpoint-icon {
  font-size: 1rem;
}
.checkpoint-toggle {
  margin-left: auto;
  font-size: 0.7rem;
}
.checkpoint-content {
  margin-top: 8px;
  color: #ccc;
  line-height: 1.5;
  white-space: pre-wrap;
}
</style>
