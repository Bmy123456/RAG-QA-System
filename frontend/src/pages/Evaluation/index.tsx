import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Typography, Row, Col, Statistic, Space, Slider, Empty, message,
} from 'antd'
import {
  LikeOutlined, DislikeOutlined, EditOutlined,
  DashboardOutlined, ThunderboltOutlined, DatabaseOutlined,
} from '@ant-design/icons'
import { getStats, listFeedbacks, listQueryLogs } from '../../api/evaluation'
import type { FeedbackStats, QueryLogStats, Feedback, QueryLog } from '../../api/evaluation'

const { Title, Text } = Typography

export default function EvaluationPage() {
  const [stats, setStats] = useState<{ feedback: FeedbackStats; query_log: QueryLogStats } | null>(null)
  const [feedbacks, setFeedbacks] = useState<Feedback[]>([])
  const [logs, setLogs] = useState<QueryLog[]>([])
  const [fbLimit, setFbLimit] = useState(50)
  const [logLimit, setLogLimit] = useState(50)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [s, fb, ql] = await Promise.all([
          getStats().catch(() => null),
          listFeedbacks({ limit: fbLimit }).catch(() => ({ items: [] })),
          listQueryLogs(logLimit).catch(() => []),
        ])
        setStats(s)
        setFeedbacks(fb.items)
        setLogs(ql)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [fbLimit, logLimit])

  const fbTypeIcon: Record<string, React.ReactNode> = {
    useful: <LikeOutlined style={{ color: '#52c41a' }} />,
    useless: <DislikeOutlined style={{ color: '#ff4d4f' }} />,
    correction: <EditOutlined style={{ color: '#1677ff' }} />,
  }
  const fbTypeLabel: Record<string, string> = { useful: '有用', useless: '无用', correction: '纠正' }
  const statusColor: Record<string, string> = {
    pending: 'gold', reviewed: 'blue', adopted: 'green', closed: 'default',
  }
  const statusLabel: Record<string, string> = {
    pending: '待处理', reviewed: '已审阅', adopted: '已采纳', closed: '已关闭',
  }

  const fbColumns = [
    {
      title: '类型',
      dataIndex: 'feedback_type',
      width: 80,
      render: (t: string) => <Space>{fbTypeIcon[t]} {fbTypeLabel[t]}</Space>,
    },
    { title: '问题', dataIndex: 'question', ellipsis: true },
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
  ]

  const logColumns = [
    {
      title: '延迟',
      dataIndex: 'latency_ms',
      width: 100,
      render: (ms: number) => {
        const color = ms < 2000 ? 'green' : ms < 5000 ? 'orange' : 'red'
        return <Tag color={color}>{ms} ms</Tag>
      },
    },
    { title: '问题', dataIndex: 'question', ellipsis: true },
    { title: '模型', dataIndex: 'model', width: 120 },
    { title: 'Token', dataIndex: 'token_total', width: 70 },
    { title: '召回', dataIndex: 'retrieval_count', width: 60 },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (t: string) => t?.slice(0, 19).replace('T', ' '),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={4}>评估与反馈</Title>

      {/* 综合统计 */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总反馈" value={stats.feedback.total} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="有用" value={stats.feedback.useful} prefix={<LikeOutlined />} valueStyle={{ color: '#52c41a' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="无用" value={stats.feedback.useless} prefix={<DislikeOutlined />} valueStyle={{ color: '#ff4d4f' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总查询" value={stats.query_log.total} prefix={<ThunderboltOutlined />} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic
                title="平均延迟"
                value={stats.query_log.avg_latency_ms?.toFixed(0) || 0}
                suffix="ms"
                prefix={<DashboardOutlined />}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic
                title="平均召回"
                value={stats.query_log.avg_retrieval_count?.toFixed(0) || 0}
                prefix={<DatabaseOutlined />}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 反馈记录 */}
      <Card
        size="small"
        title="反馈记录"
        style={{ marginBottom: 16 }}
        extra={
          <Space>
            <Text type="secondary">显示条数:</Text>
            <Slider
              min={10}
              max={200}
              value={fbLimit}
              onChange={setFbLimit}
              style={{ width: 120 }}
            />
          </Space>
        }
      >
        <Table
          dataSource={feedbacks}
          columns={fbColumns}
          rowKey="id"
          size="small"
          loading={loading}
          pagination={false}
          locale={{ emptyText: '暂无反馈记录' }}
        />
      </Card>

      {/* 查询日志 */}
      <Card
        size="small"
        title="查询日志"
        extra={
          <Space>
            <Text type="secondary">显示条数:</Text>
            <Slider
              min={10}
              max={200}
              value={logLimit}
              onChange={setLogLimit}
              style={{ width: 120 }}
            />
          </Space>
        }
      >
        <Table
          dataSource={logs}
          columns={logColumns}
          rowKey="id"
          size="small"
          loading={loading}
          pagination={false}
          locale={{ emptyText: '暂无查询日志' }}
        />
      </Card>
    </div>
  )
}
