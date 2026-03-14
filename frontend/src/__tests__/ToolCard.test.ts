// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolCard from '@/components/ToolCard.vue'
import type { ToolEvent } from '@/stores/agent'

function createEvent(overrides: Partial<ToolEvent> = {}): ToolEvent {
  return {
    id: 'test-id',
    type: 'tool',
    tool_name: 'search_files',
    arguments: { query: 'hello' },
    call_id: 'call-123',
    status: 'executing',
    timestamp: new Date(),
    ...overrides,
  }
}

describe('ToolCard', () => {
  it('renders tool name', () => {
    const wrapper = mount(ToolCard, {
      props: { event: createEvent({ tool_name: 'read_file' }) },
    })

    expect(wrapper.find('.tool-name').text()).toBe('read_file')
  })

  it('renders executing status with spinner', () => {
    const wrapper = mount(ToolCard, {
      props: { event: createEvent({ status: 'executing' }) },
    })

    expect(wrapper.find('.tool-card').classes()).toContain('executing')
    expect(wrapper.find('.spinner').exists()).toBe(true)
    expect(wrapper.find('.tool-status').text()).toBe('executing')
  })

  it('renders success status', () => {
    const wrapper = mount(ToolCard, {
      props: { event: createEvent({ status: 'success', result: 'done' }) },
    })

    expect(wrapper.find('.tool-card').classes()).toContain('success')
    expect(wrapper.find('.spinner').exists()).toBe(false)
  })

  it('renders error status', () => {
    const wrapper = mount(ToolCard, {
      props: { event: createEvent({ status: 'error', error: 'something failed' }) },
    })

    expect(wrapper.find('.tool-card').classes()).toContain('error')
    expect(wrapper.find('.spinner').exists()).toBe(false)
  })

  it('shows arguments when expanded', async () => {
    const wrapper = mount(ToolCard, {
      props: { event: createEvent({ arguments: { path: '/tmp/file.txt' } }) },
    })

    expect(wrapper.find('.tool-details').exists()).toBe(false)

    await wrapper.find('.tool-header').trigger('click')

    expect(wrapper.find('.tool-details').exists()).toBe(true)
    expect(wrapper.find('.tool-json').text()).toContain('/tmp/file.txt')
  })

  it('shows result when available and expanded', async () => {
    const wrapper = mount(ToolCard, {
      props: { event: createEvent({ status: 'success', result: 'file contents here' }) },
    })

    await wrapper.find('.tool-header').trigger('click')

    const sections = wrapper.findAll('.tool-section')
    expect(sections.length).toBe(2)
    expect(wrapper.text()).toContain('file contents here')
  })

  it('shows error when available and expanded', async () => {
    const wrapper = mount(ToolCard, {
      props: { event: createEvent({ status: 'error', error: 'file not found' }) },
    })

    await wrapper.find('.tool-header').trigger('click')

    expect(wrapper.find('.tool-section.error').exists()).toBe(true)
    expect(wrapper.text()).toContain('file not found')
  })
})
