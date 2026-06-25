import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Select, Button, Space, Typography, message,
  Tabs, Statistic, Row, Col, Progress, Input, Modal, Empty,
} from 'antd'
import {
  LikeOutlined, DislikeOutlined, EditOutlined,
  DownloadOutlined, CheckOutlined, CloseOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../../stores/authStore'
import {
  listFeedbacks, updateFeedbackStatus, getAdminStats, exportFeedback,
} from '../../api/evaluation'
import type { Feedback, FeedbackStats } from '../../api/evaluation'

const { Title, Text } = Typography

const typeIcon: Record<string, React.ReactNode> = {
  useful: <LikeOutlined style={{ color: '#52c41a' }} />,
  useless: <DislikeOutlined style={{ color: '#ff4d4f' }} />,
  correction: <EditOutlined style={{ color: '#1677ff' }} />,
}
const typeLabel: Record<string, string> = { useful: '有用', useless: '无用', correction: '纠正' }
const statusColor: Record<string, string> = {
  pending: 'gold', reviewed: 'blue', adopted: 'green', dismissed: 'default', closed: 'default',
}
const statusLabel: Record<string, string> = {
  pending: '待处理', reviewed: '已审阅', adopted: '已采纳', dismissed: '已忽略', closed: '已关闭',
}

export default function FeedbackPage() {
  const { userRole } = useAuthStore()
  const isAdmin = userRole === 'admin'

  if (!isAdmin) return <UserFeedback />
  return <AdminFeedback />
}

// ---------- 普通用户反馈 ----------
function UserFeedback() {
  const [items, setItems] = useState<Feedback[]>([])
  const [loading, setLoading] = useState(false)
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [statusFilter, setStatusFilter] = useState<string | undefined>()

  const load = async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { limit: 50 }
      if (typeFilter) params.feedback_type = typeFilter
      if (statusFilter) params.status = statusFilter
      const res = await listFeedbacks(params)
      setItems(res.items)
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [typeFilter, statusFilter])

  const columns = [
    {
      title: '类型',
      dataIndex: 'feedback_type',
      width: 80,
      render: (t: string) => (
        <Space>{typeIcon[t]} {typeLabel[t]}</Space>
      ),
    },
    {
      title: '问题',
      dataIndex: 'question',
      ellipsis: true,
      render: (q: string) => q || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => <Tag color={statusColor[s]}>{statusLabel[s] || s}</Tag>,
    },
    {
      title: '管理员回复',
      dataIndex: 'admin_reply',
      ellipsis: true,
      render: (r: string) => r || '-',
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (t: string) => t?.slice(0, 19).replace('T', ' '),
    },
    {
      title: '操作',
      width: 80,
      render: (_: unknown, record: Feedback) =>
        record.status === 'pending' ? (
          <Button
            size="small"
            onClick={async () => {
              await updateFeedbackStatus(record.id, 'closed')
              load()
            }}
          >
            关闭
          </Button>
        ) : null,
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={4}>我的反馈</Title>
      <Space style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="反馈类型"
          style={{ width: 120 }}
          value={typeFilter}
          onChange={setTypeFilter}
          options={[
            { value: 'useful', label: '有用' },
            { value: 'useless', label: '无用' },
            { value: 'correction', label: '纠正' },
          ]}
        />
        <Select
          allowClear
          placeholder="处理状态"
          style={{ width: 120 }}
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { value: 'pending', label: '待处理' },
            { value: 'reviewed', label: '已审阅' },
            { value: 'adopted', label: '已采纳' },
            { value: 'closed', label: '已关闭' },
          ]}
        />
      </Space>
      <Table
        dataSource={items}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 20 }}
        locale={{ emptyText: '暂无反馈记录' }}
      />
    </div>
  )
}

// ---------- 管理员反馈管理 ----------
function AdminFeedback() {
  const [items, setItems] = useState<Feedback[]>([])
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState<FeedbackStats | null>(null)
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [replyModal, setReplyModal] = useState<{ id: number; reply: string } | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { limit: 50 }
      if (typeFilter) params.feedback_type = typeFilter
      if (statusFilter) params.status = statusFilter
      const res = await listFeedbacks(params)
      setItems(res.items)
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const data = await getAdminStats()
      setStats(data)
    } catch { /* ignore */ }
  }

  useEffect(() => { load(); loadStats() }, [typeFilter, statusFilter])

  const handleStatus = async (id: number, status: string) => {
    try {
      await updateFeedbackStatus(id, status)
      message.success('已更新')
      load()
      loadStats()
    } catch {
      message.error('操作失败')
    }
  }

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      const data = await exportFeedback(format)
      const blob = new Blob([data], {
        type: format === 'csv' ? 'text/csv' : 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `feedback_export.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('导出失败')
    }
  }

  const columns = [
    {
      title: '类型',
      dataIndex: 'feedback_type',
      width: 80,
      render: (t: string) => (
        <Space>{typeIcon[t]} {typeLabel[t]}</Space>
      ),
    },
    {
      title: '用户ID',
      dataIndex: 'user_id',
      width: 70,
    },
    {
      title: '问题',
      dataIndex: 'question',
      ellipsis: true,
      render: (q: string) => q || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => <Tag color={statusColor[s]}>{statusLabel[s] || s}</Tag>,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (t: string) => t?.slice(0, 19).replace('T', ' '),
    },
    {
      title: '操作',
      width: 200,
      render: (_: unknown, record: Feedback) => (
        <Space>
          <Button size="small" onClick={() => handleStatus(record.id, 'reviewed')}>已审阅</Button>
          <Button size="small" type="primary" onClick={() => handleStatus(record.id, 'adopted')}>采纳</Button>
          <Button
            size="small"
            onClick={() => setReplyModal({ id: record.id, reply: record.admin_reply || '' })}
          >
            回复
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={4}>反馈管理</Title>

      {/* 统计卡片 */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="总反馈数" value={stats.total} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="待处理" value={stats.total - stats.useful - stats.useless - stats.corrections} valueStyle={{ color: '#faad14' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="有用" value={stats.useful} prefix={<LikeOutlined />} valueStyle={{ color: '#52c41a' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="纠正" value={stats.corrections} prefix={<EditOutlined />} valueStyle={{ color: '#1677ff' }} />
            </Card>
          </Col>
        </Row>
      )}

      {/* 筛选 + 导出 */}
      <Space style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="反馈类型"
          style={{ width: 120 }}
          value={typeFilter}
          onChange={setTypeFilter}
          options={[
            { value: 'useful', label: '有用' },
            { value: 'useless', label: '无用' },
            { value: 'correction', label: '纠正' },
          ]}
        />
        <Select
          allowClear
          placeholder="处理状态"
          style={{ width: 120 }}
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { value: 'pending', label: '待处理' },
            { value: 'reviewed', label: '已审阅' },
            { value: 'adopted', label: '已采纳' },
            { value: 'dismissed', label: '已忽略' },
            { value: 'closed', label: '已关闭' },
          ]}
        />
        <Button icon={<DownloadOutlined />} onClick={() => handleExport('csv')}>导出 CSV</Button>
        <Button icon={<DownloadOutlined />} onClick={() => handleExport('json')}>导出 JSON</Button>
      </Space>

      <Table
        dataSource={items}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 20 }}
        expandable={{
          expandedRowRender: (record) => (
            <div style={{ padding: 8 }}>
              {record.question && <p><strong>问题:</strong> {record.question}</p>}
              {record.answer && <p><strong>回答:</strong> {record.answer.slice(0, 300)}</p>}
              {record.reason && <p><strong>无用原因:</strong> {record.reason}</p>}
              {record.correction && <p><strong>纠正内容:</strong> {record.correction}</p>}
              {record.admin_reply && <p><strong>审核备注:</strong> {record.admin_reply}</p>}
            </div>
          ),
        }}
      />

      {/* 回复弹窗 */}
      <Modal
        title="审核备注"
        open={!!replyModal}
        onCancel={() => setReplyModal(null)}
        onOk={async () => {
          if (replyModal) {
            await updateFeedbackStatus(replyModal.id, 'reviewed')
            setReplyModal(null)
            load()
          }
        }}
      >
        <Input.TextArea
          rows={3}
          value={replyModal?.reply || ''}
          onChange={(e) => setReplyModal((prev) => prev ? { ...prev, reply: e.target.value } : null)}
          placeholder="填写审核备注…"
        />
      </Modal>
    </div>
  )
}
