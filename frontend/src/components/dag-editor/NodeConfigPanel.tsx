import { useEffect } from 'react';
import { Form, Input, InputNumber, Switch, Select, Typography, Empty } from 'antd';
import type { Node } from '@xyflow/react';

const { Text } = Typography;

interface FieldSchema {
  key: string;
  type: 'string' | 'number' | 'boolean' | 'enum';
  label?: string;
  options?: string[];
  defaultValue?: unknown;
}

interface NodeConfigPanelProps {
  node: Node | null;
  onConfigChange: (nodeId: string, config: Record<string, unknown>) => void;
}

/** Derive basic field schemas from existing config values. */
function deriveFields(config: Record<string, unknown>): FieldSchema[] {
  return Object.entries(config).map(([key, value]) => {
    if (typeof value === 'boolean') return { key, type: 'boolean' as const };
    if (typeof value === 'number') return { key, type: 'number' as const };
    if (Array.isArray(value)) return { key, type: 'enum' as const, options: value.map(String) };
    return { key, type: 'string' as const };
  });
}

function renderField(field: FieldSchema) {
  switch (field.type) {
    case 'number':
      return <InputNumber style={{ width: '100%' }} />;
    case 'boolean':
      return <Switch />;
    case 'enum':
      return (
        <Select options={(field.options || []).map((o) => ({ label: o, value: o }))} />
      );
    default:
      return <Input />;
  }
}

export default function NodeConfigPanel({ node, onConfigChange }: NodeConfigPanelProps) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (node) {
      const config = (node.data?.config as Record<string, unknown>) || {};
      form.setFieldsValue(config);
    } else {
      form.resetFields();
    }
  }, [node, form]);

  if (!node) {
    return (
      <div style={{ width: 280, padding: 24, textAlign: 'center' }}>
        <Empty description="Select a node to configure" />
      </div>
    );
  }

  const config = (node.data?.config as Record<string, unknown>) || {};
  const fields = deriveFields(config);

  const handleValuesChange = (_: unknown, allValues: Record<string, unknown>) => {
    onConfigChange(node.id, allValues);
  };

  return (
    <div style={{ width: 280, padding: 16, overflowY: 'auto' }}>
      <Text strong style={{ display: 'block', marginBottom: 4 }}>
        {node.data?.label as string}
      </Text>
      <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
        ID: {node.id} | Type: {node.data?.nodeType as string}
      </Text>
      <Form
        form={form}
        layout="vertical"
        size="small"
        onValuesChange={handleValuesChange}
        initialValues={config}
      >
        {fields.map((field) => (
          <Form.Item
            key={field.key}
            name={field.key}
            label={field.label || field.key}
            valuePropName={field.type === 'boolean' ? 'checked' : 'value'}
          >
            {renderField(field)}
          </Form.Item>
        ))}
        {fields.length === 0 && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            No configurable fields
          </Text>
        )}
      </Form>
    </div>
  );
}
