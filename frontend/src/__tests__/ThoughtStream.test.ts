// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ThoughtStream from '@/components/ThoughtStream.vue'
import type { ThoughtEntry } from '@/stores/agent'

function createThought(overrides: Partial<ThoughtEntry> = {}): ThoughtEntry {
  return {
    content: 'A test thought',
    source: 'autonomous',
    timestamp: new Date().toISOString(),
    ...overrides,
  }
}

describe('ThoughtStream', () => {
  it('renders thoughts', () => {
    const thoughts = [
      createThought({ content: 'First thought' }),
      createThought({ content: 'Second thought' }),
    ]
    const wrapper = mount(ThoughtStream, {
      props: { thoughts },
    })

    expect(wrapper.text()).toContain('First thought')
    expect(wrapper.text()).toContain('Second thought')
  })

  it('renders empty state when no thoughts', () => {
    const wrapper = mount(ThoughtStream, {
      props: { thoughts: [] },
    })

    expect(wrapper.text()).toContain('No thoughts yet')
  })

  it('shows timestamps', () => {
    const timestamp = '2025-01-15T12:30:00.000Z'
    const thoughts = [createThought({ content: 'Timed thought', timestamp })]
    const wrapper = mount(ThoughtStream, {
      props: { thoughts },
    })

    // Should render some time representation
    expect(wrapper.find('.thought-time').exists()).toBe(true)
  })
})
