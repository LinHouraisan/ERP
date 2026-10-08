import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Checkbox, Descriptions, Form, Input, Select, Space, Tag, Typography } from 'antd';
import { api } from '../../lib/api';
import { label, money } from '../../lib/display';
import { QualityReview, type Quality } from '../quality/QualityReview';

type Candidate = { candidate_id: string; product_id: string; policy_version_id: string; monthly_fee: string | null; one_time_fee: string | null; monthly_difference: string | null; contract_months: number; promotion_months: number | null; broadband: boolean | null; eligibility: string; unresolved_needs: string[] };
type Rec = { recommendation_id: string; revision: number; outcome: string; candidates: Candidate[]; missing_fields: string[]; service_tasks: string[]; rule_version: string; prompt_version_id: string; snapshot_id: string };
type AIRun = { id: string; status: string; mode: string; error: string | null; output: { items?: { candidate_id: string; text: string }[]; intent?: string; missing_fields?: string[] } | null };

export function RecommendationPanel({ sid, snapshotId, active }: { sid: string; snapshotId?: string; active: boolean }) {
  const cache = useQueryClient();
  const [rid, setRid] = useState<string>();
  const [selected, setSelected] = useState<{ candidate: Candidate; qid: string }>();
  const keys = useRef<Record<string, string>>({});
  const history = useQuery({ queryKey: ['recommendations', sid], queryFn: () => api<{ items: Rec[] }>(`/service-sessions/${sid}/recommendations`) });
  const products = useQuery({ queryKey: ['products'], queryFn: () => api<{ items: { id: string; name: string }[] }>('/products') });
  const rec = history.data?.items.find(r => r.recommendation_id === rid) || history.data?.items[0];
  const latest = !rid || rid === history.data?.items[0]?.recommendation_id;
  const create = useMutation({ mutationFn: (v: { intent: string; budget?: string; broadband?: boolean; issues?: string }) => api<Rec>(`/service-sessions/${sid}/recommendations`, { snapshot_id: snapshotId, demand: { intent: v.intent, budget: v.budget || null, must_keep: v.broadband ? ['broadband'] : [], issues: v.issues ? [v.issues] : [], missing_fields: [] } }), onSuccess: r => { setRid(r.recommendation_id); setSelected(undefined); void cache.invalidateQueries({ queryKey: ['recommendations', sid] }); void cache.invalidateQueries({ queryKey: ['service', sid] }); } });
  const analyze = useMutation({ mutationFn: (v: { text: string }) => api<AIRun>(`/service-sessions/${sid}/analyze`, { text: v.text, request_key: crypto.randomUUID() }) });
  const explain = useMutation({ mutationFn: () => api<AIRun>(`/recommendations/${rec?.recommendation_id}/explain`, { request_key: crypto.randomUUID() }) });
  const check = useMutation({ mutationFn: async (c: Candidate) => ({ candidate: c, quality: await api<Quality>(`/recommendations/${rec?.recommendation_id}/quality-checks`, { candidate_id: c.candidate_id }) }), onSuccess: r => setSelected({ candidate: r.candidate, qid: r.quality.quality_check_id }) });
  const quality = useQuery({ queryKey: ['quality', selected?.qid], queryFn: () => api<Quality>(`/quality-checks/${selected?.qid}`), enabled: !!selected });
  const draft = useMutation({ mutationFn: () => { const cid = selected!.candidate.candidate_id; keys.current[cid] ||= crypto.randomUUID(); return api('/acceptances', { recommendation_id: rec!.recommendation_id, candidate_id: cid }, { 'Idempotency-Key': keys.current[cid] }); }, onSuccess: () => { void cache.invalidateQueries({ queryKey: ['acceptances', sid] }); void cache.invalidateQueries({ queryKey: ['service', sid] }); } });
  const task = useMutation({ mutationFn: (title: string) => api('/service-tasks', { service_id: sid, title, owner_role: 'STAFF' }), onSuccess: () => { void cache.invalidateQueries({ queryKey: ['tasks', sid] }); } });
  const error = history.error || products.error || create.error || analyze.error || explain.error || check.error || draft.error || task.error;
  const confirmed = quality.data?.reviews?.at(-1)?.decision === 'CONFIRM';
  return <div className="stack">
    {error && <Alert title={error.message} type="error" />}
    <Card title="需求与人工方案选择">
      <Form layout="vertical" onFinish={analyze.mutate}><Form.Item label="客户需求原文（可选 AI 辅助）" name="text" rules={[{ required: true }]}><Input.TextArea rows={2} /></Form.Item><Button htmlType="submit" loading={analyze.isPending} disabled={!active}>辅助分析需求</Button></Form>
      {analyze.data && <Alert type={analyze.data.status === 'FAILED' ? 'warning' : 'info'} title={analyze.data.error || `${analyze.data.mode === 'offline' ? '离线草稿' : '模型草稿'}，请核对后手工填写下方需求`} description={analyze.data.output && JSON.stringify(analyze.data.output)} />}
      <Form layout="vertical" initialValues={{ intent: 'REDUCE_COST', broadband: true }} onFinish={create.mutate} style={{ marginTop: 20 }}>
        <div className="grid"><Form.Item label="办理目标" name="intent"><Select options={[['REDUCE_COST','降低月费'],['CHANGE_PLAN','变更套餐'],['KEEP_CURRENT','保留当前套餐'],['FAULT','故障服务'],['CONSULT','一般咨询']].map(([value, label]) => ({ value, label }))} /></Form.Item>
          <Form.Item label="月费预算（留空不限）" name="budget"><Input inputMode="decimal" /></Form.Item><Form.Item label="其他需求或故障" name="issues"><Input /></Form.Item>
          <Form.Item name="broadband" valuePropName="checked"><Checkbox>必须保留宽带</Checkbox></Form.Item></div>
        <Button htmlType="submit" type="primary" disabled={!snapshotId || !active} loading={create.isPending}>生成规则方案</Button>
        {!snapshotId && <Typography.Paragraph type="secondary">请先查询账号事实；无账号的故障服务可直接建立下方任务。</Typography.Paragraph>}
      </Form>
    </Card>
    {rec && <Card title={<Space>方案结果<Tag>{label(rec.outcome)}</Tag></Space>} extra={<Select aria-label="历史方案版本" value={rec.recommendation_id} onChange={v => { setRid(v); setSelected(undefined); explain.reset(); }} options={history.data?.items.map(r => ({ value: r.recommendation_id, label: `方案 V${r.revision}` }))} />}>
      <Typography.Paragraph type="secondary">规则 {rec.rule_version} · 方案 V{rec.revision} · 所有金额由后端计算。{!latest && '当前是历史方案，仅供回查。'}</Typography.Paragraph>
      {!!rec.missing_fields.length && <Alert type="warning" title={rec.missing_fields.join('；')} />}
      <div className="grid">{rec.candidates.map(c => <Card key={c.candidate_id} size="small" title={products.data?.items.find(p => p.id === c.product_id)?.name || '套餐'} data-testid={`candidate-${c.monthly_fee}`}>
        <Descriptions column={1} items={[
          { key: 'month', label: '月费', children: money(c.monthly_fee) }, { key: 'once', label: '一次费', children: money(c.one_time_fee) },
          { key: 'diff', label: '每月减少', children: money(c.monthly_difference) }, { key: 'contract', label: '新合约', children: `${c.contract_months} 个月` },
          { key: 'promotion', label: '优惠期限', children: c.promotion_months == null ? '未单列限期优惠' : `${c.promotion_months} 个月，到期需重新核查政策` },
          { key: 'broadband', label: '宽带', children: c.broadband == null ? '未知' : c.broadband ? '包含' : '不含' },
        ]} />
        {!!c.unresolved_needs.length && <Alert type="warning" title={c.unresolved_needs.join('；')} />}
        <Typography.Paragraph type="secondary" copyable>{c.policy_version_id}</Typography.Paragraph>
        <Button disabled={!active || !latest || c.eligibility !== 'eligible'} loading={check.isPending} onClick={() => check.mutate(c)}>质检此方案</Button>
      </Card>)}</div>
      {rec.service_tasks.map(title => <Button key={title} onClick={() => task.mutate(title)} loading={task.isPending} style={{ marginTop: 12 }}>建立任务：{title}</Button>)}
      {!!rec.candidates.length && <Button onClick={() => explain.mutate()} loading={explain.isPending} style={{ marginTop: 16 }}>生成辅助解释</Button>}
      {explain.data && <Alert type={explain.data.status === 'FAILED' ? 'warning' : 'info'} title={explain.data.error || `${explain.data.mode === 'offline' ? '离线说明' : '模型说明'}，需人工核对`} description={explain.data.output?.items?.map(i => <p key={i.candidate_id}>{i.text}</p>)} />}
    </Card>}
    {selected && <Card title={`方案质检与人工复核 · 月费 ${money(selected.candidate.monthly_fee)}`}>
      <QualityReview id={selected.qid} onRevision={qid => setSelected({ ...selected, qid })} />
      <Button type="primary" style={{ marginTop: 16 }} disabled={!active || !latest || !confirmed} loading={draft.isPending} onClick={() => draft.mutate()}>建立受理草稿</Button>
      {!confirmed && <Typography.Paragraph type="secondary">需先保存人工确认；受理提交时会重新核查版本、政策与账号事实。</Typography.Paragraph>}
      {draft.isSuccess && <Alert type="success" title="受理草稿已保存，请在下方受理记录中确认提交。" />}
    </Card>}
  </div>;
}
