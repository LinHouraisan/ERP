import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Select, Space, Tag, Typography } from 'antd';
import { api } from '../../lib/api';
import { date, label } from '../../lib/display';
import type { Quality } from '../quality/QualityReview';

type Acceptance = { acceptance_id: string; recommendation_id: string; candidate_id: string; external_request_id: string; external_order_id: string | null; status: string; expected_version: number; last_error: string | null; updated_at: string };
function AcceptanceRow({ row, sid, active }: { row: Acceptance; sid: string; active: boolean }) {
  const cache = useQueryClient();
  const [qid, setQid] = useState<string>();
  const checks = useQuery({ queryKey: ['qualities', row.recommendation_id], queryFn: () => api<{ items: (Quality & { candidate_id: string; created_at: string })[] }>(`/quality-checks?target_id=${row.recommendation_id}`), enabled: row.status === 'DRAFT' });
  const choices = checks.data?.items.filter(q => q.candidate_id === row.candidate_id && q.status !== 'BLOCKED') || [];
  const selected = qid || choices[0]?.quality_check_id;
  const change = useMutation({ mutationFn: (action: string) => api(`/acceptances/${row.acceptance_id}/${action}`, action === 'confirm' ? { expected_version: row.expected_version, quality_check_id: selected } : {}), onSuccess: () => { void cache.invalidateQueries({ queryKey: ['acceptances', sid] }); void cache.invalidateQueries({ queryKey: ['service', sid] }); } });
  return <Card size="small" title={<Space>模拟受理<Tag data-testid="acceptance-status">{label(row.status)}</Tag></Space>}>
    <Typography.Paragraph>更新：{date(row.updated_at)}</Typography.Paragraph>
    <Typography.Paragraph copyable>原请求号：{row.external_request_id}</Typography.Paragraph>
    {row.external_order_id && <Typography.Paragraph>外部单号：{row.external_order_id}</Typography.Paragraph>}
    {row.last_error && <Alert title={row.last_error} type="warning" />}
    {(change.error || checks.error) && <Alert title={(change.error || checks.error)?.message} type="error" />}
    <Space wrap>
      {row.status === 'SUCCESS' && <Button href={`/reversals?acceptance_id=${row.acceptance_id}`}>申请通信冲正</Button>}
      {row.status === 'DRAFT' && <><Select aria-label="确认依据的质检记录" style={{ width: 280 }} value={selected} onChange={setQid} options={choices.map(q => ({ value: q.quality_check_id, label: `${date(q.created_at)} · ${label(q.status)}` }))} />
        <Button type="primary" disabled={!active || !selected} loading={change.isPending} onClick={() => change.mutate('confirm')}>确认并提交模拟办理</Button>
        <Button onClick={() => change.mutate('cancel')} loading={change.isPending}>取消未提交草稿</Button></>}
      {['UNKNOWN','SUBMITTED','SUBMITTING'].includes(row.status) && <Button type="primary" onClick={() => change.mutate('reconcile')} loading={change.isPending}>按原请求号核对</Button>}
    </Space>
    {['UNKNOWN','SUBMITTING','SUBMITTED'].includes(row.status) && <Typography.Paragraph type="secondary">结果尚未确定；请使用上面的核对按钮，保留原请求号。</Typography.Paragraph>}
  </Card>;
}

export function AcceptancePanel({ sid, active }: { sid: string; active: boolean }) {
  const query = useQuery({ queryKey: ['acceptances', sid], queryFn: () => api<{ items: Acceptance[] }>(`/acceptances?service_id=${sid}`) });
  return <Card title="受理记录（与接待状态分别记录）" extra={<Button onClick={() => void query.refetch()}>刷新受理结果</Button>}>
    {query.error && <Alert type="error" title={query.error.message} />}
    <div className="stack">{query.data?.items.map(row => <AcceptanceRow key={row.acceptance_id} row={row} sid={sid} active={active} />)}</div>
    {!query.data?.items.length && <Typography.Text type="secondary">尚无受理；完成方案质检和人工复核后可建立草稿。</Typography.Text>}
  </Card>;
}
