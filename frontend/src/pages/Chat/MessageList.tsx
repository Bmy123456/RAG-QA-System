import { useEffect, useRef } from 'react'
import { Empty, Typography } from 'antd'
import { MessageOutlined } from '@ant-design/icons'
import MessageBubble from './MessageBubble'
import type { Message } from '../../stores/chatStore'

const { Text } = Typography

interface Props {
  messages: Message[]
  streamingAnswer: string
  streamingSources: import('../../api/chat').Source[]
  streaming: boolean
}

export default function MessageList({ messages, streamingAnswer, streamingSources, streaming }: Props) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingAnswer])

  if (messages.length === 0 && !streaming) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Empty
          image={<MessageOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />}
          description={
            <Text type="secondary">选择知识库，输入问题开始对话</Text>
          }
        />
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: '24px' }}>
      {messages.map((msg, i) => (
        <MessageBubble key={i} message={msg} index={i} />
      ))}

      {/* 流式输出中的消息 */}
      {streaming && (
        <MessageBubble
          message={{
            role: 'assistant',
            content: streamingAnswer,
            sources: streamingSources,
          }}
          index={messages.length}
          isStreaming
        />
      )}

      <div ref={endRef} />
    </div>
  )
}
