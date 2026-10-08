import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Table, Typography } from 'antd';
import { api } from '../../lib/api';
import { date, label } from '../../lib/display';
type Run = { id: string; status: string; created_at: string; settings: { mode: string; model: string; split: string; purpose?: string; labels_confirmed: boolean; case_count: number }; metrics: { tp?: number; fp?: number; fn?: number; precision?: number | null; recall?: number | null; failed_cases: number } | null; results?: { case_id: string; status: string; input: unknown; actual_issue_ids: string[] | null; ai_run: unknown; error: string | null }[]; recovery_note?: string };
export function EvaluationPage() {
  const [id, setId] = useState<string>();
  const list = useQuery({ queryKey: ['evaluations'], queryFn: () => api<{ items: Run[] }>('/evaluation-runs') });
  const detail = useQuery({ queryKey: ['evaluation', id], queryFn: () => api<Run>(`/evaluation-runs/${id}`), enabled: !!id });
  return <div className="stack"><Alert type="info" title="评测记录只读；离线结果与未核对标签不能证明模型效果。真实评测需本地凭证、调用预算和已核对用例。保留集仅在版本冻结后查看。" />
    {(list.error || detail.error) && <Alert type="error" title={(list.error || detail.error)?.message} />}
    <Card title="版本评测批次" extra={<Button onClick={() => void list.refetch()}>刷新记录</Button>}><Table rowKey="id" dataSource={list.data?.items} columns={[
      { title: '时间', dataIndex: 'created_at', render: date }, { title: '模型 / 模式', render: (_, r) => `${r.settings.model} / ${r.settings.mode}` }, { title: '集合', render: (_, r) => `${r.settings.split} · ${r.settings.case_count} 条` },
      { title: '用途', render: (_, r) => r.settings.purpose === 'connection_smoke' ? '联网试跑（不计效果分）' : r.settings.mode === 'live' ? '正式评测' : '离线检查' }, { title: '标签', render: (_, r) => r.settings.labels_confirmed ? '已核对' : '待人工核对' }, { title: '状态', dataIndex: 'status', render: label }, { title: '查看', render: (_, r) => <Button onClick={() => setId(r.id)}>查看批次</Button> },
    ]} /></Card>
    {detail.data && <Card title="运行设置与逐条结果"><Typography.Paragraph>{detail.data.recovery_note}</Typography.Paragraph><pre>{JSON.stringify({ settings: detail.data.settings, metrics: detail.data.metrics }, null, 2)}</pre>
      <Typography.Paragraph type="secondary">{detail.data.settings.purpose === 'connection_smoke' ? '本批次仅检查真实调用与输出；标签仍待人工核对，不计算精确率、召回率或版本效果。' : '计数以问题类别为单位；失败样本单列，不进入精确率和召回率分母；没有可数 TN，不报告误报率。'}</Typography.Paragraph>
      <Table rowKey="case_id" dataSource={detail.data.results} columns={[{ title: '用例', dataIndex: 'case_id' }, { title: '状态', dataIndex: 'status', render: label }, { title: '检出问题', dataIndex: 'actual_issue_ids', render: v => v?.join('、') || '无结果 / 无问题' }, { title: '错误', dataIndex: 'error' }]} expandable={{ expandedRowRender: r => <pre>{JSON.stringify(r, null, 2)}</pre> }} />
    </Card>}
  </div>;
}
