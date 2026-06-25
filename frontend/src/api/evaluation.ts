import client from './client'

export interface Feedback {
  id: number
  user_id: number
  session_id: string
  message_index: number
  feedback_type: 'useful' | 'useless' | 'correction'
  question: string
  answer: string
  reason: string | null
  correction: string | null
  status: string
  admin_reply: string | null
  kb_id: number | null
  created_at: string
  reviewed_at: string | null
}

export interface FeedbackStats {
  total: number
  useful: number
  useless: number
  corrections: number
  satisfaction_rate: number
  trend: { date: string; count: number }[]
  distribution: { useful: number; useless: number; correction: number }
}

export interface QueryLog {
  id: number
  session_id: string
  question: string
  rewritten_query: string | null
  answer: string
  model: string
  latency_ms: number
  token_total: number
  retrieval_count: number
  reranked_count: number
  retrieval_strategy: string
  created_at: string
}

export interface QueryLogStats {
  total: number
  avg_latency_ms: number
  avg_tokens: number
  avg_retrieval_count: number
}

// 提交反馈
export async function submitFeedback(data: {
  session_id: string
  message_index: number
  feedback_type: string
  reason?: string
  correction?: string
  question?: string
  answer?: string
}): Promise<void> {
  await client.post('/api/evaluation/feedback', data)
}

// 获取反馈列表
export async function listFeedbacks(params?: {
  limit?: number
  feedback_type?: string
  status?: string
  session_id?: string
  kb_id?: number
  created_after?: string
}): Promise<{ items: Feedback[]; total: number }> {
  const res = await client.get('/api/evaluation/feedback', { params })
  return res.data
}

// 更新反馈状态
export async function updateFeedbackStatus(
  feedbackId: number,
  status: string
): Promise<void> {
  await client.put(`/api/evaluation/feedback/${feedbackId}/status?status=${status}`)
}

// 获取综合统计
export async function getStats(): Promise<{
  feedback: FeedbackStats
  query_log: QueryLogStats
}> {
  const res = await client.get('/api/evaluation/stats')
  return res.data
}

// 获取查询日志
export async function listQueryLogs(limit = 50): Promise<QueryLog[]> {
  const res = await client.get('/api/evaluation/logs', { params: { limit } })
  return res.data
}

// 管理员统计
export async function getAdminStats(): Promise<FeedbackStats> {
  const res = await client.get('/api/evaluation/admin/stats')
  return res.data
}

// 管理员导出
export async function exportFeedback(
  format: 'csv' | 'json',
  params?: Record<string, string>
): Promise<string> {
  const res = await client.get('/api/evaluation/admin/export', {
    params: { format, ...params },
  })
  return typeof res.data === 'string' ? res.data : JSON.stringify(res.data)
}
