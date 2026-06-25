import client from './client'

export interface KnowledgeBase {
  id: number
  name: string
  description: string | null
  is_public: boolean
  doc_count: number
  created_at: string
}

export interface Document {
  id: number
  filename: string
  file_type: string
  file_size: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error_msg: string | null
  chunk_count: number
  progress: number
  progress_msg: string | null
  created_at: string
}

export async function listKbs(): Promise<KnowledgeBase[]> {
  const res = await client.get('/api/kb')
  return res.data
}

export async function createKb(data: {
  name: string
  description?: string
  is_public?: boolean
}): Promise<KnowledgeBase> {
  const res = await client.post('/api/kb', data)
  return res.data
}

export async function deleteKb(kbId: number): Promise<void> {
  await client.delete(`/api/kb/${kbId}`)
}

export async function listDocuments(kbId: number): Promise<Document[]> {
  const res = await client.get(`/api/kb/${kbId}/documents`)
  return res.data
}

export async function uploadDocument(
  kbId: number,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  await client.post(`/api/kb/${kbId}/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    },
  })
}

export async function deleteDocument(kbId: number, docId: number): Promise<void> {
  await client.delete(`/api/kb/${kbId}/documents/${docId}`)
}

export async function batchDeleteDocs(kbId: number, docIds: number[]): Promise<void> {
  await client.post(`/api/kb/${kbId}/documents/batch/delete`, { doc_ids: docIds })
}

export async function batchRetryDocs(kbId: number, docIds: number[]): Promise<void> {
  await client.post(`/api/kb/${kbId}/documents/batch/retry`, { doc_ids: docIds })
}

export async function getDocumentChunks(
  kbId: number,
  docId: number
): Promise<{ id: number; chunk_index: number; content: string }[]> {
  const res = await client.get(`/api/kb/${kbId}/documents/${docId}/chunks`)
  return res.data
}
