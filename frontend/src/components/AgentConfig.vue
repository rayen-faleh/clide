<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

interface Config {
  agent: {
    name: string
    system_prompt: string
    llm: { provider: string; model: string; max_tokens: number }
    states: {
      thinking: { interval_seconds: number; max_consecutive_cycles: number }
      budget: { daily_token_limit: number; warning_threshold: number }
      [key: string]: unknown
    }
    character: {
      base_traits: {
        curiosity: number
        warmth: number
        humor: number
        assertiveness: number
        creativity: number
      }
    }
    persona?: {
      reinforcement_interval: number
      persona_summary: string
      summarize_history: boolean
      history_summarize_threshold: number
      history_summary_keep_recent: number
    }
    [key: string]: unknown
  }
}

const props = defineProps<{
  config: Config
}>()

const emit = defineEmits<{
  save: [config: Config]
}>()

const systemPrompt = ref(props.config.agent.system_prompt ?? '')

const traits = reactive({
  curiosity: props.config.agent.character.base_traits.curiosity,
  warmth: props.config.agent.character.base_traits.warmth,
  humor: props.config.agent.character.base_traits.humor,
  assertiveness: props.config.agent.character.base_traits.assertiveness,
  creativity: props.config.agent.character.base_traits.creativity,
})

const autonomy = reactive({
  interval_seconds: props.config.agent.states.thinking.interval_seconds,
  max_consecutive_cycles: props.config.agent.states.thinking.max_consecutive_cycles,
})

const budget = reactive({
  daily_token_limit: props.config.agent.states.budget.daily_token_limit,
  warning_threshold: props.config.agent.states.budget.warning_threshold,
})

const persona = reactive({
  reinforcement_interval: props.config.agent.persona?.reinforcement_interval ?? 8,
  persona_summary: props.config.agent.persona?.persona_summary ?? '',
  summarize_history: props.config.agent.persona?.summarize_history ?? true,
  history_summarize_threshold: props.config.agent.persona?.history_summarize_threshold ?? 40,
  history_summary_keep_recent: props.config.agent.persona?.history_summary_keep_recent ?? 10,
})

watch(
  () => props.config,
  (newConfig) => {
    systemPrompt.value = newConfig.agent.system_prompt ?? ''
    Object.assign(traits, newConfig.agent.character.base_traits)
    autonomy.interval_seconds = newConfig.agent.states.thinking.interval_seconds
    autonomy.max_consecutive_cycles = newConfig.agent.states.thinking.max_consecutive_cycles
    budget.daily_token_limit = newConfig.agent.states.budget.daily_token_limit
    budget.warning_threshold = newConfig.agent.states.budget.warning_threshold
    if (newConfig.agent.persona) {
      persona.reinforcement_interval = newConfig.agent.persona.reinforcement_interval
      persona.persona_summary = newConfig.agent.persona.persona_summary
      persona.summarize_history = newConfig.agent.persona.summarize_history
      persona.history_summarize_threshold = newConfig.agent.persona.history_summarize_threshold
      persona.history_summary_keep_recent = newConfig.agent.persona.history_summary_keep_recent
    }
  },
  { deep: true },
)

const traitLabels: Record<string, string> = {
  curiosity: 'Curiosity',
  warmth: 'Warmth',
  humor: 'Humor',
  assertiveness: 'Assertiveness',
  creativity: 'Creativity',
}

function handleSave() {
  const updated: Config = {
    agent: {
      ...props.config.agent,
      system_prompt: systemPrompt.value,
      character: {
        base_traits: { ...traits },
      },
      states: {
        ...props.config.agent.states,
        thinking: {
          interval_seconds: autonomy.interval_seconds,
          max_consecutive_cycles: autonomy.max_consecutive_cycles,
        },
        budget: {
          daily_token_limit: budget.daily_token_limit,
          warning_threshold: budget.warning_threshold,
        },
      },
      persona: { ...persona },
    },
  }
  emit('save', updated)
}
</script>

<template>
  <div class="agent-config">
    <section class="config-section">
      <h3 class="section-title">System Prompt</h3>
      <div class="field-row field-row--vertical">
        <label class="field-label">System Prompt</label>
        <textarea
          v-model="systemPrompt"
          rows="5"
          class="field-textarea"
          placeholder="Enter custom system prompt..."
        />
      </div>
    </section>

    <section class="config-section">
      <h3 class="section-title">Personality Traits</h3>
      <div class="trait-list">
        <div v-for="(label, key) in traitLabels" :key="key" class="trait-row">
          <label class="trait-label">{{ label }}</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            :value="traits[key as keyof typeof traits]"
            class="trait-slider"
            @input="
              (e) =>
                (traits[key as keyof typeof traits] = parseFloat(
                  (e.target as HTMLInputElement).value,
                ))
            "
          />
          <span class="trait-value">{{ traits[key as keyof typeof traits].toFixed(2) }}</span>
        </div>
      </div>
    </section>

    <section class="config-section">
      <h3 class="section-title">Autonomy Settings</h3>
      <div class="field-row">
        <label class="field-label">Thinking Interval (seconds)</label>
        <input v-model.number="autonomy.interval_seconds" type="number" class="field-input" />
      </div>
      <div class="field-row">
        <label class="field-label">Max Consecutive Cycles</label>
        <input v-model.number="autonomy.max_consecutive_cycles" type="number" class="field-input" />
      </div>
    </section>

    <section class="config-section">
      <h3 class="section-title">Budget</h3>
      <div class="field-row">
        <label class="field-label">Daily Token Limit</label>
        <input v-model.number="budget.daily_token_limit" type="number" class="field-input" />
      </div>
      <div class="field-row">
        <label class="field-label">Warning Threshold</label>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          :value="budget.warning_threshold"
          class="trait-slider"
          @input="
            (e) => (budget.warning_threshold = parseFloat((e.target as HTMLInputElement).value))
          "
        />
        <span class="trait-value">{{ budget.warning_threshold.toFixed(2) }}</span>
      </div>
    </section>

    <section class="config-section">
      <h3 class="section-title">Persona Stability</h3>
      <div class="field-row field-row--vertical">
        <label class="field-label">Persona Summary</label>
        <textarea
          v-model="persona.persona_summary"
          rows="3"
          class="field-textarea"
          placeholder="Leave empty for auto-generation from system prompt..."
        />
        <span class="field-hint"
          >A 2-3 sentence reminder of the character's voice, injected periodically to prevent
          drift.</span
        >
      </div>
      <div class="field-row">
        <label class="field-label">Reinforcement Interval</label>
        <input
          v-model.number="persona.reinforcement_interval"
          type="number"
          min="1"
          max="50"
          class="field-input"
        />
        <span class="field-hint">Inject persona reminder every N user messages</span>
      </div>
      <div class="field-row">
        <label class="field-label">History Summarization</label>
        <label class="toggle-label">
          <input v-model="persona.summarize_history" type="checkbox" />
          Summarize old messages instead of discarding
        </label>
      </div>
      <div class="field-row">
        <label class="field-label">Summarization Threshold</label>
        <input
          v-model.number="persona.history_summarize_threshold"
          type="number"
          min="10"
          max="100"
          class="field-input"
        />
        <span class="field-hint">Trigger summarization when history exceeds this count</span>
      </div>
      <div class="field-row">
        <label class="field-label">Keep Recent Messages</label>
        <input
          v-model.number="persona.history_summary_keep_recent"
          type="number"
          min="5"
          max="30"
          class="field-input"
        />
        <span class="field-hint">Keep this many recent messages unsummarized</span>
      </div>
    </section>

    <div class="config-actions">
      <button class="save-btn" @click="handleSave">Save Changes</button>
    </div>
  </div>
</template>

<style scoped>
.agent-config {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.config-section {
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.trait-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.trait-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.trait-label {
  width: 120px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.trait-slider {
  flex: 1;
  height: 4px;
  appearance: none;
  background: var(--color-border);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}

.trait-slider::-webkit-slider-thumb {
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-button);
  cursor: pointer;
}

.trait-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-button);
  cursor: pointer;
  border: none;
}

.trait-value {
  width: 40px;
  text-align: right;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--color-text);
}

.field-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.field-label {
  width: 200px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.field-input {
  flex: 1;
  max-width: 200px;
  padding: 6px 10px;
  background-color: var(--color-input-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text);
  font-size: 13px;
  outline: none;
}

.field-input:focus {
  border-color: var(--color-focus);
}

.field-row--vertical {
  flex-direction: column;
  align-items: stretch;
}

.field-textarea {
  width: 100%;
  padding: 8px 10px;
  background-color: var(--color-input-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text);
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  outline: none;
  resize: vertical;
}

.field-textarea:focus {
  border-color: var(--color-focus);
}

.config-actions {
  display: flex;
  justify-content: flex-end;
}

.save-btn {
  padding: 8px 20px;
  background-color: var(--color-button);
  color: var(--color-user-text);
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s;
}

.save-btn:hover {
  background-color: var(--color-button-hover);
}

.field-hint {
  font-size: 11px;
  color: var(--color-text-secondary, #6b7280);
  opacity: 0.7;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.toggle-label input[type='checkbox'] {
  accent-color: var(--color-button, #2563eb);
}
</style>
