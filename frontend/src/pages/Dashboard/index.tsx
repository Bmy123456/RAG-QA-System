import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Table, Tag, Typography, Spin, Badge, Space, theme } from 'antd'
import {
  ThunderboltOutlined,
  LikeOutlined,
  DislikeOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  AlertOutlined,
  FireOutlined,
} from '@ant-design/icons'
import { Column, Line, Pie } from '@ant-design/charts'
import {
  getDashboardOverview,
  getLatencyBreakdown,
  getErrorRate,
  getFeedbackTrend,
  getFeedbackTopDocs,
  getTokenUsage,
  getAlerts,
  getHttpOverview,
} from '../../api/admin'
import type {
  DashboardOverview,
  LatencyBreakdown,
  HourlyMetric,
  TokenUsage,
  DislikedDoc,
  Alert,
  HttpOverview,
} from '../../api/admin'

const { Title, Text } = Typography

export default function DashboardPage() {
  const { token } = theme.useToken()
  const [loading, setLoading] = useState(true)
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [latency, setLatency] = useState<LatencyBreakdown | null>(null)
  const [errorRate, setErrorRate] = useState<HourlyMetric[]>([])
  const [feedbackTrend, setFeedbackTrend] = useState<HourlyMetric[]>([])
  const [topDocs, setTopDocs] = useState<DislikedDoc[]>([])
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [httpOverview, setHttpOverview] = useState<HttpOverview | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [ov, lat, err, fb, td, tu, al, http] = await Promise.all([
          getDashboardOverview().catch(() => null),
          getLatencyBreakdown().catch(() => null),
          getErrorRate().catch(() => []),
          getFeedbackTrend().catch(() => []),
          getFeedbackTopDocs().catch(() => []),
          getTokenUsage().catch(() => []),
          getAlerts().catch(() => []),
          getHttpOverview().catch(() => null),
        ])
        setOverview(ov)
        setLatency(lat)
        setErrorRate(err)
        setFeedbackTrend(fb)
        setTopDocs(td)
        setTokenUsage(tu)
        setAlerts(al)
        setHttpOverview(http)
      } finally {
        setLoading(false)
      }
    }
    load()
    const timer = setInterval(load, 60000) // 每分钟刷新
    return () => clearInterval(timer)
  }, [])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <Spin size="large" tip="加载中…" />
      </div>
    )
  }

  // 延迟瀑布图数据
  const waterfallData = latency
    ? [
        { stage: '检索', type: '平均', value: latency.retrieval.avg_ms },
        { stage: '检索', type: 'P95', value: latency.retrieval.p95_ms },
        { stage: '重排序', type: '平均', value: latency.rerank.avg_ms },
        { stage: '重排序', type: 'P95', value: latency.rerank.p95_ms },
        { stage: 'LLM 生成', type: '平均', value: latency.generation.avg_ms },
        { stage: 'LLM 生成', type: 'P95', value: latency.generation.p95_ms },
      ]
    : []

  // 错误率曲线数据
  const errorLineData = errorRate.map((d) => ({
    hour: d.hour?.slice(11, 16) || '',
    错误率: (d.error_rate || 0) * 100,
    请求数: d.count || 0,
  }))

  // 反馈趋势数据
  const feedbackLineData = feedbackTrend.flatMap((d) => [
    { hour: d.hour?.slice(11, 16) || '', 类型: '点赞', 数量: d.useful || 0 },
    { hour: d.hour?.slice(11, 16) || '', 类型: '点踩', 数量: d.useless || 0 },
  ])

  // Token 消耗饼图
  const tokenPieData = tokenUsage.map((d) => ({
    type: d.model || '未知',
    value: d.total_tokens,
  }))

  return (
    <div style={{ padding: 24, background: token.colorBgLayout, minHeight: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>系统监控仪表盘</Title>
        <Badge count={alerts.length} offset={[-8, 0]}>
          <Tag icon={<AlertOutlined />} color={alerts.length > 0 ? 'warning' : 'success'}>
            {alerts.length > 0 ? `${alerts.length} 条告警` : '系统正常'}
          </Tag>
        </Badge>
      </div>

      {/* ===== 第一行：服务质量概览 ===== */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="今日问答总量"
              value={overview?.today_query_count || 0}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: token.colorPrimary }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="平均端到端延迟"
              value={overview?.avg_latency_ms || 0}
              suffix="ms"
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: (overview?.avg_latency_ms || 0) > 5000 ? token.colorError : token.colorSuccess }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="P95 延迟"
              value={overview?.p95_latency_ms || 0}
              suffix="ms"
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: (overview?.p95_latency_ms || 0) > 10000 ? token.colorError : token.colorWarning }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="用户满意度"
              value={((overview?.satisfaction_rate || 0) * 100).toFixed(1)}
              suffix="%"
              prefix={<LikeOutlined />}
              valueStyle={{ color: (overview?.satisfaction_rate || 0) > 0.7 ? token.colorSuccess : token.colorError }}
            />
          </Card>
        </Col>
      </Row>

      {/* ===== 第二行：延迟瀑布 + 错误率 ===== */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card size="small" title="核心链路延迟分解">
            {waterfallData.length > 0 ? (
              <Column
                data={waterfallData}
                xField="stage"
                yField="value"
                colorField="type"
                group={{ groupBy: 'x' }}
                style={{ height: 260 }}
                axis={{
                  x: { title: false },
                  y: { title: false, labelFormatter: (v: number) => `${v}ms` },
                }}
                legend={{ position: 'top' }}
              />
            ) : (
              <Text type="secondary">暂无数据</Text>
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="错误率趋势（按小时）">
            {errorLineData.length > 0 ? (
              <Line
                data={errorLineData}
                xField="hour"
                yField="错误率"
                style={{ height: 260 }}
                axis={{
                  x: { title: false },
                  y: { title: false, labelFormatter: (v: number) => `${v}%` },
                }}
                point={{ size: 2 }}
                color={() => token.colorError}
              />
            ) : (
              <Text type="secondary">暂无数据</Text>
            )}
          </Card>
        </Col>
      </Row>

      {/* ===== 第三行：反馈趋势 + Token 消耗 ===== */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card size="small" title="用户反馈趋势">
            {feedbackLineData.length > 0 ? (
              <Line
                data={feedbackLineData}
                xField="hour"
                yField="数量"
                colorField="类型"
                style={{ height: 260 }}
                axis={{ x: { title: false }, y: { title: false } }}
                point={{ size: 2 }}
                color={['#52c41a', '#ff4d4f']}
              />
            ) : (
              <Text type="secondary">暂无数据</Text>
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="Token 消耗（按模型）">
            {tokenPieData.length > 0 ? (
              <Pie
                data={tokenPieData}
                angleField="value"
                colorField="type"
                style={{ height: 260 }}
                innerRadius={0.5}
                label={{
                  text: (d: { type: string }) => d.type,
                  position: 'outside',
                }}
                legend={{ position: 'bottom' }}
              />
            ) : (
              <Text type="secondary">暂无数据</Text>
            )}
          </Card>
        </Col>
      </Row>

      {/* ===== 第四行：点踩文档 Top + 告警 ===== */}
      <Row gutter={16}>
        <Col span={12}>
          <Card size="small" title="高频点踩文档 Top 5">
            <Table
              dataSource={topDocs}
              rowKey="kb_id"
              size="small"
              pagination={false}
              columns={[
                {
                  title: '知识库',
                  dataIndex: 'kb_name',
                  render: (name: string) => <Text strong>{name}</Text>,
                },
                {
                  title: '点踩次数',
                  dataIndex: 'dislike_count',
                  width: 100,
                  render: (n: number) => (
                    <Tag color="red" icon={<DislikeOutlined />}>
                      {n}
                    </Tag>
                  ),
                },
              ]}
              locale={{ emptyText: '暂无点踩数据' }}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card
            size="small"
            title={
              <Space>
                <WarningOutlined style={{ color: alerts.length > 0 ? '#faad14' : '#52c41a' }} />
                实时告警
              </Space>
            }
          >
            {alerts.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <CheckCircleOutlined style={{ fontSize: 32, color: '#52c41a' }} />
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">系统运行正常，无告警</Text>
                </div>
              </div>
            ) : (
              <Table
                dataSource={alerts}
                rowKey={(a, i) => `${a.timestamp}-${i}`}
                size="small"
                pagination={false}
                columns={[
                  {
                    title: '级别',
                    dataIndex: 'level',
                    width: 80,
                    render: (level: string) => (
                      <Tag color={level === 'warning' ? 'orange' : 'blue'} icon={<FireOutlined />}>
                        {level === 'warning' ? '警告' : '信息'}
                      </Tag>
                    ),
                  },
                  {
                    title: '告警信息',
                    dataIndex: 'message',
                  },
                  {
                    title: '时间',
                    dataIndex: 'timestamp',
                    width: 160,
                    render: (t: string) => t?.slice(0, 19).replace('T', ' '),
                  },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* HTTP 请求级指标 */}
      {httpOverview && httpOverview.total_requests > 0 && (
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card size="small" title="HTTP 请求指标（24h）">
              <Row gutter={16}>
                <Col span={4}>
                  <Statistic title="总请求数" value={httpOverview.total_requests} />
                </Col>
                <Col span={4}>
                  <Statistic title="QPS" value={httpOverview.qps} precision={2} />
                </Col>
                <Col span={4}>
                  <Statistic
                    title="5xx 错误率"
                    value={(httpOverview.error_5xx_rate * 100).toFixed(2)}
                    suffix="%"
                    valueStyle={{ color: httpOverview.error_5xx_rate > 0.01 ? '#ff4d4f' : '#52c41a' }}
                  />
                </Col>
                <Col span={4}>
                  <Statistic title="P50 延迟" value={httpOverview.p50_latency_ms} suffix="ms" />
                </Col>
                <Col span={4}>
                  <Statistic title="P95 延迟" value={httpOverview.p95_latency_ms} suffix="ms" />
                </Col>
                <Col span={4}>
                  <Statistic title="P99 延迟" value={httpOverview.p99_latency_ms} suffix="ms" />
                </Col>
              </Row>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  )
}
