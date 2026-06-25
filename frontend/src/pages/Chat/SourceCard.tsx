import { Typography, Tag } from 'antd'
import { FileTextOutlined } from '@ant-design/icons'
import type { Source } from '../../api/chat'

const { Text, Paragraph } = Typography

interface Props {
  source: Source
}

export default function SourceCard({ source }: Props) {
  return (
    <div
      style={{
        padding: '8px 12px',
        borderRadius: 6,
        background: '#fafafa',
        border: '1px solid #f0f0f0',
        marginBottom: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Tag color="blue" style={{ margin: 0 }}>
          [{source.index}]
        </Tag>
        <FileTextOutlined style={{ color: '#999' }} />
        <Text ellipsis style={{ flex: 1, fontSize: 13 }}>
          {source.filename}
        </Text>
        {source.page != null && (
          <Text type="secondary" style={{ fontSize: 12, flexShrink: 0 }}>
            第{source.page}页
          </Text>
        )}
      </div>
      {source.snippet && (
        <Paragraph
          type="secondary"
          ellipsis={{ rows: 2, expandable: true }}
          style={{ fontSize: 12, marginBottom: 0 }}
        >
          {source.snippet}
        </Paragraph>
      )}
    </div>
  )
}
