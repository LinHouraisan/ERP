import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Input, Select, Table } from 'antd';
import { api } from '../../lib/api';
import { label } from '../../lib/display';
import { QualityReview, type Quality } from './QualityReview';
export function QualityPage() {
  const cache = useQueryClient();
  const [pid, setPid] = useState<string>(), [qid, setQid] = useState<string | undefined>(new URLSearchParams(location.search).get('id') || undefined);
  const products = useQuery({ queryKey: ['products'], queryFn: () => api<{ items: { id: string; name: string }[] }>('/products') });
  const policies = useQuery({ queryKey: ['policies', pid], queryFn: () => api<{ items: { id: string; version: number; status: string }[] }>(`/products/${pid}/policy-versions`), enabled: !!pid });
  const checks = useQuery({ queryKey: ['qualities'], queryFn: () => api<{ items: Quality[] }>('/quality-checks') });
  const create = useMutation({ mutationFn: (body: object) => api<Quality>('/quality-checks', body), onSuccess: q => { setQid(q.quality_check_id); void cache.invalidateQueries({ queryKey: ['qualities'] }); } });
  const error = products.error || policies.error || checks.error || create.error;
  return <div className="stack">{error && <Alert title={error.message} type="error" />}
    <Card title="营销文案与客户答复质检"><Form layout="vertical" initialValues={{ target_type: 'MARKETING', policy_version_ids: [] }} onFinish={create.mutate}>
      <Form.Item label="文本类别" name="target_type"><Select options={[{ value: 'MARKETING', label: '营销文案' }, { value: 'REPLY', label: '客户答复' }]} /></Form.Item>
      <Form.Item label="查询政策所属产品"><Select aria-label="查询政策所属产品" showSearch optionFilterProp="label" value={pid} onChange={setPid} options={products.data?.items.map(p => ({ value: p.id, label: p.name }))} /></Form.Item>
      <Form.Item label="政策版本依据" name="policy_version_ids"><Select mode="multiple" options={policies.data?.items.map(p => ({ value: p.id, label: `V${p.version} · ${label(p.status)}` }))} /></Form.Item>
      <Form.Item label="待检查正文" name="text" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={5} maxLength={12000} /></Form.Item><Button htmlType="submit" type="primary" loading={create.isPending}>执行文本质检</Button>
    </Form></Card>
    {qid && <Card title="质检详情与人工复核"><QualityReview key={qid} id={qid} onRevision={setQid} /></Card>}
    <Card title="质检历史"><Table rowKey="quality_check_id" dataSource={checks.data?.items} columns={[{ title: '类别', dataIndex: 'target_type' }, { title: '状态', dataIndex: 'status', render: label }, { title: '正文', dataIndex: 'text', ellipsis: true }, { title: '查看', render: (_, q) => <Button onClick={() => setQid(q.quality_check_id)}>查看质检记录</Button> }]} /></Card>
  </div>;
}
