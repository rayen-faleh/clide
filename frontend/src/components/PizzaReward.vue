<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{ rewarded: [] }>()

const showDialog = ref(false)
const amount = ref(1)
const reason = ref('')
const submitting = ref(false)

async function submitReward() {
  if (!reason.value.trim() || amount.value < 1) return
  submitting.value = true
  try {
    const res = await fetch('/api/rewards/give', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount: amount.value, reason: reason.value.trim() }),
    })
    if (res.ok) {
      emit('rewarded')
      showDialog.value = false
      reason.value = ''
      amount.value = 1
    }
  } catch (e) {
    console.error('Failed to give reward:', e)
  } finally {
    submitting.value = false
  }
}

function toggleDialog() {
  showDialog.value = !showDialog.value
}
</script>

<template>
  <div class="pizza-reward">
    <button class="pizza-btn" title="Give virtual pizzas" @click="toggleDialog">
      <span class="pizza-icon">&#127829;</span>
    </button>
    <div v-if="showDialog" class="reward-dialog">
      <div class="dialog-header">Give Pizzas</div>
      <label class="dialog-label">
        Amount
        <input v-model.number="amount" type="number" min="1" max="10" class="amount-input" />
      </label>
      <label class="dialog-label">
        Reason
        <input
          v-model="reason"
          type="text"
          placeholder="Why are you rewarding?"
          class="reason-input"
          @keyup.enter="submitReward"
        />
      </label>
      <button
        class="give-btn"
        :disabled="!reason.trim() || amount < 1 || submitting"
        @click="submitReward"
      >
        {{ submitting ? 'Giving...' : `Give ${amount}` }} &#127829;
      </button>
    </div>
  </div>
</template>

<style scoped>
.pizza-reward {
  position: relative;
}

.pizza-btn {
  background: none;
  border: 1px solid var(--color-border, #374151);
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 1.2rem;
  transition: background 0.2s;
}
.pizza-btn:hover {
  background: rgba(255, 152, 0, 0.15);
}

.pizza-icon {
  display: block;
  line-height: 1;
}

.reward-dialog {
  position: absolute;
  bottom: 100%;
  right: 0;
  margin-bottom: 8px;
  background: var(--color-bg-secondary, #1f2937);
  border: 1px solid var(--color-border, #374151);
  border-radius: 8px;
  padding: 12px;
  width: 240px;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.dialog-header {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--color-text-primary, #e5e7eb);
  margin-bottom: 8px;
}

.dialog-label {
  display: block;
  font-size: 0.75rem;
  color: var(--color-text-secondary, #9ca3af);
  margin-bottom: 6px;
}

.amount-input {
  width: 60px;
  background: var(--color-bg-primary, #111827);
  border: 1px solid var(--color-border, #374151);
  border-radius: 4px;
  color: var(--color-text-primary, #e5e7eb);
  padding: 4px 8px;
  margin-left: 8px;
  font-size: 0.85rem;
}

.reason-input {
  width: 100%;
  background: var(--color-bg-primary, #111827);
  border: 1px solid var(--color-border, #374151);
  border-radius: 4px;
  color: var(--color-text-primary, #e5e7eb);
  padding: 6px 8px;
  margin-top: 4px;
  font-size: 0.85rem;
}

.give-btn {
  width: 100%;
  margin-top: 8px;
  background: rgba(255, 152, 0, 0.2);
  border: 1px solid #ff9800;
  border-radius: 6px;
  color: #ffb74d;
  padding: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: background 0.2s;
}
.give-btn:hover:not(:disabled) {
  background: rgba(255, 152, 0, 0.35);
}
.give-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
