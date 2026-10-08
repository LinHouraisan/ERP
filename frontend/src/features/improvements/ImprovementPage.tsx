import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Form, Input, Select, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../lib/api';
import { categories, date, label } from '../../lib/display';
type Ratio = { numerator: number; denominator: number; value: number | null };
type Duration = { sample_count: number; p50_seconds: number | null; p90_seconds: number | null; sample_insufficient: boolean };
type Snapshot = { snapshot_id: string; created_at: string; filters: { from: string; to: string; category: string | null; cohort: string }; metrics: { completed_services: number; preset_services: number; participation: Ratio; satisfaction: { average: number | null; sample_count: number }; quality_problem_rate: Ratio; waiting: Duration; cumulative_waiting: Duration; service_duration: Duration; cancelled: number; missed: number; fulfillment?: { sample_count: number; completed: number; pending: number; definition: string } }; evidence: Record<string, string[]> };
type Task = { id: string; snapshot_id: string; status: string; suggestion: Record<string, unknown>; owner_id: string | null; plan: string | null; target: string | null; verification: unknown; events?: { from: string; to: string; reason: string; at: string }[] };
const ratio = (r: Ratio) => `${r.value == null ? '暂无数据' : (r.value * 100).toFixed(1) + '%'}（${r.numerator}/${r.denominator}）`;

function TaskDetail({ id, afterSnapshot }: { id: string; afterSnapshot?: string }) {
  const cache = useQueryClient();
  const task = useQuery({ queryKey: ['improvement', id], queryFn: () => api<Task>(`/improvement-tasks/${id}`) });
  const staff = useQuery({ queryKey: ['staff'], queryFn: () => api<{ items: { id: string; username: string; role: string }[] }>('/staff') });
  const before = useQuery({ queryKey: ['metric-snapshot', task.data?.snapshot_id], queryFn: () => api<Snapshot>(`/metric-snapshots/${task.data?.snapshot_id}`), enabled: !!task.data });
  const change = useMutation({ mutationFn: (v: { status: string; reason: string; owner_id?: string; plan?: string; target?: string; result?: string; conditions_changed?: string; unresolved_issues?: string }) => {
    const { result, conditions_changed, unresolved_issues, ...body } = v;
    return api(`/improvement-tasks/${id}/transition`, { ...body, ...(v.status === 'VERIFIED' ? { verification: { before_snapshot_id: task.data?.snapshot_id, after_snapshot_id: afterSnapshot, result, conditions_changed, unresolved_issues } } : {}) });
  }, onSuccess: async () => { await Promise.all([cache.invalidateQueries({ queryKey: ['improvement', id] }), cache.invalidateQueries({ queryKey: ['improvements'] })]); } });
  const row = task.data;
  const next: Record<string, string[]> = { PROPOSED: ['APPROVED','REJECTED'], APPROVED: ['IN_PROGRESS','REJECTED'], IN_PROGRESS: ['VERIFIED'], VERIFIED: ['CLOSED'] };
  return <Card title="改进任务详情">{(task.error || staff.error || before.error || change.error) && <Alert type="error" title={(task.error || staff.error || before.error || change.error)?.message} />}
    {row && <><Tag data-testid="improvement-status">{label(row.status)}</Tag><Descriptions column={1} items={[{ key: 'plan', label: '处理计划', children: row.plan || '待审核' }, { key: 'target', label: '验证目标', children: row.target || '待审核' }]} />
      <Descriptions column={1} items={[['phenomenon','观察到的现象'],['possible_cause','待核查的原因'],['suggestion','改进建议'],['verification','验证办法']].filter(([key]) => row.suggestion[key]).map(([key, name]) => ({ key, label: name, children: String(row.suggestion[key]) }))} />
      <details><summary>建议依据与统计口径</summary><pre>{JSON.stringify(before.data, null, 2)}</pre>{before.data?.evidence.service_ids.map(sid => <p key={sid}><a href={`/services?id=${sid}`}>查看服务 {sid}</a></p>)}</details>
      {next[row.status] && <Form key={row.status} disabled={change.isPending} layout="vertical" initialValues={{ status: next[row.status][0] }} onFinish={change.mutate} style={{ marginTop: 18 }}>
        <Form.Item label="下一状态" name="status"><Select options={next[row.status].map(value => ({ value, label: label(value) }))} /></Form.Item>
        <Form.Item label="处理原因" name="reason" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={2} /></Form.Item>
        {row.status === 'PROPOSED' && <><Form.Item label="负责人" name="owner_id"><Select options={staff.data?.items.map(u => ({ value: u.id, label: `${u.username} · ${u.role}` }))} /></Form.Item><Form.Item label="执行计划" name="plan"><Input.TextArea /></Form.Item><Form.Item label="验证目标" name="target"><Input /></Form.Item></>}
        {row.status === 'IN_PROGRESS' && <><Alert type="info" title="验证前请先按相同口径生成新的统计快照；样本少或条件变化时，不能据此认定效果提升。" />
          <Typography.Paragraph>前快照：{row.snapshot_id}<br />后快照：{afterSnapshot || '尚未生成'}</Typography.Paragraph>
          <Form.Item label="同期条件变化" name="conditions_changed" rules={[{ required: true }]}><Input.TextArea /></Form.Item><Form.Item label="验证结论（含未改善情况）" name="result" rules={[{ required: true }]}><Input.TextArea /></Form.Item><Form.Item label="遗留问题" name="unresolved_issues"><Input.TextArea /></Form.Item>
        </>}
        <Button htmlType="submit" type="primary" loading={change.isPending}>保存任务进展</Button>
      </Form>}
      {row.verification != null && <details><summary>验证记录</summary><pre>{JSON.stringify(row.verification, null, 2)}</pre></details>}
      {row.events?.map((e, i) => <p key={i}>{date(e.at)} · {label(e.from)} → {label(e.to)}：{e.reason}</p>)}
    </>}
  </Card>;
}
export function ImprovementPage() {
  const cache = useQueryClient();
  const [filters, setFilters] = useState(''), [id, setId] = useState<string>();
  const metrics = useQuery({ queryKey: ['metrics', filters], queryFn: () => api<Snapshot>(`/service-metrics${filters}`), staleTime: Infinity });
  const tasks = useQuery({ queryKey: ['improvements'], queryFn: () => api<{ items: Task[] }>('/improvement-tasks') });
  const propose = useMutation({ mutationFn: () => api<Task>('/improvement-proposals', { snapshot_id: metrics.data!.snapshot_id, request_key: crypto.randomUUID() }), onSuccess: r => { setId(r.id); void cache.invalidateQueries({ queryKey: ['improvements'] }); } });
  const manual = useMutation({ mutationFn: (v: object) => api<Task>('/improvement-tasks', { ...v, snapshot_id: metrics.data!.snapshot_id }), onSuccess: r => { setId(r.id); void cache.invalidateQueries({ queryKey: ['improvements'] }); } });
  const m = metrics.data?.metrics, error = metrics.error || tasks.error || propose.error || manual.error;
  return <div className="stack">{error && <Alert type="error" title={error.message} />}
    <Card title="服务统计与证据" extra={<Button onClick={() => void metrics.refetch()} loading={metrics.isFetching}>生成新统计快照</Button>}>
      <Form layout="inline" onFinish={v => { const p = new URLSearchParams(); if (v.start) p.set('start', v.start + '+08:00'); if (v.end) p.set('end', v.end + '+08:00'); if (v.category) p.set('category', v.category); setFilters('?' + p.toString()); }} style={{ gap: 12, marginBottom: 18 }}>
        <Form.Item label="开始时间（上海）" name="start"><Input type="datetime-local" /></Form.Item><Form.Item label="结束时间（上海）" name="end"><Input type="datetime-local" /></Form.Item><Form.Item label="类别" name="category"><Select allowClear style={{ width: 140 }} options={categories} /></Form.Item><Button htmlType="submit">按条件统计</Button>
      </Form>
      {m && <><Descriptions column={{ xs: 1, md: 3 }} items={[
        { key: 'services', label: '完成接待 / 其中预置', children: `${m.completed_services} / ${m.preset_services}` },
        { key: 'score', label: '客户满意度', children: `${m.satisfaction.average?.toFixed(2) ?? '暂无评价'}（${m.satisfaction.sample_count} 个样本）` },
        { key: 'participation', label: '评价参与率', children: ratio(m.participation) }, { key: 'quality', label: '质检问题率', children: ratio(m.quality_problem_rate) },
        { key: 'cancel', label: '取消 / 过号', children: `${m.cancelled} / ${m.missed}` },
      ]} />
        <Table size="small" pagination={false} rowKey="name" dataSource={[{ name: '本轮等待', ...m.waiting }, { name: '累计等待', ...m.cumulative_waiting }, { name: '服务时长', ...m.service_duration }]} columns={[
          { title: '指标', dataIndex: 'name' }, { title: '样本数', dataIndex: 'sample_count' }, { title: 'P50 秒', dataIndex: 'p50_seconds', render: v => v == null ? '暂无数据' : v.toFixed(1) }, { title: 'P90 秒', dataIndex: 'p90_seconds', render: v => v == null ? '暂无数据' : v.toFixed(1) }, { title: '说明', dataIndex: 'sample_insufficient', render: v => v ? '样本少于 5，仅供核查' : '模拟样本，不代表经营效果' },
        ]} />
        {m.fulfillment && <Typography.Paragraph>安装交付：{m.fulfillment.completed} 已验收 / {m.fulfillment.pending} 待完成 / {m.fulfillment.sample_count} 个样本。{m.fulfillment.definition}</Typography.Paragraph>}
        <Typography.Paragraph type="secondary">{metrics.data?.filters.from} 至 {metrics.data?.filters.to}；{metrics.data?.filters.cohort}</Typography.Paragraph>
        <details><summary>当前统计快照及原始证据</summary><pre>{JSON.stringify(metrics.data, null, 2)}</pre>{metrics.data?.evidence.service_ids.map(sid => <p key={sid}><a href={`/services?id=${sid}`}>服务 {sid}</a></p>)}{metrics.data?.evidence.installation_ids?.map(iid => <p key={iid}><a href={`/installations?id=${iid}`}>安装交付 {iid}</a></p>)}</details>
        <Button style={{ marginTop: 16 }} type="primary" loading={propose.isPending} onClick={() => propose.mutate()}>生成改进建议草稿</Button>
      </>}
    </Card>
    <Card title="人工改进建议"><Form layout="vertical" onFinish={manual.mutate}><Form.Item label="建议内容" name="suggestion" rules={[{ required: true, whitespace: true }]}><Input.TextArea /></Form.Item><Button htmlType="submit" disabled={!metrics.data} loading={manual.isPending}>保存人工建议</Button></Form></Card>
    {id && <TaskDetail key={id} id={id} afterSnapshot={metrics.data?.snapshot_id} />}
    <Card title="改进任务"><Table rowKey="id" dataSource={tasks.data?.items} columns={[{ title: '任务状态', dataIndex: 'status', render: label }, { title: '计划', dataIndex: 'plan', render: v => v || '待审核' }, { title: '目标', dataIndex: 'target' }, { title: '处理', render: (_, t) => <Button onClick={() => setId(t.id)}>打开改进任务</Button> }]} /></Card>
  </div>;
}
