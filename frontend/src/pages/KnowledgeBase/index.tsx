import { useEffect, useState } from 'react'
import {
  Card, Button, Modal, Form, Input, Switch, Table, Tag, Space,
  Typography, message, Popconfirm, Empty, Upload, Progress,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, DatabaseOutlined,
  UploadOutlined, InboxOutlined,
} from '@ant-design/icons'
import {
  listKbs, createKb, deleteKb, listDocuments,
  uploadDocument, deleteDocument, batchDeleteDocs, batchRetryDocs,
} from '../../api/knowledgeBase'
import DocumentList from './DocumentList'
import type { KnowledgeBase, Document } from '../../api/knowledgeBase'

const { Title, Text } = Typography
const { Dragger } = Upload

export default function KnowledgeBasePage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedKb, setSelectedKb] = useState<KnowledgeBase | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

  const loadKbs = async () => {
    setLoading(true)
    try {
      const data = await listKbs()
      setKbs(data)
    } catch {
      message.error('加载知识库失败')
    } finally {
      setLoading(false)
    }
  }

  const loadDocs = async (kbId: number) => {
    setDocsLoading(true)
    try {
      const data = await listDocuments(kbId)
      setDocs(data)
    } catch {
      message.error('加载文档失败')
    } finally {
      setDocsLoading(false)
    }
  }

  useEffect(() => {
    loadKbs()
  }, [])

  useEffect(() => {
    if (selectedKb) loadDocs(selectedKb.id)
  }, [selectedKb])

  // 轮询处理中文档
  useEffect(() => {
    if (!selectedKb) return
    const hasProcessing = docs.some((d) => d.status === 'processing')
    if (!hasProcessing) return
    const timer = setInterval(() => loadDocs(selectedKb.id), 3000)
    return () => clearInterval(timer)
  }, [docs, selectedKb])

  const handleCreate = async (values: { name: string; description: string; is_public: boolean }) => {
    setCreating(true)
    try {
      await createKb(values)
      message.success('创建成功')
      setCreateOpen(false)
      form.resetFields()
      loadKbs()
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '创建失败')
    } finally {
      setCreating(false)
    }
  }

  const handleDeleteKb = async (kbId: number) => {
    try {
      await deleteKb(kbId)
      message.success('已删除')
      if (selectedKb?.id === kbId) {
        setSelectedKb(null)
        setDocs([])
      }
      loadKbs()
    } catch {
      message.error('删除失败')
    }
  }

  const handleUpload = async (file: File) => {
    if (!selectedKb) return false
    try {
      await uploadDocument(selectedKb.id, file)
      message.success(`${file.name} 上传成功`)
      loadDocs(selectedKb.id)
    } catch (err: any) {
      message.error(`${file.name} 上传失败: ${err?.response?.data?.detail || err.message}`)
    }
    return false
  }

  const handleDeleteDoc = async (docId: number) => {
    if (!selectedKb) return
    try {
      await deleteDocument(selectedKb.id, docId)
      message.success('已删除')
      loadDocs(selectedKb.id)
    } catch {
      message.error('删除失败')
    }
  }

  const handleRetryDoc = async (docId: number) => {
    if (!selectedKb) return
    try {
      await batchRetryDocs(selectedKb.id, [docId])
      message.success('已重新处理')
      loadDocs(selectedKb.id)
    } catch {
      message.error('重传失败')
    }
  }

  const handleBatchDelete = async (ids: number[]) => {
    if (!selectedKb) return
    try {
      await batchDeleteDocs(selectedKb.id, ids)
      message.success('批量删除完成')
      loadDocs(selectedKb.id)
    } catch {
      message.error('批量删除失败')
    }
  }

  const handleBatchRetry = async (ids: number[]) => {
    if (!selectedKb) return
    try {
      await batchRetryDocs(selectedKb.id, ids)
      message.success('批量重传完成')
      loadDocs(selectedKb.id)
    } catch {
      message.error('批量重传失败')
    }
  }

  const kbColumns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: KnowledgeBase) => (
        <Button
          type="link"
          style={{ padding: 0, fontWeight: selectedKb?.id === record.id ? 600 : 400 }}
          onClick={() => setSelectedKb(record)}
        >
          {name}
        </Button>
      ),
    },
    {
      title: '文档数',
      dataIndex: 'doc_count',
      key: 'doc_count',
      width: 80,
    },
    {
      title: '类型',
      key: 'type',
      width: 80,
      render: (_: unknown, record: KnowledgeBase) => (
        record.is_public
          ? <Tag color="blue">公共</Tag>
          : <Tag>私有</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 60,
      render: (_: unknown, record: KnowledgeBase) => (
        <Popconfirm title="确定删除该知识库？" onConfirm={() => handleDeleteKb(record.id)}>
          <Button type="link" danger icon={<DeleteOutlined />} size="small" />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <DatabaseOutlined /> 知识库管理
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          创建知识库
        </Button>
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        {/* 知识库列表 */}
        <Card style={{ width: 360, flexShrink: 0 }} size="small" title="知识库列表">
          <Table
            dataSource={kbs}
            columns={kbColumns}
            rowKey="id"
            size="small"
            loading={loading}
            pagination={false}
            locale={{ emptyText: '暂无知识库，点击右上角创建' }}
          />
        </Card>

        {/* 文档管理 */}
        <Card
          style={{ flex: 1 }}
          size="small"
          title={
            selectedKb
              ? `${selectedKb.name} — 文档列表`
              : '选择一个知识库'
          }
        >
          {selectedKb ? (
            <>
              <div style={{ marginBottom: 16 }}>
                <Dragger
                  multiple
                  showUploadList={false}
                  beforeUpload={handleUpload}
                  accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.md,.html,.htm,.png,.jpg,.jpeg,.bmp,.eml,.msg"
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
                  <p className="ant-upload-hint">
                    支持 PDF、Word、Excel、PPT、图片、网页、邮件等格式
                  </p>
                </Dragger>
              </div>
              <DocumentList
                documents={docs}
                loading={docsLoading}
                onDelete={handleDeleteDoc}
                onRetry={handleRetryDoc}
                onBatchDelete={handleBatchDelete}
                onBatchRetry={handleBatchRetry}
              />
            </>
          ) : (
            <Empty description="请从左侧选择一个知识库" />
          )}
        </Card>
      </div>

      {/* 创建知识库弹窗 */}
      <Modal
        title="创建知识库"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入知识库名称' }]}
          >
            <Input placeholder="例如：产品文档" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选描述" />
          </Form.Item>
          <Form.Item name="is_public" label="公共知识库" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={creating} block>
              创建
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
