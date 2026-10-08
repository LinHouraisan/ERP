import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Form, Input, Select, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../lib/api';
import { date } from '../../lib/display';
type Metric = { label: string; value: string; unit: string; definition: string; evidence_ids: string[]; page: string };
type Snapshot = { id: string; filters: { from: string; to: string; store_name: string; as_of: string }; metrics: Record<string, Metric> };
type Geo = { id: string; platform: string; question: string; answer: string; brand: string; captured_at: string; simulated: boolean; mentioned: boolean; citations: string[]; factual_errors: string };
type Summary = { status: string; error: string | null; output: { items: { metric_id: string; value: string; explanation: string; evidence_ids: string[] }[] } | null };

export function OperationsPage() {
  const cache = useQueryClient(), [filter, setFilter] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [batchKey, setBatchKey] = useState(() => crypto.randomUUID());
  const snapshot = useQuery({ queryKey: ['operations', filter], queryFn: () => api<Snapshot>(`/operations/overview${filter}`), staleTime: Infinity });
  const geo = useQuery({ queryKey: ['geo-samples'], queryFn: () => api<{ items: Geo[]; sample_counts: Record<string, { sample_count: number; mentioned_count: number }>; definition: string }>('/operations/geo-samples') });
  const summary = useMutation({ mutationFn: (v: object) => api<Summary>('/operations/summary', { ...v, snapshot_id: snapshot.data!.id, request_key: crypto.randomUUID() }) });
  const add = useMutation({ mutationFn: (v: { platform: string; question: string; answer: string; brand: string; captured_at: string; simulated: boolean; citations?: string; factual_errors?: string }) => api('/operations/geo-samples', { request_key: key, samples: [{ ...v, captured_at: v.captured_at+'+08:00', factual_errors: v.factual_errors || '', citations: v.citations?.trim().split(/\s+/).filter(Boolean) || [] }] }), onSuccess: async () => { setKey(crypto.randomUUID()); await cache.invalidateQueries({ queryKey: ['geo-samples'] }); } });
  const batch = useMutation({ mutationFn: async (file: File) => api('/operations/geo-samples', { request_key: batchKey, samples: JSON.parse(await file.text()) }), onSuccess: () => { setBatchKey(crypto.randomUUID()); return cache.invalidateQueries({ queryKey: ['geo-samples'] }); } });
  const error = snapshot.error || geo.error || summary.error || add.error || batch.error;
  return <div className="stack">{error && <Alert type="error" title={error.message} />}
    <Card title="经营看板" extra={<Button loading={snapshot.isFetching} onClick={() => { summary.reset(); void snapshot.refetch(); }}>生成新统计快照</Button>}>
      <Form layout="inline" onFinish={v => { const query = new URLSearchParams(); if (v.start) query.set('start', v.start+'+08:00'); if (v.end) query.set('end', v.end+'+08:00'); setFilter('?'+query.toString()); summary.reset(); }}><Form.Item name="start" label="开始（上海）"><Input type="datetime-local" /></Form.Item><Form.Item name="end" label="结束（不含）"><Input type="datetime-local" /></Form.Item><Button htmlType="submit">按范围统计</Button></Form>
      {snapshot.data && <><Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>{snapshot.data.filters.store_name} · {date(snapshot.data.filters.from)} 至 {date(snapshot.data.filters.to)} · 更新于 {date(snapshot.data.filters.as_of)}</Typography.Paragraph>
        <Table rowKey="key" dataSource={Object.entries(snapshot.data.metrics).map(([key, m]) => ({ key, ...m }))} pagination={false} expandable={{ expandedRowRender: m => m.evidence_ids.length ? <Space wrap>{m.evidence_ids.map(id => <a key={id} href={`/${m.page}?id=${id}`}>来源 {id.slice(0,8)}</a>)}</Space> : '此指标没有明细样本' }} columns={[{ title: '指标', dataIndex: 'label' }, { title: '数值', render: (_, m) => <strong>{m.value} {m.unit}</strong> }, { title: '口径', dataIndex: 'definition' }, { title: '依据数量', render: (_, m) => m.evidence_ids.length }]} />
      </>}
    </Card>
    <Card title="经营问答与摘要草稿"><Form layout="vertical" initialValues={{ question: '概括本期经营情况，列出需要核查的事项。' }} onFinish={summary.mutate}><Form.Item name="question" label="关注的问题"><Input.TextArea /></Form.Item><Button htmlType="submit" disabled={!snapshot.data} loading={summary.isPending}>基于当前快照生成摘要</Button></Form>
      {summary.data && (summary.data.status === 'SUCCEEDED' && summary.data.output ? <><Alert type="info" title="摘要为辅助草稿；数字及引用已与快照核对，原因解释仍需人工确认。" />{summary.data.output.items.map(m => <p key={m.metric_id}><strong>{snapshot.data?.metrics[m.metric_id]?.label}：{m.value}</strong> — {m.explanation}</p>)}</> : <Alert type="warning" title={summary.data.error || '辅助尚未完成，仍可查看统计表'} />)}
      <Button href="/improvements" style={{ marginTop: 12 }}>进入服务与交付改进闭环</Button>
    </Card>
    <Card title="GEO 回答采样"><Typography.Paragraph type="secondary">{geo.data?.definition}</Typography.Paragraph>
      <Descriptions items={Object.entries(geo.data?.sample_counts || {}).map(([k,v]) => ({ key: k, label: k === 'real' ? '真实采样' : '模拟采样', children: `${v.mentioned_count} 条字面命中 / ${v.sample_count} 条回答` }))} />
      <Table rowKey="id" dataSource={geo.data?.items} expandable={{ expandedRowRender: r => <><Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{r.answer}</Typography.Paragraph><p>人工核查：{r.factual_errors || '未填写事实错误备注'}</p>{r.citations.map(url => <p key={url}><a href={url} target="_blank" rel="noreferrer">引用来源：{url}</a></p>)}</> }} columns={[{ title: '平台', dataIndex: 'platform' }, { title: '问题', dataIndex: 'question' }, { title: '采样时间', dataIndex: 'captured_at', render: date }, { title: '性质', dataIndex: 'simulated', render: v => <Tag>{v ? '模拟回答' : '真实采样'}</Tag> }, { title: '品牌字面命中', dataIndex: 'mentioned', render: v => v ? '命中' : '未命中' }]} />
    </Card>
    <Card title="录入外部回答"><Form layout="vertical" initialValues={{ simulated: true, brand: '模拟营业厅', factual_errors: '' }} onFinish={add.mutate}>
      <div className="grid"><Form.Item name="platform" label="平台" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="captured_at" label="采样时间（上海）" rules={[{ required: true }]}><Input type="datetime-local" /></Form.Item><Form.Item name="brand" label="待核查品牌名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="simulated" label="采样性质"><Select options={[{ value: true, label: '模拟演示样本' }, { value: false, label: '实际取得的外部回答' }]} /></Form.Item></div>
      <Form.Item name="question" label="原始问题" rules={[{ required: true }]}><Input.TextArea rows={2} /></Form.Item><Form.Item name="answer" label="完整回答" rules={[{ required: true }]}><Input.TextArea rows={5} /></Form.Item><Form.Item name="citations" label="引用来源网址（每行一个）"><Input.TextArea rows={2} /></Form.Item><Form.Item name="factual_errors" label="人工核查的事实错误与依据"><Input.TextArea rows={2} /></Form.Item><Button htmlType="submit" type="primary" loading={add.isPending}>保存回答样本</Button>
    </Form><details style={{ marginTop: 16 }}><summary>批量导入采样文件</summary><p>选择包含多条采样记录的 JSON 文件；字段与操作指南中的样例一致。</p><input aria-label="采样文件" type="file" accept=".json" disabled={batch.isPending} onChange={e => { const file = e.target.files?.[0]; if (file) batch.mutate(file); e.target.value = ''; }} /></details></Card>
  </div>;
}
