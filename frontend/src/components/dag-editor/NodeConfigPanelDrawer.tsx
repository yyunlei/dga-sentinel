import { useEffect, useCallback } from 'react';
import { Drawer, Form, Input, InputNumber, Switch, Select, Button, Space, Empty } from 'antd';
import type { Node } from '@xyflow/react';
import { getSchemaForNode, type NodeConfigFieldSchema } from './nodeConfigSchemas';

interface NodeConfigPanelDrawerProps {
  node: Node | null;
  open: boolean;
  onClose: () => void;
  onConfigChange: (nodeId: string, config: Record<string, unknown>) => void;
}

function renderField(field: NodeConfigFieldSchema) {
  switch (field.type) {
    case 'number':
      return <InputNumber style={{ width: '100%' }} placeholder={field.placeholder} />;
    case 'boolean':
      return <Switch />;
    case 'enum':
      return (
        <Select
          allowClear
          placeholder={field.placeholder}
          options={field.options}
          style={{ width: '100%' }}
        />
      );
    case 'array':
      return (
        <Select
          mode="tags"
          style={{ width: '100%' }}
          placeholder={field.placeholder || '输入后回车添加'}
          tokenSeparators={[',', ' ']}
        />
      );
    default:
      return <Input placeholder={field.placeholder} />;
  }
}

export default function NodeConfigPanelDrawer({
  node,
  open,
  onClose,
  onConfigChange,
}: NodeConfigPanelDrawerProps) {
  const [form] = Form.useForm();
  const subType = (node?.data?.subType as string) || '';
  const schema = getSchemaForNode(subType);

  useEffect(() => {
    if (open && node && schema) {
      const config = (node.data?.config as Record<string, unknown>) || {};
      const withDefaults: Record<string, unknown> = {};
      for (const f of schema.fields) {
        if (config[f.key] !== undefined && config[f.key] !== '') {
          withDefaults[f.key] = config[f.key];
        } else if (f.default !== undefined) {
          withDefaults[f.key] = f.default;
        }
      }
      Object.assign(withDefaults, config);
      form.setFieldsValue(withDefaults);
    } else if (!open) {
      form.resetFields();
    }
  }, [open, node, schema, form]);

  const handleSave = useCallback(() => {
    if (!node) return;
    form.validateFields().then((values) => {
      onConfigChange(node.id, values);
      onClose();
    });
  }, [node, form, onConfigChange, onClose]);

  if (!node) return null;

  return (
    <Drawer
      title={`节点配置 — ${subType || node.data?.label || '未命名'}`}
      open={open}
      onClose={onClose}
      width={480}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
    >
      {schema ? (
        <Form form={form} layout="vertical" size="small">
          {schema.fields.map((field) => (
            <Form.Item
              key={field.key}
              name={field.key}
              label={field.label}
              rules={field.required ? [{ required: true, message: `请填写 ${field.label}` }] : []}
              valuePropName={field.type === 'boolean' ? 'checked' : 'value'}
            >
              {renderField(field)}
            </Form.Item>
          ))}
        </Form>
      ) : (
        <Empty description={`暂无「${subType}」类型的专业配置项，可在配置管理中维护。`} />
      )}
    </Drawer>
  );
}
