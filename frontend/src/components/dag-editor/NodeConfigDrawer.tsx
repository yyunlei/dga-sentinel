import { useState, useEffect } from 'react';
import { Drawer, Form, Input, InputNumber, Switch, Select, Button, Space, message, Spin } from 'antd';
import { nodeConfigAPI } from '@/services/api';
import type { NodeConfigSchema } from '@/services/api';

interface NodeConfigDrawerProps {
  open: boolean;
  onClose: () => void;
  nodeType: string | null;
  editId?: number | null;
  onSaved?: () => void;
}

export default function NodeConfigDrawer({ open, onClose, nodeType, editId, onSaved }: NodeConfigDrawerProps) {
  const [form] = Form.useForm();
  const [schema, setSchema] = useState<NodeConfigSchema | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !nodeType) return;
    setLoading(true);
    nodeConfigAPI.schema(nodeType)
      .then((s) => {
        setSchema(s);
        // Set defaults
        const defaults: Record<string, unknown> = {};
        s.fields.forEach((f) => { if (f.default !== undefined) defaults[f.key] = f.default; });
        if (!editId) form.setFieldsValue({ name: '', description: '', ...defaults });
      })
      .catch(() => setSchema(null))
      .finally(() => setLoading(false));

    if (editId) {
      nodeConfigAPI.get(editId).then((cfg) => {
        form.setFieldsValue({ name: cfg.name, description: cfg.description, ...cfg.config });
      });
    }
  }, [open, nodeType, editId, form]);
  useEffect(() => {
    if (!open) { form.resetFields(); setSchema(null); }
  }, [open, form]);

  async function handleSave() {
    if (!nodeType || !schema) return;
    try {
      const values = await form.validateFields();
      const { name, description, ...config } = values;
      setSaving(true);
      if (editId) {
        await nodeConfigAPI.update(editId, { name, description, config });
        message.success('配置已更新');
      } else {
        await nodeConfigAPI.create({ node_type: nodeType, name, description, config });
        message.success('配置已创建');
      }
      onSaved?.();
      onClose();
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  }

  function renderField(field: NodeConfigSchema['fields'][0]) {
    switch (field.type) {
      case 'number': return <InputNumber style={{ width: '100%' }} />;
      case 'boolean': return <Switch />;
      case 'enum': return <Select options={(field.options || []).map((o) => ({ label: o, value: o }))} />;
      case 'array': return <Select mode="tags" style={{ width: '100%' }} />;
      default: return <Input />;
    }
  }

  return (
    <Drawer
      title={`${editId ? '编辑' : '新建'}节点配置 — ${nodeType || ''}`}
      open={open}
      onClose={onClose}
      width={480}
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
        </Space>
      }
    >
      {loading ? <Spin /> : (
        <Form form={form} layout="vertical" size="small">
          <Form.Item name="name" label="配置名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如: production-kafka" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          {schema?.fields.map((f) => (
            <Form.Item
              key={f.key}
              name={f.key}
              label={f.label || f.key}
              rules={f.required ? [{ required: true, message: `请填写 ${f.label}` }] : []}
              valuePropName={f.type === 'boolean' ? 'checked' : 'value'}
            >
              {renderField(f)}
            </Form.Item>
          ))}
        </Form>
      )}
    </Drawer>
  );
}
