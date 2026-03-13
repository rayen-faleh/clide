// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatMessage from '@/components/ChatMessage.vue'
import type { ChatEntry } from '@/composables/useChat'

function createEntry(overrides: Partial<ChatEntry> = {}): ChatEntry {
  return {
    id: 'test-id',
    content: 'Test message',
    role: 'user',
    timestamp: new Date(),
    streaming: false,
    ...overrides,
  }
}

describe('ChatMessage', () => {
  it('renders user message content', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: createEntry({ role: 'user', content: 'Hello from user' }) },
    })

    expect(wrapper.text()).toContain('Hello from user')
    expect(wrapper.find('.chat-message').classes()).toContain('user')
  })

  it('renders assistant message content', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: createEntry({ role: 'assistant', content: 'Hello from assistant' }) },
    })

    expect(wrapper.text()).toContain('Hello from assistant')
    expect(wrapper.find('.chat-message').classes()).toContain('assistant')
  })

  it('shows streaming indicator when streaming', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        message: createEntry({ role: 'assistant', content: 'Thinking...', streaming: true }),
      },
    })

    expect(wrapper.find('.streaming-indicator').exists()).toBe(true)
  })

  it('does not show streaming indicator when not streaming', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        message: createEntry({ role: 'assistant', content: 'Done', streaming: false }),
      },
    })

    expect(wrapper.find('.streaming-indicator').exists()).toBe(false)
  })
})
