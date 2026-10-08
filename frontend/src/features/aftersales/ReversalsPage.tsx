import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Input, Select, Table } from 'antd';
import { api } from '../../lib/api';
import { date, label } from '../../lib/display';
import type { User } from '../auth/LoginPage';
type Reversal = { id: string; acceptance_id: string; reason: string; status: string; last_error: string | null; resolution: string; external_request_id: string; events: { action: string; at: string; detail: unknown }[] };

export function ReversalsPage({ user }: { user: User }) {
  const cache = useQueryClient(), [params, setParams] = useSearchParams(), [key, setKey] = useState(() => crypto.randomUUID());
  const manager = ['MANAGER','ADMIN'].includes(user.role), id = params.get('id');
  const list = useQuery({ queryKey: ['reversals'], queryFn: () => api<{ items: Reversal[] }>('/reversals') });
  const detail = useQuery({ queryKey: ['reversal', id], queryFn: () => api<Reversal>(`/reversals/${id}`), enabled: !!id });
  const sources = useQuery({ queryKey: ['acceptances'], queryFn: () => api<{ items: { acceptance_id: string; status: string; service_id: string }[] }>('/acceptances') });
  const refresh = async () => { await Promise.all(['reversals','reversal','todos','earnings','transactions'].map(k => cache.invalidateQueries({ queryKey: [k] }))); };
  const write = useMutation({ mutationFn: ({ path, body }: { path: string; body: object }) => api<Reversal>(path, body), onSuccess: refresh });
  const create = useMutation({ mutationFn: (v: object) => api<Reversal>('/reversals', { ...v, request_key: key }), onSuccess: async r => { setParams({ id: r.id }); setKey(crypto.randomUUID()); await refresh(); } });
  const row = detail.data, error = list.error || detail.error || sources.error || write.error || create.error;
  return <div className="stack">{error && <Alert type="error" title={error.message} />}<Card title="通信冲正记录"><Table rowKey="id" dataSource={list.data?.items} columns={[{ title: '原因', dataIndex: 'reason' }, { title: '结果', dataIndex: 'status', render: label }, { title: '操作', render: (_, r) => <Button onClick={() => setParams({ id: r.id })}>打开冲正</Button> }]} /></Card>
    {row && <Card title={`冲正 ${row.id.slice(0,8)}`}><p>{row.reason} · {label(row.status)}</p>{row.last_error && <Alert title={row.last_error} type="warning" />}<p>原请求号：{row.external_request_id}</p><p>{row.resolution}</p>
      {manager && row.status === 'REQUESTED' && <Form name="reversal-review" layout="inline" initialValues={{ decision: 'APPROVE' }} onFinish={v => write.mutate({ path: `/reversals/${row.id}/review`, body: v })}><Form.Item name="decision" label="审批"><Select options={[{ value: 'APPROVE', label: '批准' }, { value: 'REJECT', label: '驳回' }]} /></Form.Item><Form.Item name="note" label="核对依据" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item><Button htmlType="submit" loading={write.isPending}>审核冲正</Button></Form>}
      {manager && ['APPROVED','PENDING','UNKNOWN'].includes(row.status) && <Button type="primary" loading={write.isPending} onClick={() => write.mutate({ path: `/reversals/${row.id}/${row.status === 'APPROVED' ? 'submit' : 'reconcile'}`, body: {} })}>{row.status === 'APPROVED' ? '提交模拟冲正' : '按原冲正号核对'}</Button>}
      {manager && ['APPROVED','FAILED'].includes(row.status) && !row.resolution && <Form name="reversal-evidence" onFinish={v => write.mutate({ path: `/reversals/${row.id}/resolution`, body: v })}><Form.Item name="note" label="人工核查与已履约服务的处理依据" rules={[{ required: true, whitespace: true }]}><Input.TextArea /></Form.Item><Button htmlType="submit" loading={write.isPending}>保留人工处理记录</Button></Form>}
      <details><summary>原单与冲正过程</summary>{row.events.map((e,i) => <p key={i}>{date(e.at)} · {label(e.action)} · {JSON.stringify(e.detail)}</p>)}</details>
    </Card>}
    <Card title="申请通信冲正"><Form name="reversal-create" layout="vertical" initialValues={{ acceptance_id: params.get('acceptance_id') || undefined, scenario: 'NORMAL' }} onFinish={create.mutate}><Form.Item name="acceptance_id" label="原成功受理" rules={[{ required: true }]}><Select options={sources.data?.items.filter(a => a.status === 'SUCCESS').map(a => ({ value: a.acceptance_id, label: `成功受理 ${a.acceptance_id.slice(0,8)}` }))} /></Form.Item><Form.Item name="reason" label="冲正原因" rules={[{ required: true, whitespace: true }]}><Input.TextArea /></Form.Item><Form.Item name="scenario" label="模拟情形"><Select options={[{ value: 'NORMAL', label: '正常冲正' }, { value: 'SUCCESS_TIMEOUT', label: '成功后返回超时' }, { value: 'DECLINED', label: '模拟拒绝' }]} /></Form.Item><Button type="primary" htmlType="submit" loading={create.isPending}>提交冲正申请</Button></Form></Card>
  </div>;
}
