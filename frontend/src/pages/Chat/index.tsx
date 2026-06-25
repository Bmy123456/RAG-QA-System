import { useEffect, useState, useCallback, useRef } from 'react'
import { Layout, Select, Typography, Divider, message, Spin, Empty } from 'antd'
import { DatabaseOutlined } from '@ant-design/icons'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import SessionList from '../../components/SessionList'
import { useChatStore } from '../../stores/chatStore'
import { listKbs } from '../../api/knowledgeBase'
import { streamChat } from '../../api/chat'
import type { KnowledgeBase } from '../../api/knowledgeBase'

const { Sider, Content } = Layout
const { Text } = Typography

export default function ChatPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [loadingKbs, setLoadingKbs] = useState(true)
  const abortRef = useRef<AbortController | null>(null)

  const {
    kbId, kbName, sessionId, messages,
    streaming, streamingAnswer, streamingSources,
    setKb, addMessage, startStream, appendToken,
    setSources, finishStream, cancelStream, setSession,
  } = useChatStore()

  useEffect(() => {
    const load = async () => {
      try {
        const data = await listKbs()
        setKbs(data)
        // 如果没有选中知识库且有可用的，自动选第一个
        if (!kbId && data.length > 0) {
          setKb(data[0].id, data[0].name)
        }
      } catch {
        /* ignore */
      } finally {
        setLoadingKbs(false)
      }
    }
    load()
  }, [])

  const handleKbChange = (value: number) => {
    const kb = kbs.find((k) => k.id === value)
    if (kb) setKb(kb.id, kb.name)
  }

  const handleSend = useCallback(
    async (text: string) => {
      addMessage({ role: 'user', content: text })
      startStream()

      await streamChat(
        {
          question: text,
          kb_id: kbId,
          session_id: sessionId,
          strategy: 'hybrid',
        },
        (token) => appendToken(token),
        (sources) => setSources(sources),
        (sid) => {
          if (!sessionId) setSession(sid)
        },
        () => finishStream(),
        (err) => {
          message.error(`对话出错: ${err.message}`)
          cancelStream()
        }
      )
    },
    [kbId, sessionId, addMessage, startStream, appendToken, setSources, finishStream, cancelStream, setSession]
  )

  const handleCancel = () => {
    abortRef.current?.abort()
    cancelStream()
  }

  return (
    <Layout style={{ height: 'calc(100vh - 56px)' }}>
      {/* 左侧边栏 */}
      <Sider
        width={280}
        style={{
          background: '#fafafa',
          borderRight: '1px solid #f0f0f0',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* 知识库选择 */}
        <div style={{ padding: '16px 16px 8px' }}>
          <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 8 }}>
            <DatabaseOutlined /> 知识库
          </Text>
          {loadingKbs ? (
            <Spin size="small" />
          ) : kbs.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无知识库"
              style={{ margin: 0 }}
            />
          ) : (
            <Select
              value={kbId}
              onChange={handleKbChange}
              style={{ width: '100%' }}
              placeholder="选择知识库"
              options={kbs.map((kb) => ({
                value: kb.id,
                label: `${kb.name}（${kb.doc_count} 篇）`,
              }))}
            />
          )}
        </div>

        <Divider style={{ margin: '8px 0' }} />

        {/* 会话列表 */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <SessionList kbId={kbId} />
        </div>
      </Sider>

      {/* 右侧对话区 */}
      <Content style={{ display: 'flex', flexDirection: 'column', background: '#fff' }}>
        {/* 顶部信息栏 */}
        <div
          style={{
            padding: '12px 24px',
            borderBottom: '1px solid #f0f0f0',
            background: '#fafafa',
          }}
        >
          <Text strong>{kbName || '未选择知识库'}</Text>
          {sessionId && (
            <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
              会话: {sessionId.slice(0, 8)}…
            </Text>
          )}
        </div>

        {/* 消息列表 */}
        <MessageList
          messages={messages}
          streamingAnswer={streamingAnswer}
          streamingSources={streamingSources}
          streaming={streaming}
        />

        {/* 输入框 */}
        <ChatInput
          onSend={handleSend}
          onCancel={handleCancel}
          streaming={streaming}
          disabled={!kbId}
        />
      </Content>
    </Layout>
  )
}
