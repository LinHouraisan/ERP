import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Input, Select, Table } from 'antd';
import { api } from '../../lib/api';
import { label } from '../../lib/display';
type Task = { id: string; title: string; status: string; owner_role: string; note: string };
function TaskAction({ task, sid }: { task: Task; sid: string }) {
  const cache = useQueryClient();
  const update = useMutation({ mutationFn: (body: unknown) => api(`/service-tasks/${task.id}/transition`, body), onSuccess: () => { void cache.invalidateQueries({ queryKey: ['tasks', sid] }); void cache.invalidateQueries({ queryKey: ['service', sid] }); } });
  const options = task.status === 'OPEN' ? ['IN_PROGRESS','CANCELLED'] : task.status === 'IN_PROGRESS' ? ['CLOSED','CANCELLED'] : [];
  return options.length ? <Form layout="inline" onFinish={update.mutate} initialValues={{ status: options[0] }}>
    <Form.Item label="下一状态" name="status"><Select options={options.map(value => ({ value, label: label(value) }))} /></Form.Item>
    <Form.Item label="处理记录" name="note" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item><Button htmlType="submit" loading={update.isPending}>更新任务</Button>
    {update.error && <Alert title={update.error.message} type="error" />}
  </Form> : null;
}
export function TaskPanel({ sid }: { sid: string }) {
  const cache = useQueryClient();
  const tasks = useQuery({ queryKey: ['tasks', sid], queryFn: () => api<{ items: Task[] }>(`/service-tasks?service_id=${sid}`) });
  const create = useMutation({ mutationFn: (body: object) => api('/service-tasks', { ...body, service_id: sid }), onSuccess: () => { void cache.invalidateQueries({ queryKey: ['tasks', sid] }); void cache.invalidateQueries({ queryKey: ['service', sid] }); } });
  return <Card title="服务任务"><Form layout="inline" initialValues={{ owner_role: 'STAFF' }} onFinish={create.mutate} style={{ gap: 12, marginBottom: 18 }}>
    <Form.Item label="任务内容" name="title" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item><Form.Item label="负责角色" name="owner_role"><Select options={[{ value: 'STAFF', label: '店员' }, { value: 'MANAGER', label: '店长' }]} /></Form.Item><Button htmlType="submit" loading={create.isPending}>建立服务任务</Button>
    {(create.error || tasks.error) && <Alert type="error" title={(create.error || tasks.error)?.message} />}
  </Form><Table size="small" rowKey="id" dataSource={tasks.data?.items} columns={[{ title: '任务', dataIndex: 'title' }, { title: '状态', dataIndex: 'status', render: label }, { title: '最新处理', dataIndex: 'note' }]} expandable={{ expandedRowRender: task => <TaskAction task={task} sid={sid} /> }} /></Card>;
}
