import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useWebSocket, resetWebSocketState } from '@/composables/useWebSocket'
import type { WSMessage } from '@/types/messages'

class MockWebSocket {
  static OPEN = 1
  static CLOSED = 3
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.OPEN
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send = vi.fn()
  close = vi.fn()

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  simulateMessage(data: WSMessage) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  simulateError() {
    this.onerror?.(new Event('error'))
  }

  simulateClose() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  }
}

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
  resetWebSocketState()
})

describe('useWebSocket', () => {
  it('initial status is disconnected', () => {
    const { status } = useWebSocket('ws://localhost:8000/ws')
    expect(status.value).toBe('disconnected')
  })

  it('connect sets status to connecting then connected on open', () => {
    const { status, connect } = useWebSocket('ws://localhost:8000/ws')

    connect()
    expect(status.value).toBe('connecting')

    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()
    expect(status.value).toBe('connected')
  })

  it('on/off register and remove handlers correctly', () => {
    const { connect, on, off } = useWebSocket('ws://localhost:8000/ws')

    connect()
    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()

    const handler = vi.fn()
    on('chat_response_chunk', handler)

    const msg: WSMessage = {
      type: 'chat_response_chunk',
      payload: { content: 'hello', done: false },
      timestamp: new Date().toISOString(),
    }
    ws.simulateMessage(msg)
    expect(handler).toHaveBeenCalledOnce()
    expect(handler).toHaveBeenCalledWith(msg)

    off('chat_response_chunk', handler)
    ws.simulateMessage(msg)
    expect(handler).toHaveBeenCalledOnce() // not called again
  })

  it('wildcard handlers receive all messages', () => {
    const { connect, on } = useWebSocket('ws://localhost:8000/ws')

    connect()
    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()

    const handler = vi.fn()
    on('*', handler)

    const msg: WSMessage = {
      type: 'state_change',
      payload: { new_state: 'thinking' },
      timestamp: new Date().toISOString(),
    }
    ws.simulateMessage(msg)
    expect(handler).toHaveBeenCalledOnce()
  })

  it('send calls ws.send with JSON string', () => {
    const { connect, send } = useWebSocket('ws://localhost:8000/ws')

    connect()
    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()

    const msg: WSMessage = {
      type: 'chat_message',
      payload: { content: 'hello', role: 'user' },
      timestamp: new Date().toISOString(),
    }
    send(msg)
    expect(ws.send).toHaveBeenCalledWith(JSON.stringify(msg))
  })

  it('send sets error when not connected', () => {
    const { error, send } = useWebSocket('ws://localhost:8000/ws')

    const msg: WSMessage = {
      type: 'chat_message',
      payload: { content: 'hello', role: 'user' },
      timestamp: new Date().toISOString(),
    }
    send(msg)
    expect(error.value).toBe('WebSocket is not connected')
  })

  it('disconnect closes the connection', () => {
    const { status, connect, disconnect } = useWebSocket('ws://localhost:8000/ws')

    connect()
    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()

    disconnect()
    expect(ws.close).toHaveBeenCalled()
    expect(status.value).toBe('disconnected')
  })

  it('shares state across multiple calls (singleton)', () => {
    const first = useWebSocket('ws://localhost:8000/ws')
    const second = useWebSocket('ws://localhost:8000/ws')

    first.connect()
    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()

    expect(first.status.value).toBe('connected')
    expect(second.status.value).toBe('connected')
  })
})
