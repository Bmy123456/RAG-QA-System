import { useState } from 'react'
import { Button, Input, Space, message, Typography } from 'antd'
import {
  LikeOutlined,
  DislikeOutlined,
  EditOutlined,
  CheckOutlined,
} from '@ant-design/icons'
import { submitFeedback } from '../api/evaluation'
import { useChatStore } from '../stores/chatStore'

const { TextArea } = Input
const { Text } = Typography

interface Props {
  messageIndex: number
  feedbackType?: string
}

export default function FeedbackButtons({ messageIndex, feedbackType }: Props) {
  const { sessionId, messages, markFeedback } = useChatStore()
  const [expandType, setExpandType] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [correction, setCorrection] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (feedbackType) {
    const labels: Record<string, string> = {
      useful: '已标记有用',
      useless: '已标记无用',
      correction: '已提交纠正',
    }
    return (
      <Text type="secondary" style={{ fontSize: 12 }}>
        <CheckOutlined /> {labels[feedbackType] || '已反馈'}
      </Text>
    )
  }

  const findQuestion = (): string => {
    for (let i = messageIndex - 1; i >= 0; i--) {
      if (messages[i]?.role === 'user') return messages[i].content
    }
    return ''
  }

  const handleSubmit = async (type: string) => {
    setSubmitting(true)
    try {
      await submitFeedback({
        session_id: sessionId || '',
        message_index: messageIndex,
        feedback_type: type,
        reason: type === 'useless' ? reason : undefined,
        correction: type === 'correction' ? correction : undefined,
        question: findQuestion().slice(0, 500),
        answer: (messages[messageIndex]?.content || '').slice(0, 500),
      })
      markFeedback(messageIndex, type)
      message.success('感谢反馈！')
      setExpandType(null)
      setReason('')
      setCorrection('')
    } catch {
      message.error('提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <Space size={4}>
        <Button
          type="text"
          size="small"
          icon={<LikeOutlined />}
          onClick={() => handleSubmit('useful')}
          loading={submitting}
        >
          有用
        </Button>
        <Button
          type="text"
          size="small"
          icon={<DislikeOutlined />}
          onClick={() => setExpandType(expandType === 'useless' ? null : 'useless')}
        >
          无用
        </Button>
        <Button
          type="text"
          size="small"
          icon={<EditOutlined />}
          onClick={() => setExpandType(expandType === 'correction' ? null : 'correction')}
        >
          纠正
        </Button>
      </Space>

      {expandType === 'useless' && (
        <div style={{ marginTop: 8 }}>
          <TextArea
            rows={2}
            placeholder="请说明原因或指出错误…"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            style={{ fontSize: 13 }}
          />
          <Button
            size="small"
            type="primary"
            style={{ marginTop: 4 }}
            loading={submitting}
            disabled={!reason.trim()}
            onClick={() => handleSubmit('useless')}
          >
            提交
          </Button>
        </div>
      )}

      {expandType === 'correction' && (
        <div style={{ marginTop: 8 }}>
          <TextArea
            rows={3}
            placeholder="请输入您认为正确的回答…"
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            style={{ fontSize: 13 }}
          />
          <Button
            size="small"
            type="primary"
            style={{ marginTop: 4 }}
            loading={submitting}
            disabled={!correction.trim()}
            onClick={() => handleSubmit('correction')}
          >
            提交纠正
          </Button>
        </div>
      )}
    </div>
  )
}
