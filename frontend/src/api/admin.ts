import client from './client'

export interface VectorStats {
  total_collections: number
  total_chunks: number
  collections: {
    collection: string
    kb_id: number | null
    kb_name: string | null
    chunk_count: number
  }[]
}

export interface ChunkItem {
  chunk_id: string
  text_preview: string
  filename: string
  chunk_level: string
  modality: string
  created_at: string
  metadata: Record<string, unknown>
}

export interface ChunkDetail {
  chunk_id: string
  text: string
  embedding: number[]
  metadata: Record<string, unknown>
}

export async function getVectorStats(): Promise<VectorStats> {
  const res = await client.get('/api/admin/vectors/stats')
  return res.data
}

export async function listChunks(
  kbId: number,
  page = 1,
  pageSize = 20,
  filename?: string
): Promise<{ items: ChunkItem[]; total: number }> {
  const res = await client.get(`/api/admin/vectors/${kbId}/chunks`, {
    params: { page, page_size: pageSize, filename },
  })
  return res.data
}

export async function searchChunks(
  kbId: number,
  query: string,
  page = 1,
  pageSize = 20,
  filename?: string
): Promise<{ items: ChunkItem[]; total: number }> {
  const res = await client.get(`/api/admin/vectors/${kbId}/search`, {
    params: { q: query, page, page_size: pageSize, filename },
  })
  return res.data
}

export async function getChunkDetail(
  kbId: number,
  chunkId: string
): Promise<ChunkDetail> {
  const res = await client.get(`/api/admin/vectors/${kbId}/chunks/${chunkId}`)
  return res.data
}

// ---------------------------------------------------------------------------
// 仪表盘 API
// ---------------------------------------------------------------------------

export interface DashboardOverview {
  today_query_count: number
  avg_latency_ms: number
  p95_latency_ms: number
  satisfaction_rate: number
}

export interface LatencyBreakdown {
  retrieval: { avg_ms: number; p95_ms: number }
  rerank: { avg_ms: number; p95_ms: number }
  generation: { avg_ms: number; p95_ms: number }
}

export interface HourlyMetric {
  hour: string
  count: number
  error_count?: number
  error_rate?: number
  avg_latency_ms?: number
  p95_latency_ms?: number
  useful?: number
  useless?: number
}

export interface TokenUsage {
  model: string
  call_count: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
}

export interface DislikedDoc {
  kb_id: number
  kb_name: string
  dislike_count: number
}

export interface Alert {
  level: string
  message: string
  timestamp: string
}

export interface HttpOverview {
  total_requests: number
  error_5xx_count: number
  error_5xx_rate: number
  avg_latency_ms: number
  p50_latency_ms: number
  p95_latency_ms: number
  p99_latency_ms: number
  qps: number
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  const res = await client.get('/api/dashboard/overview')
  return res.data
}

export async function getLatencyBreakdown(hours = 24): Promise<LatencyBreakdown> {
  const res = await client.get('/api/dashboard/latency-breakdown', { params: { hours } })
  return res.data
}

export async function getErrorRate(hours = 24): Promise<HourlyMetric[]> {
  const res = await client.get('/api/dashboard/error-rate', { params: { hours } })
  return res.data
}

export async function getFeedbackTrend(hours = 24): Promise<HourlyMetric[]> {
  const res = await client.get('/api/dashboard/feedback-trend', { params: { hours } })
  return res.data
}

export async function getFeedbackTopDocs(limit = 5): Promise<DislikedDoc[]> {
  const res = await client.get('/api/dashboard/feedback-top-docs', { params: { limit } })
  return res.data
}

export async function getTokenUsage(hours = 24): Promise<TokenUsage[]> {
  const res = await client.get('/api/dashboard/token-usage', { params: { hours } })
  return res.data
}

export async function getAlerts(): Promise<Alert[]> {
  const res = await client.get('/api/dashboard/alerts')
  return res.data
}

export async function getHttpOverview(hours = 24): Promise<HttpOverview> {
  const res = await client.get('/api/dashboard/http-overview', { params: { hours } })
  return res.data
}
