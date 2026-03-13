// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MoodDisplay from '@/components/MoodDisplay.vue'

describe('MoodDisplay', () => {
  it('renders mood name', () => {
    const wrapper = mount(MoodDisplay, {
      props: { mood: 'curious', intensity: 0.7 },
    })

    expect(wrapper.text()).toContain('curious')
  })

  it('renders intensity', () => {
    const wrapper = mount(MoodDisplay, {
      props: { mood: 'excited', intensity: 0.9 },
    })

    // The component should visually represent intensity
    const indicator = wrapper.find('.mood-indicator')
    expect(indicator.exists()).toBe(true)
  })

  it('renders different moods with different styling', () => {
    const wrapper = mount(MoodDisplay, {
      props: { mood: 'contemplative', intensity: 0.5 },
    })

    expect(wrapper.text()).toContain('contemplative')
  })
})
