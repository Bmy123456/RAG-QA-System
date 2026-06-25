import { useState, useRef, useEffect } from 'react'
import { Input, Button, Tooltip } from 'antd'
import { SendOutlined, StopOutlined } from '@ant-design/icons'

const { TextArea } = Input

interface Props {
  onSend: (text: string) => void
  onCancel: () => void
  streaming: boolean
  disabled?: boolean
}

export default function ChatInput({ onSend, onCancel, streaming, disabled }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<any>(null)

  useEffect(() => {
    if (!streaming) ref.current?.focus?.()
  }, [streaming])

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || streaming) return
    onSend(trimmed)
    setText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      style={{
        padding: '16px 24px',
        borderTop: '1px solid #f0f0f0',
        background: '#fff',
      }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <TextArea
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的问题…（Shift+Enter 换行）"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={streaming || disabled}
          style={{ flex: 1 }}
        />
        {streaming ? (
          <Tooltip title="停止生成">
            <Button
              danger
              icon={<StopOutlined />}
              onClick={onCancel}
              style={{ height: 40, width: 40 }}
            />
          </Tooltip>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!text.trim() || disabled}
            style={{ height: 40, width: 40 }}
          />
        )}
      </div>
    </div>
  )
}
