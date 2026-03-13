import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChat } from '@/composables/useChat'
import type { WSMessage } from '@/types/messages'

describe('useChat', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('sendMessage adds user message and assistant placeholder', () => {
    const sendWs = vi.fn()
    const { messages, sendMessage } = useChat(sendWs)

    sendMessage('Hello')

    expect(messages.value).toHaveLength(2)
    expect(messages.value[0].role).toBe('user')
    expect(messages.value[0].content).toBe('Hello')
    expect(messages.value[1].role).toBe('assistant')
    expect(messages.value[1].content).toBe('')
    expect(messages.value[1].streaming).toBe(true)
  })

  it('sendMessage calls sendWs with correct WSMessage', () => {
    const sendWs = vi.fn()
    const { sendMessage } = useChat(sendWs)

    sendMessage('Hello')

    expect(sendWs).toHaveBeenCalledOnce()
    const msg = sendWs.mock.calls[0][0] as WSMessage
    expect(msg.type).toBe('chat_message')
    expect(msg.payload).toEqual({ content: 'Hello', role: 'user' })
    expect(msg.timestamp).toBeDefined()
  })

  it('handleResponseChunk appends content to last assistant message', () => {
    const sendWs = vi.fn()
    const { messages, sendMessage, handleResponseChunk } = useChat(sendWs)

    sendMessage('Hello')

    handleResponseChunk({
      type: 'chat_response_chunk',
      payload: { content: 'Hi ', done: false },
      timestamp: new Date().toISOString(),
    })

    handleResponseChunk({
      type: 'chat_response_chunk',
      payload: { content: 'there!', done: false },
      timestamp: new Date().toISOString(),
    })

    expect(messages.value[1].content).toBe('Hi there!')
    expect(messages.value[1].streaming).toBe(true)
  })

  it('handleResponseChunk with done=true marks streaming complete', () => {
    const sendWs = vi.fn()
    const { messages, isStreaming, sendMessage, handleResponseChunk } = useChat(sendWs)

    sendMessage('Hello')
    expect(isStreaming.value).toBe(true)

    handleResponseChunk({
      type: 'chat_response_chunk',
      payload: { content: 'Hi', done: false },
      timestamp: new Date().toISOString(),
    })

    handleResponseChunk({
      type: 'chat_response_chunk',
      payload: { content: '', done: true },
      timestamp: new Date().toISOString(),
    })

    expect(messages.value[1].streaming).toBe(false)
    expect(isStreaming.value).toBe(false)
  })

  it('clearMessages resets state', () => {
    const sendWs = vi.fn()
    const { messages, isStreaming, sendMessage, clearMessages } = useChat(sendWs)

    sendMessage('Hello')
    expect(messages.value).toHaveLength(2)
    expect(isStreaming.value).toBe(true)

    clearMessages()
    expect(messages.value).toHaveLength(0)
    expect(isStreaming.value).toBe(false)
  })
})
