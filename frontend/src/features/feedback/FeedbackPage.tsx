import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Checkbox, Form, Input, Select, Typography } from 'antd';
import { api } from '../../lib/api';

const tags = ['等待时间','解释清晰度','问题解决','办理体验'];
export function FeedbackPage() {
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  const submit = useMutation({ mutationFn: (body: object) => api('/public/feedback', { ...body, token }) });
  return <main className="login"><Card title="本次服务评价" style={{ width: 500, maxWidth: '100%' }}>
    <Typography.Paragraph>模拟服务环境 · 自愿评价，无需填写客户号码。</Typography.Paragraph>
    {!token ? <Alert type="error" title="评价链接无效，请向服务人员获取本次服务专属链接。" /> : submit.isSuccess ? <Alert type="success" title="评价已提交，感谢反馈。" /> : <Form layout="vertical" initialValues={{ tags: [] }} onFinish={submit.mutate}>
      <Form.Item label="满意度" name="score" rules={[{ required: true }]}><Select options={[1,2,3,4,5].map(value => ({ value, label: `${value} 分` }))} /></Form.Item>
      <Form.Item label="关注方面" name="tags"><Checkbox.Group options={tags} /></Form.Item><Form.Item label="意见（可选）" name="comment"><Input.TextArea rows={3} maxLength={2000} /></Form.Item>
      {submit.error && <Alert title={submit.error.message} type="error" />}<Button type="primary" htmlType="submit" loading={submit.isPending}>提交评价</Button>
    </Form>}
  </Card></main>;
}
export function FeedbackPanel({ sid, ended }: { sid: string; ended: boolean }) {
  const query = useQuery({ queryKey: ['feedback', sid], queryFn: () => api<{ feedback: { score: number; tags: string[]; comment: string } | null }>(`/service-sessions/${sid}/feedback`) });
  const issue = useMutation({ mutationFn: () => api<{ path: string; expires_at: string }>(`/service-sessions/${sid}/feedback-link`, {}) });
  return <Card title="客户评分（独立于系统质检）" extra={<Button onClick={() => void query.refetch()}>刷新评价</Button>}>
    {(query.error || issue.error) && <Alert type="error" title={(query.error || issue.error)?.message} />}
    {query.data?.feedback ? <Typography.Paragraph>{query.data.feedback.score} 分 · {query.data.feedback.tags.join('、')} · {query.data.feedback.comment}</Typography.Paragraph> : <>
      <Typography.Paragraph>尚未评价；未评价不补零分。</Typography.Paragraph><Button disabled={!ended} loading={issue.isPending} onClick={() => issue.mutate()}>生成客户评价链接</Button>
      {!ended && <Typography.Paragraph type="secondary">结束接待后可以邀请评价。</Typography.Paragraph>}
      {issue.data && <Typography.Paragraph style={{ marginTop: 12 }}><a href={issue.data.path} target="_blank" rel="noreferrer">打开本次服务评价页</a> · 链接有效 24 小时</Typography.Paragraph>}
    </>}
  </Card>;
}
