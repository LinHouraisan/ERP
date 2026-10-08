import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Input, Select, Table } from 'antd';
import { api } from '../../lib/api';
import { date, label } from '../../lib/display';
import type { User } from '../auth/LoginPage';
type Prompt = { id: string; scenario: string; version: number; status: string; text: string };
type Run = { id: string; scenario: string; status: string; mode: string; model: string; error: string | null; usage: unknown; output: unknown; created_at: string };
export function PromptPage({ user }: { user: User }) {
  const cache = useQueryClient();
  const prompts = useQuery({ queryKey: ['prompts'], queryFn: () => api<{ items: Prompt[] }>('/prompt-versions') });
  const runs = useQuery({ queryKey: ['ai-runs'], queryFn: () => api<{ items: Run[] }>('/ai-runs') });
  const write = useMutation({ mutationFn: ({ path, body }: { path: string; body: object }) => api(path, body), onSuccess: () => { void cache.invalidateQueries({ queryKey: ['prompts'] }); } });
  const error = prompts.error || runs.error || write.error;
  return <div className="stack">{error && <Alert type="error" title={error.message} />}
    <Card title="提示词版本"><Table rowKey="id" dataSource={prompts.data?.items} columns={[{ title: '场景', dataIndex: 'scenario' }, { title: '版本', dataIndex: 'version' }, { title: '状态', dataIndex: 'status', render: label }, { title: '操作', render: (_, p) => <Button disabled={p.status === 'PUBLISHED' || user.role !== 'ADMIN'} loading={write.isPending} onClick={() => write.mutate({ path: `/prompt-versions/${p.id}/publish`, body: {} })}>{p.status === 'PUBLISHED' ? '已发布不可覆盖' : '发布提示词'}</Button> }]} expandable={{ expandedRowRender: p => <pre>{p.text}</pre> }} /></Card>
    {user.role === 'ADMIN' && <Card title="新建提示词草稿"><Form layout="vertical" onFinish={body => write.mutate({ path: '/prompt-versions', body })} initialValues={{ scenario: 'quality' }}><Form.Item label="用途" name="scenario"><Select options={['demand','explanation','quality','improvement','sales','operations'].map(value => ({ value, label: value }))} /></Form.Item><Form.Item label="提示词内容" name="text" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={6} maxLength={12000} /></Form.Item><Button htmlType="submit" loading={write.isPending}>保存新版本草稿</Button></Form></Card>}
    <Card title="AI 辅助运行记录" extra={<Button onClick={() => void runs.refetch()}>刷新运行记录</Button>}><Table rowKey="id" dataSource={runs.data?.items} columns={[{ title: '时间', dataIndex: 'created_at', render: date }, { title: '场景', dataIndex: 'scenario' }, { title: '模式', dataIndex: 'mode' }, { title: '模型', dataIndex: 'model' }, { title: '状态', dataIndex: 'status', render: label }, { title: '错误', dataIndex: 'error' }]} expandable={{ expandedRowRender: r => <pre>{JSON.stringify(r, null, 2)}</pre> }} /></Card>
  </div>;
}
