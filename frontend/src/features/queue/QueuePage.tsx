import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Form, Input, Select, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../lib/api';
import { categories, date, label } from '../../lib/display';
import type { User } from '../auth/LoginPage';

type PublicTicket = { ticket_number: string; category: string; window: string | null; status: string; updated_at: string };
type Ticket = PublicTicket & { id: string; window_id: string | null; service_id: string | null; round_wait_seconds: number | null; cumulative_wait_seconds: number };
export function PublicQueuePage({ boardOnly = false }: { boardOnly?: boolean }) {
  const board = useQuery({ queryKey: ['public-board'], queryFn: () => api<{ items: PublicTicket[]; updated_at: string }>('/public/queue-board'), refetchInterval: 5000 });
  const take = useMutation({ mutationFn: (body: unknown) => api<PublicTicket>('/public/queue-tickets', body), onSuccess: () => { void board.refetch(); } });
  return <main className="page stack"><Typography.Title>模拟营业厅 · {boardOnly ? '叫号屏' : '取号'}</Typography.Title>
    {!boardOnly && <Card title="选择办理类别"><Form layout="inline" initialValues={{ category: 'PLAN' }} onFinish={take.mutate}>
      <Form.Item label="业务类别" name="category"><Select style={{ width: 200 }} options={categories} /></Form.Item><Button htmlType="submit" type="primary" loading={take.isPending}>领取号码</Button>
    </Form>{take.data && <Typography.Title level={2}>您的号码：{take.data.ticket_number}</Typography.Title>}</Card>}
    {(take.error || board.error) && <Alert type="error" title={(take.error || board.error)?.message} />}
    <Card title="当前排队"><Table rowKey={r => `${r.ticket_number}-${r.updated_at}`} pagination={false} dataSource={board.data?.items} columns={[
      { title: '票号', dataIndex: 'ticket_number' }, { title: '业务类别', dataIndex: 'category', render: label }, { title: '状态', dataIndex: 'status', render: label }, { title: '窗口', dataIndex: 'window', render: v => v || '请等候' },
    ]} /></Card><Typography.Text type="secondary">上次成功更新：{date(board.data?.updated_at)}。公共屏仅显示票号、业务类别和窗口，不显示客户资料。</Typography.Text>
  </main>;
}
function TicketHistory({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['ticket', id], queryFn: () => api<Ticket & { events: { action: string; reason: string; at: string }[] }>(`/queue-tickets/${id}`) });
  return <>{q.error && <Alert type="error" title={q.error.message} />}{q.data?.events.map((e, i) => <p key={i}>{date(e.at)} · {e.action} · {e.reason}</p>)}</>;
}
export function QueuePage({ user }: { user: User }) {
  const cache = useQueryClient(), navigate = useNavigate();
  const [notice, setNotice] = useState('');
  const windows = useQuery({ queryKey: ['windows'], queryFn: () => api<{ items: { id: string; name: string; categories: string[] }[] }>('/windows') });
  const tickets = useQuery({ queryKey: ['tickets'], queryFn: () => api<{ items: Ticket[] }>('/queue-tickets'), refetchInterval: 5000 });
  const refresh = () => { void cache.invalidateQueries({ queryKey: ['tickets'] }); void cache.invalidateQueries({ queryKey: ['ticket'] }); };
  const call = useMutation({ mutationFn: (id: string) => api<{ ticket: Ticket | null }>(`/windows/${id}/call-next`, {}), onSuccess: r => { setNotice(r.ticket ? `当前票号 ${r.ticket.ticket_number}` : '没有符合窗口类别的待办号码'); refresh(); } });
  const act = useMutation({ mutationFn: ({ id, action, body = {} }: { id: string; action: string; body?: object }) => api<Ticket>(`/queue-tickets/${id}/${action}`, body), onSuccess: (r, v) => { refresh(); if (v.action === 'start' && r.service_id) navigate(`/services?id=${r.service_id}`); } });
  const error = windows.error || tickets.error || call.error || act.error;
  return <div className="stack"><div className="toolbar"><Typography.Title level={3}>排队与窗口</Typography.Title><Space><a href="/take-number" target="_blank" rel="noreferrer">打开取号页</a><a href="/public-board" target="_blank" rel="noreferrer">打开公共屏</a></Space></div>
    {error && <Alert type="error" title={error.message} />}{notice && <Alert title={notice} type="info" />}
    <div className="grid">{windows.data?.items.map(w => <Card key={w.id} title={w.name}><p>{w.categories.map(label).join('、')}</p><Button onClick={() => call.mutate(w.id)} loading={call.isPending}>叫下一号 · {w.name}</Button></Card>)}</div>
    <Table rowKey="id" dataSource={tickets.data?.items} scroll={{ x: 850 }} expandable={{ expandedRowRender: r => <TicketHistory id={r.id} /> }} columns={[
      { title: '票号', dataIndex: 'ticket_number' }, { title: '类别', dataIndex: 'category', render: label }, { title: '状态', dataIndex: 'status', render: s => <Tag>{label(s)}</Tag> },
      { title: '本轮 / 累计等待秒', render: (_, r) => `${r.round_wait_seconds ?? '等待中'} / ${r.cumulative_wait_seconds}` },
      { title: '操作', render: (_, r) => <Space wrap>
        {r.status === 'CALLED' && <><Button type="primary" onClick={() => act.mutate({ id: r.id, action: 'start' })} loading={act.isPending}>开始接待</Button><Button onClick={() => act.mutate({ id: r.id, action: 'miss', body: { reason: '叫号后未到场' } })}>标记过号</Button></>}
        {['WAITING','CALLED'].includes(r.status) && <Button onClick={() => act.mutate({ id: r.id, action: 'cancel', body: { reason: '人工取消排队' } })}>取消排队</Button>}
        {r.status === 'MISSED' && <Button onClick={() => act.mutate({ id: r.id, action: 'requeue', body: { reason: '客户返回，重新排队' } })}>返回队尾</Button>}
        {r.service_id && <Button onClick={() => navigate(`/services?id=${r.service_id}`)}>查看接待</Button>}
      </Space> },
    ]} />
    {user.role !== 'STAFF' && <Card title="调整等待中的业务类别"><Form layout="inline" onFinish={v => act.mutate({ id: v.id, action: 'adjust', body: { category: v.category, reason: v.reason } })}>
      <Form.Item label="票号" name="id" rules={[{ required: true }]}><Select style={{ width: 160 }} options={tickets.data?.items.filter(r => r.status === 'WAITING').map(r => ({ value: r.id, label: r.ticket_number }))} /></Form.Item>
      <Form.Item label="类别" name="category" rules={[{ required: true }]}><Select style={{ width: 140 }} options={categories} /></Form.Item><Form.Item label="原因" name="reason" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item><Button htmlType="submit" loading={act.isPending}>保存调整</Button>
    </Form></Card>}
  </div>;
}
