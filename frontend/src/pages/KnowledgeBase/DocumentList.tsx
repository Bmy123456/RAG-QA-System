import { Table, Tag, Progress, Button, Space, Popconfirm, message } from 'antd'
import { DeleteOutlined, ReloadOutlined, FileTextOutlined } from '@ant-design/icons'
import type { Document } from '../../api/knowledgeBase'

interface Props {
  documents: Document[]
  loading: boolean
  onDelete: (docId: number) => void
  onRetry: (docId: number) => void
  onBatchDelete: (ids: number[]) => void
  onBatchRetry: (ids: number[]) => void
}

const statusMap: Record<string, { color: string; label: string }> = {
  completed: { color: 'green', label: '已完成' },
  processing: { color: 'blue', label: '处理中' },
  pending: { color: 'default', label: '待处理' },
  failed: { color: 'red', label: '失败' },
}

const typeIcon: Record<string, string> = {
  pdf: '📄',
  docx: '📝',
  doc: '📝',
  xlsx: '📊',
  xls: '📊',
  pptx: '📽️',
  ppt: '📽️',
  txt: '📃',
  md: '📃',
  html: '🌐',
  htm: '🌐',
  png: '🖼️',
  jpg: '🖼️',
  jpeg: '🖼️',
  bmp: '🖼️',
  eml: '✉️',
  msg: '✉️',
}

export default function DocumentList({
  documents,
  loading,
  onDelete,
  onRetry,
  onBatchDelete,
  onBatchRetry,
}: Props) {
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const columns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      ellipsis: true,
      render: (name: string, record: Document) => (
        <Space>
          <span>{typeIcon[record.file_type] || '📄'}</span>
          <span>{name}</span>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string, record: Document) => {
        const { color, label } = statusMap[status] || { color: 'default', label: status }
        return (
          <div>
            <Tag color={color}>{label}</Tag>
            {status === 'processing' && (
              <Progress
                percent={record.progress}
                size="small"
                status="active"
                format={(p) => `${p}%`}
              />
            )}
            {status === 'processing' && record.progress_msg && (
              <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                {record.progress_msg}
              </div>
            )}
          </div>
        )
      },
    },
    {
      title: '分块数',
      dataIndex: 'chunk_count',
      key: 'chunk_count',
      width: 80,
      render: (n: number) => (n > 0 ? n : '-'),
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      key: 'file_size',
      width: 80,
      render: (size: number) => {
        if (size < 1024) return `${size} B`
        if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
        return `${(size / 1024 / 1024).toFixed(1)} MB`
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: Document) => (
        <Space>
          {record.status === 'failed' && (
            <Button
              type="link"
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => onRetry(record.id)}
            >
              重传
            </Button>
          )}
          <Popconfirm title="确定删除？" onConfirm={() => onDelete(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      {selectedRowKeys.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Space>
            <span>已选 {selectedRowKeys.length} 项</span>
            <Button
              size="small"
              danger
              onClick={() => {
                onBatchDelete(selectedRowKeys as number[])
                setSelectedRowKeys([])
              }}
            >
              批量删除
            </Button>
            <Button
              size="small"
              onClick={() => {
                onBatchRetry(selectedRowKeys as number[])
                setSelectedRowKeys([])
              }}
            >
              批量重传
            </Button>
          </Space>
        </div>
      )}
      <Table
        dataSource={documents}
        columns={columns}
        rowKey="id"
        size="small"
        loading={loading}
        pagination={false}
        rowSelection={{
          selectedRowKeys,
          onChange: setSelectedRowKeys,
          getCheckboxProps: (record: Document) => ({
            disabled: record.status === 'processing',
          }),
        }}
        locale={{ emptyText: '暂无文档' }}
      />
    </div>
  )
}

import { useState } from 'react'
