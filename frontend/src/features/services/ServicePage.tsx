import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Form, Input, Select, Space, Table, Tag, Timeline, Typography } from 'antd';
import { api } from '../../lib/api';
import { label } from '../../lib/display';
import { RecommendationPanel } from '../recommendations/RecommendationPanel';
import { AcceptancePanel } from '../acceptances/AcceptancePanel';
import { FeedbackPanel } from '../feedback/FeedbackPage';
import { TaskPanel } from './TaskPanel';

export type Snapshot = { snapshot_id: string; account_id: string; source: string; source_time: string; fetched_at: string; completeness: string; payload: { monthly_fee: string | null; package_name: string; broadband: boolean | null; contract_end: string | null; number: string; restrictions: string[] | null; discounts: string[] | null } };
export type Service = { service_id: string; customer_id: string | null; category: string; status: string; started_at: string; ended_at: string | null; preset: boolean; snapshots?: Snapshot[]; events?: { action: string; at: string; detail: unknown }[] };
const date = (s: string | null) => s ? new Date(s).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '—';

export function ServicePage() {
  const cache = useQueryClient();
  const [params, setParams] = useSearchParams();
  const sid = params.get('id') || undefined;
  const setSid = (id: string) => setParams({ id });
  const [notice, setNotice] = useState('');
  const [page, setPage] = useState(1);
  const list = useQuery({ queryKey: ['services', page], queryFn: () => api<{ items: Service[]; total: number }>(`/service-sessions?page=${page}&page_size=10`) });
  const detail = useQuery({ queryKey: ['service', sid], queryFn: () => api<Service>(`/service-sessions/${sid}`), enabled: !!sid });
  const refresh = () => { void cache.invalidateQueries({ queryKey: ['services'] }); void cache.invalidateQueries({ queryKey: ['service', sid] }); };
  const create = useMutation({ mutationFn: (category: string) => api<Service>('/service-sessions', { category }), onSuccess: r => { setSid(r.service_id); setNotice(''); refresh(); } });
  const query = useMutation({ mutationFn: (data: { number: string }) => api<Snapshot | { status: string }>(`/service-sessions/${sid}/account-query`, { ...data, account_type: 'MOBILE' }), onSuccess: r => { setNotice('status' in r ? '未找到该模拟号码，请核对后重试。' : ''); refresh(); } });
  const finish = useMutation({ mutationFn: () => api(`/service-sessions/${sid}/finish`, {}), onSuccess: refresh });
  const snapshot = detail.data?.snapshots?.at(-1);
  const error = list.error || detail.error || create.error || query.error || finish.error;
  return <div className="stack">
    <div className="toolbar"><div><Typography.Title level={3}>服务工作台</Typography.Title><Typography.Text type="secondary">事实查询、人工决策与办理记录</Typography.Text></div>
      <Space><Button type="primary" onClick={() => create.mutate('PLAN')} loading={create.isPending}>新建套餐咨询</Button><Button onClick={() => create.mutate('FAULT')}>新建故障服务</Button></Space></div>
    {error && <Alert title={error.message} type="error" showIcon />}
    {notice && <Alert title={notice} type="warning" showIcon />}
    {sid && <>
      <Card title={<Space>本次接待<Tag>{detail.data?.status === 'ENDED' ? '已结束' : '进行中'}</Tag></Space>} extra={<Button onClick={() => finish.mutate()} disabled={detail.data?.status !== 'ACTIVE'} loading={finish.isPending}>结束接待</Button>}>
        <Form layout="inline" onFinish={query.mutate} style={{ gap: 12 }}>
          <Form.Item label="模拟号码" name="number" initialValue="19900000001" rules={[{ required: true }, { pattern: /^199\d{8}$/, message: '请输入 199 开头的 11 位模拟号码' }]}><Input placeholder="19900000001" /></Form.Item>
          <Button htmlType="submit" type="primary" loading={query.isPending} disabled={detail.data?.status !== 'ACTIVE'}>查询账号资料</Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>开始于 {date(detail.data?.started_at || null)} · 接待结束与外部办理结果分别记录。</Typography.Paragraph>
        {detail.data?.customer_id && <Space><Button href={`/customers?id=${detail.data.customer_id}`}>客户全景</Button><Button href={`/sales?customer_id=${detail.data.customer_id}&source_service_id=${sid}`}>关联销售订单</Button></Space>}
      </Card>
      {snapshot && <Card title="账号事实" extra={<Tag>{snapshot.completeness === 'COMPLETE' ? '资料完整' : '资料缺失，需核查'}</Tag>}>
        <Descriptions column={{ xs: 1, sm: 2, lg: 3 }} items={[
          { key: 'number', label: '模拟号码', children: snapshot.payload.number },
          { key: 'package', label: '当前套餐', children: snapshot.payload.package_name || '未知' },
          { key: 'monthly', label: '当前月费', children: snapshot.payload.monthly_fee == null ? '未知' : `${snapshot.payload.monthly_fee} 元` },
          { key: 'broadband', label: '宽带', children: snapshot.payload.broadband == null ? '未知' : snapshot.payload.broadband ? '包含' : '不含' },
          { key: 'contract', label: '合约到期日', children: snapshot.payload.contract_end === undefined ? '未知' : snapshot.payload.contract_end ?? '无在约记录' },
          { key: 'restrictions', label: '限制', children: snapshot.payload.restrictions == null ? '未知' : snapshot.payload.restrictions.join('、') || '无已知限制' },
          { key: 'discounts', label: '优惠', children: snapshot.payload.discounts == null ? '未知' : snapshot.payload.discounts.join('、') || '无已知优惠' },
          { key: 'source', label: '资料来源', children: snapshot.source },
          { key: 'source_time', label: '来源时间', children: date(snapshot.source_time) },
          { key: 'fetched', label: '查询时间', children: date(snapshot.fetched_at) },
        ]} />
        <details><summary>历史查询快照（{detail.data?.snapshots?.length}）</summary>{detail.data?.snapshots?.map(s => <details key={s.snapshot_id}><summary>{date(s.fetched_at)} · {s.payload.package_name} · 月费 {s.payload.monthly_fee ?? '未知'}</summary><pre>{JSON.stringify(s, null, 2)}</pre></details>)}</details>
      </Card>}
      <RecommendationPanel key={sid} sid={sid} snapshotId={snapshot?.snapshot_id} active={detail.data?.status === 'ACTIVE'} />
      <AcceptancePanel sid={sid} active={detail.data?.status === 'ACTIVE'} />
      <TaskPanel sid={sid} />
      <FeedbackPanel key={`feedback-${sid}`} sid={sid} ended={detail.data?.status === 'ENDED'} />
      <Card title="服务时间线"><Timeline items={detail.data?.events?.map(e => ({ content: <details><summary>{date(e.at)} · {e.action}</summary><pre>{JSON.stringify(e.detail, null, 2)}</pre></details> }))} /></Card>
    </>}
    <Card title="服务记录"><Table size="small" rowKey="service_id" dataSource={list.data?.items} loading={list.isPending} pagination={{ current: page, pageSize: 10, total: list.data?.total, onChange: setPage, showSizeChanger: false }} scroll={{ x: 650 }} columns={[
      { title: '开始时间', dataIndex: 'started_at', render: date }, { title: '类别', dataIndex: 'category', render: label }, { title: '接待状态', dataIndex: 'status', render: label },
      { title: '来源', dataIndex: 'preset', render: v => v ? '预置模拟历史' : '本地模拟接待' },
      { title: '查看', render: (_, r) => <Button onClick={() => { setSid(r.service_id); setNotice(''); }}>打开服务</Button> },
    ]} /></Card>
  </div>;
}
