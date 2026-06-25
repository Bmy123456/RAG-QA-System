import { create } from 'zustand'
import type { Source } from '../api/chat'

export interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  feedbackType?: string
}

interface ChatState {
  // 会话
  sessionId: string | null
  messages: Message[]

  // 当前知识库
  kbId: number | null
  kbName: string

  // 流式状态
  streaming: boolean
  streamingAnswer: string
  streamingSources: Source[]

  // actions
  setKb: (id: number | null, name: string) => void
  setSession: (id: string | null) => void
  setMessages: (msgs: Message[]) => void
  addMessage: (msg: Message) => void
  clearMessages: () => void
  markFeedback: (index: number, type: string) => void

  // 流式控制
  startStream: () => void
  appendToken: (token: string) => void
  setSources: (sources: Source[]) => void
  finishStream: () => void
  cancelStream: () => void
}

export const useChatStore = create<ChatState>()((set, get) => ({
  sessionId: null,
  messages: [],
  kbId: null,
  kbName: '',
  streaming: false,
  streamingAnswer: '',
  streamingSources: [],

  setKb: (id, name) => set({ kbId: id, kbName: name, sessionId: null, messages: [] }),

  setSession: (id) => set({ sessionId: id }),

  setMessages: (msgs) => set({ messages: msgs }),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  clearMessages: () => set({ messages: [], sessionId: null }),

  markFeedback: (index, type) =>
    set((s) => {
      const msgs = [...s.messages]
      if (msgs[index]) msgs[index] = { ...msgs[index], feedbackType: type }
      return { messages: msgs }
    }),

  startStream: () => set({ streaming: true, streamingAnswer: '', streamingSources: [] }),

  appendToken: (token) =>
    set((s) => ({ streamingAnswer: s.streamingAnswer + token })),

  setSources: (sources) => set({ streamingSources: sources }),

  finishStream: () => {
    const { streamingAnswer, streamingSources, messages } = get()
    set({
      streaming: false,
      messages: [
        ...messages,
        { role: 'assistant', content: streamingAnswer, sources: streamingSources },
      ],
      streamingAnswer: '',
      streamingSources: [],
    })
  },

  cancelStream: () => {
    const { streamingAnswer, streamingSources, messages } = get()
    const answer = streamingAnswer
      ? streamingAnswer + '\n\n*（回答被中断）*'
      : ''
    set({
      streaming: false,
      messages: answer
        ? [...messages, { role: 'assistant', content: answer, sources: streamingSources }]
        : messages,
      streamingAnswer: '',
      streamingSources: [],
    })
  },
}))
