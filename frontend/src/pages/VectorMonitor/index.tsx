import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Select, Input, Button, Space, Typography,
  Statistic, Row, Col, Modal, Empty, message,
} from 'antd'
import { SearchOutlined, EyeOutlined, DatabaseOutlined } from '@ant-design/icons'
import { getVectorStats, listChunks, searchChunks, getChunkDetail } from '../../api/admin'
import type { VectorStats, ChunkItem, ChunkDetail } from '../../api/admin'

const { Title, Text, Paragraph } = Typography

export default function VectorMonitorPage() {
  const [stats, setStats] = useState<VectorStats | null>(null)
  const [selectedKbId, setSelectedKbId] = useState<number | null>(null)
  const [chunks, setChunks] = useState<{ items: ChunkItem[]; total: number }>({ items: [], total: 0 })
  const [page, setPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const [filenameFilter, setFilenameFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<ChunkDetail | null>(null)
  const pageSize = 20

  const loadStats = async () => {
    try {
      const data = await getVectorStats()
      setStats(data)
      if (data.collections.length > 0 && selectedKbId === null) {
        const first = data.collections.find((c) => c.kb_id !== null)
        if (first) setSelectedKbId(first.kb_id!)
      }
    } catch {
      message.error('获取向量库信息失败')
    }
  }

  const loadChunks = async () => {
    if (selectedKbId === null) return
    setLoading(true)
    try {
      const data = searchQuery
        ? await searchChunks(selectedKbId, searchQuery, page, pageSize, filenameFilter || undefined)
        : await listChunks(selectedKbId, page, pageSize, filenameFilter || undefined)
      setChunks(data)
    } catch {
      message.error('查询失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadStats() }, [])
  useEffect(() => { loadChunks() }, [selectedKbId, page, searchQuery, filenameFilter])

  const handleDetail = async (chunkId: string) => {
    if (selectedKbId === null) return
    try {
      const data = await getChunkDetail(selectedKbId, chunkId)
      setDetail(data)
    } catch {
      message.error('获取详情失败')
    }
  }

  const columns = [
    {
      title: 'Chunk ID',
      dataIndex: 'chunk_id',
      width: 140,
      ellipsis: true,
      render: (id: string) => <Text code style={{ fontSize: 12 }}>{id}</Text>,
    },
    {
      title: '文件名',
      key: 'filename',
      width: 140,
      ellipsis: true,
      render: (_: unknown, record: ChunkItem) => record.filename || record.metadata?.filename || '-',
    },
    {
      title: '层级',
      key: 'level',
      width: 80,
      render: (_: unknown, record: ChunkItem) => {
        const level = record.chunk_level || (record.metadata?.chunk_level as string)
        return level ? <Tag>{level}</Tag> : '-'
      },
    },
    {
      title: '文本预览',
      dataIndex: 'text_preview',
      ellipsis: true,
    },
    {
      title: '操作',
      width: 60,
      render: (_: unknown, record: ChunkItem) => (
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => handleDetail(record.chunk_id)}
        >
          详情
        </Button>
      ),
    },
  ]

  const totalPages = Math.ceil(chunks.total / pageSize)

  return (
    <div style={{ padding: 24 }}>
      <Title level={4}><DatabaseOutlined /> 向量库监控</Title>

      {/* 概览 */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="Collections" value={stats.total_collections} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="总 Chunks" value={stats.total_chunks} />
            </Card>
          </Col>
        </Row>
      )}

      {/* Collection 选择 */}
      {stats && stats.collections.length > 0 && (
        <Space style={{ marginBottom: 16 }} wrap>
          <Text strong>选择知识库:</Text>
          <Select
            style={{ width: 320 }}
            value={selectedKbId}
            onChange={(v) => { setSelectedKbId(v); setPage(1) }}
            options={stats.collections
              .filter((c) => c.kb_id !== null)
              .map((c) => ({
                value: c.kb_id!,
                label: `${c.collection} | ${c.kb_name || '-'} | ${c.chunk_count} chunks`,
              }))}
          />
        </Space>
      )}

      {/* 搜索 */}
      <Space style={{ marginBottom: 16 }}>
        <Input
          placeholder="关键词搜索"
          prefix={<SearchOutlined />}
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setPage(1) }}
          style={{ width: 240 }}
          allowClear
        />
        <Input
          placeholder="文件名筛选"
          value={filenameFilter}
          onChange={(e) => { setFilenameFilter(e.target.value); setPage(1) }}
          style={{ width: 200 }}
          allowClear
        />
      </Space>

      {/* 分页信息 */}
      <div style={{ marginBottom: 8 }}>
        <Text type="secondary">
          共 {chunks.total} 条 | 第 {page}/{totalPages || 1} 页
        </Text>
      </div>

      {/* Chunk 列表 */}
      <Table
        dataSource={chunks.items}
        columns={columns}
        rowKey="chunk_id"
        size="small"
        loading={loading}
        pagination={false}
        locale={{ emptyText: '暂无数据' }}
      />

      {/* 分页按钮 */}
      {totalPages > 1 && (
        <Space style={{ marginTop: 16 }}>
          <Button disabled={page <= 1} onClick={() => setPage(1)}>首页</Button>
          <Button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
          <Button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</Button>
          <Button disabled={page >= totalPages} onClick={() => setPage(totalPages)}>末页</Button>
        </Space>
      )}

      {/* 详情弹窗 */}
      <Modal
        title="Chunk 详情"
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width={700}
      >
        {detail && (
          <div>
            <p><strong>Chunk ID:</strong> <Text code>{detail.chunk_id}</Text></p>
            <p><strong>文本内容:</strong></p>
            <Paragraph
              style={{
                maxHeight: 300,
                overflow: 'auto',
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 6,
                whiteSpace: 'pre-wrap',
              }}
            >
              {detail.text}
            </Paragraph>
            <p><strong>元数据:</strong></p>
            <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, overflow: 'auto', maxHeight: 200 }}>
              {JSON.stringify(detail.metadata, null, 2)}
            </pre>
            {detail.embedding && (
              <p>
                <strong>向量维度:</strong> {detail.embedding.length}
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  (前 5 维: [{detail.embedding.slice(0, 5).map((v) => v.toFixed(4)).join(', ')}])
                </Text>
              </p>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
