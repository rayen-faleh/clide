// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentConfig from '@/components/AgentConfig.vue'

const defaultConfig = {
  agent: {
    name: 'Clide',
    llm: { provider: 'anthropic', model: 'claude-sonnet-4-20250514', max_tokens: 4096 },
    states: {
      thinking: { interval_seconds: 300, max_consecutive_cycles: 5 },
      budget: { daily_token_limit: 500000, warning_threshold: 0.8 },
    },
    character: {
      base_traits: {
        curiosity: 0.8,
        warmth: 0.7,
        humor: 0.5,
        assertiveness: 0.4,
        creativity: 0.7,
      },
    },
  },
}

describe('AgentConfig', () => {
  it('renders trait sliders', () => {
    const wrapper = mount(AgentConfig, {
      props: { config: defaultConfig },
    })

    expect(wrapper.text()).toContain('Curiosity')
    expect(wrapper.text()).toContain('Warmth')
    expect(wrapper.text()).toContain('Humor')
    expect(wrapper.text()).toContain('Assertiveness')
    expect(wrapper.text()).toContain('Creativity')

    const sliders = wrapper.findAll('input[type="range"]')
    expect(sliders.length).toBeGreaterThanOrEqual(5)
  })

  it('renders save button', () => {
    const wrapper = mount(AgentConfig, {
      props: { config: defaultConfig },
    })

    const saveBtn = wrapper.find('button.save-btn')
    expect(saveBtn.exists()).toBe(true)
    expect(saveBtn.text()).toContain('Save')
  })

  it('emits save on click', async () => {
    const wrapper = mount(AgentConfig, {
      props: { config: defaultConfig },
    })

    const saveBtn = wrapper.find('button.save-btn')
    await saveBtn.trigger('click')

    expect(wrapper.emitted('save')).toBeTruthy()
    expect(wrapper.emitted('save')!.length).toBe(1)
  })

  it('displays current trait values', () => {
    const wrapper = mount(AgentConfig, {
      props: { config: defaultConfig },
    })

    expect(wrapper.text()).toContain('0.8')
    expect(wrapper.text()).toContain('0.7')
    expect(wrapper.text()).toContain('0.5')
    expect(wrapper.text()).toContain('0.4')
  })

  it('displays autonomy settings', () => {
    const wrapper = mount(AgentConfig, {
      props: { config: defaultConfig },
    })

    expect(wrapper.text()).toContain('Thinking Interval')
    expect(wrapper.text()).toContain('Max Consecutive Cycles')
  })

  it('displays budget settings', () => {
    const wrapper = mount(AgentConfig, {
      props: { config: defaultConfig },
    })

    expect(wrapper.text()).toContain('Daily Token Limit')
    expect(wrapper.text()).toContain('Warning Threshold')
  })
})
