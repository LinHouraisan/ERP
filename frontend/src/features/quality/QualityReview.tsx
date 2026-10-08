import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Descriptions, Form, Input, Select, Table, Tag, Typography } from 'antd';
import { api } from '../../lib/api';
import { date, label } from '../../lib/display';

export type Quality = { quality_check_id: string; target_type: string; status: string; text: string; input_hash: string; rule_version: string; supersedes_id: string | null; ai_run_id: string; policy_version_ids: string[]; findings: { rule_id: string; field_or_excerpt: string; evidence_ids: string[]; explanation: string; suggested_revision: string }[]; reviews?: { id: string; decision: string; reason: string; created_at: string }[] };

export function QualityReview({ id, onRevision }: { id: string; onRevision?: (id: string) => void }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ['quality', id], queryFn: () => api<Quality>(`/quality-checks/${id}`) });
  const review = useMutation({ mutationFn: (body: unknown) => api<{ revised_quality_check_id: string | null }>(`/quality-checks/${id}/reviews`, body), onSuccess: r => { void cache.invalidateQueries({ queryKey: ['quality', id] }); if (r.revised_quality_check_id) { void cache.invalidateQueries({ queryKey: ['qualities'] }); onRevision?.(r.revised_quality_check_id); } } });
  const q = query.data;
  return <div className="stack">
    {(query.error || review.error) && <Alert type="error" title={(query.error || review.error)?.message} />}
    {q && <>
      <Descriptions items={[{ key: 'status', label: '质检状态', children: <Tag data-testid="quality-status">{label(q.status)}</Tag> }, { key: 'rules', label: '规则版本', children: q.rule_version }]} />
      <Table size="small" pagination={false} rowKey={f => `${f.rule_id}:${f.field_or_excerpt}:${f.evidence_ids.join(',')}`} dataSource={q.findings} columns={[
        { title: '问题', dataIndex: 'explanation' }, { title: '定位', dataIndex: 'field_or_excerpt' }, { title: '建议', dataIndex: 'suggested_revision' },
      ]} locale={{ emptyText: '未发现确定性问题；请人工核实事实和客户需求。' }} />
      <details><summary>查看依据、原文与版本绑定</summary><pre>{JSON.stringify({ text: q.text, evidence: q.policy_version_ids, input_hash: q.input_hash, previous: q.supersedes_id, findings: q.findings }, null, 2)}</pre></details>
      <Form layout="vertical" initialValues={{ decision: 'CONFIRM' }} onFinish={review.mutate}>
        <Form.Item label="复核决定" name="decision"><Select options={['CONFIRM','REJECT','REVISE'].map(value => ({ value, label: label(value), disabled: value === 'CONFIRM' && q.status === 'BLOCKED' }))} /></Form.Item>
        <Form.Item label="复核原因" name="reason" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={2} /></Form.Item>
        <Form.Item label="修订稿（选择修订时必填）" name="revised_text"><Input.TextArea rows={3} /></Form.Item>
        <Button htmlType="submit" loading={review.isPending}>保存人工复核</Button>
      </Form>
      {q.status === 'BLOCKED' && <Alert type="warning" title="硬规则阻断不能跳过；请修订或重新生成方案。" />}
      {q.reviews?.map(r => <Typography.Paragraph key={r.id}>{date(r.created_at)} · {label(r.decision)}：{r.reason}</Typography.Paragraph>)}
    </>}
  </div>;
}
