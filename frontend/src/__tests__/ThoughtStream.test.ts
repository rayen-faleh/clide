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

  it('renders tool badge when toolEvents present', () => {
    const thoughts = [
      createThought({
        content: 'Thought with tools',
        toolEvents: [
          {
            tool_name: 'search_files',
            arguments: { query: 'test' },
            call_id: 'call-1',
            result: 'found 3 files',
          },
        ],
      }),
    ]
    const wrapper = mount(ThoughtStream, {
      props: { thoughts },
    })

    expect(wrapper.find('.tool-badge').exists()).toBe(true)
  })

  it('tool badge shows correct count', () => {
    const thoughts = [
      createThought({
        content: 'Thought with multiple tools',
        toolEvents: [
          {
            tool_name: 'search_files',
            arguments: { query: 'test' },
            call_id: 'call-1',
          },
          {
            tool_name: 'read_file',
            arguments: { path: '/foo' },
            call_id: 'call-2',
            result: 'file contents',
          },
        ],
      }),
    ]
    const wrapper = mount(ThoughtStream, {
      props: { thoughts },
    })

    const badge = wrapper.find('.tool-badge')
    expect(badge.text()).toContain('2 tool(s) used')
  })

  it('does not render tool badge when no toolEvents', () => {
    const thoughts = [createThought({ content: 'Plain thought' })]
    const wrapper = mount(ThoughtStream, {
      props: { thoughts },
    })

    expect(wrapper.find('.tool-badge').exists()).toBe(false)
  })
})
