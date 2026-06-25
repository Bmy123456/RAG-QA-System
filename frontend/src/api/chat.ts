import client from './client'

export interface ChatRequest {
  question: string
  kb_id?: number | null
  session_id?: string | null
  strategy?: string
  top_k?: number
  stream?: boolean
}

export interface Source {
  index: number
  chunk_id: string
  filename: string
  page: number | null
  snippet: string
}

export interface ChatResponse {
  session_id: string
  answer: string
  sources: Source[]
  rewritten_query?: string
  model: string
}

export interface SessionInfo {
  session_id: string
  title: string
  message_count: number
  created_at: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  metadata?: {
    sources?: Source[]
  }
}

export interface HistoryResponse {
  session_id: string
  kb_id: number
  messages: ChatMessage[]
}

// 非流式对话
export async function sendMessage(req: ChatRequest): Promise<ChatResponse> {
  const res = await client.post('/api/chat', { ...req, stream: false })
  return res.data
}

// 获取会话列表
export async function listSessions(kbId?: number): Promise<SessionInfo[]> {
  const params = kbId ? { kb_id: kbId } : {}
  const res = await client.get('/api/chat/sessions', { params })
  return res.data
}

// 获取会话历史
export async function getHistory(sessionId: string): Promise<HistoryResponse> {
  const res = await client.get(`/api/chat/history/${sessionId}`)
  return res.data
}

// 删除会话
export async function deleteSession(sessionId: string): Promise<void> {
  await client.delete(`/api/chat/history/${sessionId}`)
}

// SSE 流式对话
export async function streamChat(
  req: ChatRequest,
  onToken: (token: string) => void,
  onSources: (sources: Source[]) => void,
  onSession: (sessionId: string) => void,
  onDone: () => void,
  onError: (err: Error) => void
): Promise<void> {
  const token = localStorage.getItem('access_token')
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ ...req, stream: true }),
    })

    if (response.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
      return
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    // 从响应头获取 session_id
    const sid = response.headers.get('x-session-id')
    if (sid) onSession(sid)

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        if (data === '[DONE]') {
          onDone()
          return
        }
        if (data.startsWith('[SOURCES]')) {
          try {
            const sources = JSON.parse(data.slice(9))
            onSources(sources)
          } catch { /* ignore */ }
          continue
        }
        onToken(data)
      }
    }
    onDone()
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}
