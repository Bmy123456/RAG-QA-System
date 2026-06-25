import { useEffect, useState } from 'react'
import { List, Button, Typography, Popconfirm, Empty, Spin, message } from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  MessageOutlined,
  CheckCircleFilled,
} from '@ant-design/icons'
import { listSessions, deleteSession, getHistory } from '../api/chat'
import { useChatStore } from '../stores/chatStore'
import type { SessionInfo } from '../api/chat'

const { Text } = Typography

interface Props {
  kbId: number | null
}

export default function SessionList({ kbId }: Props) {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [loading, setLoading] = useState(false)
  const { sessionId, setSession, setMessages } = useChatStore()

  const load = async () => {
    setLoading(true)
    try {
      const data = await listSessions(kbId ?? undefined)
      setSessions(data)
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [kbId])

  const handleSelect = async (sid: string) => {
    try {
      const history = await getHistory(sid)
      setSession(sid)
      setMessages(
        history.messages.map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.metadata?.sources || [],
        }))
      )
    } catch {
      message.error('加载会话失败')
    }
  }

  const handleDelete = async (sid: string) => {
    try {
      await deleteSession(sid)
      if (sid === sessionId) {
        setSession(null)
        setMessages([])
      }
      load()
    } catch {
      message.error('删除失败')
    }
  }

  const handleNew = () => {
    setSession(null)
    setMessages([])
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '12px 16px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong style={{ fontSize: 13 }}>会话列表</Text>
        <Button size="small" icon={<PlusOutlined />} onClick={handleNew}>
          新建
        </Button>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '0 8px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin size="small" />
          </div>
        ) : sessions.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无会话"
            style={{ marginTop: 40 }}
          />
        ) : (
          <List
            size="small"
            dataSource={sessions}
            renderItem={(s) => (
              <List.Item
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  borderRadius: 6,
                  marginBottom: 2,
                  background:
                    s.session_id === sessionId
                      ? 'rgba(22,119,255,0.08)'
                      : 'transparent',
                  border:
                    s.session_id === sessionId
                      ? '1px solid rgba(22,119,255,0.2)'
                      : '1px solid transparent',
                }}
                onClick={() => handleSelect(s.session_id)}
                actions={[
                  <Popconfirm
                    key="del"
                    title="确定删除此会话？"
                    onConfirm={(e) => {
                      e?.stopPropagation()
                      handleDelete(s.session_id)
                    }}
                    onCancel={(e) => e?.stopPropagation()}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>,
                ]}
              >
                <List.Item.Meta
                  avatar={
                    s.session_id === sessionId ? (
                      <CheckCircleFilled style={{ color: '#1677ff', fontSize: 14 }} />
                    ) : (
                      <MessageOutlined style={{ color: '#999', fontSize: 14 }} />
                    )
                  }
                  title={
                    <Text
                      ellipsis
                      style={{
                        fontSize: 13,
                        fontWeight: s.session_id === sessionId ? 600 : 400,
                      }}
                    >
                      {s.title || '新会话'}
                    </Text>
                  }
                  description={
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {s.message_count} 条消息
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  )
}
