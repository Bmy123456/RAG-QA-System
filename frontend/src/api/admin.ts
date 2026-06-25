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
