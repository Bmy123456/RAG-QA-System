import { useState } from 'react'
import { Avatar, Typography, Collapse, Badge, theme } from 'antd'
import { UserOutlined, RobotOutlined, PaperClipOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import SourceCard from './SourceCard'
import FeedbackButtons from '../../components/FeedbackButtons'
import type { Message } from '../../stores/chatStore'

const { Text } = Typography

interface Props {
  message: Message
  index: number
  isStreaming?: boolean
}

export default function MessageBubble({ message, index, isStreaming }: Props) {
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const { token } = theme.useToken()

  const isUser = message.role === 'user'
  const sources = message.sources || []

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 16,
        gap: 8,
      }}
    >
      {!isUser && (
        <Avatar
          size={32}
          icon={<RobotOutlined />}
          style={{ background: token.colorPrimary, flexShrink: 0 }}
        />
      )}

      <div style={{ maxWidth: '75%', minWidth: 120 }}>
        {/* 消息气泡 */}
        <div
          style={{
            padding: '10px 14px',
            borderRadius: 10,
            background: isUser ? token.colorPrimary : token.colorBgContainer,
            color: isUser ? '#fff' : token.colorText,
            border: isUser ? 'none' : `1px solid ${token.colorBorderSecondary}`,
            fontSize: 14,
            lineHeight: 1.7,
            wordBreak: 'break-word',
          }}
        >
          {isUser ? (
            message.content
          ) : (
            <div className="markdown-body">
              <ReactMarkdown>{message.content}</ReactMarkdown>
              {isStreaming && <span style={{ opacity: 0.5 }}>▌</span>}
            </div>
          )}
        </div>

        {/* 引用来源 */}
        {!isUser && sources.length > 0 && (
          <Collapse
            ghost
            activeKey={sourcesOpen ? ['sources'] : []}
            onChange={(keys) => setSourcesOpen(keys.includes('sources'))}
            style={{ marginTop: 4 }}
            items={[
              {
                key: 'sources',
                label: (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <PaperClipOutlined /> {sources.length} 篇引用来源
                  </Text>
                ),
                children: (
                  <div style={{ padding: '0 4px' }}>
                    {sources.map((src, i) => (
                      <SourceCard key={i} source={src} />
                    ))}
                  </div>
                ),
              },
            ]}
          />
        )}

        {/* 反馈按钮 */}
        {!isUser && !isStreaming && (
          <div style={{ marginTop: 4 }}>
            <FeedbackButtons messageIndex={index} feedbackType={message.feedbackType} />
          </div>
        )}
      </div>

      {isUser && (
        <Avatar
          size={32}
          icon={<UserOutlined />}
          style={{ background: '#87d068', flexShrink: 0 }}
        />
      )}
    </div>
  )
}
