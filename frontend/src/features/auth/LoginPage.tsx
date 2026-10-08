import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, setCsrfToken } from '../../lib/api';

export type User = { user_id: string; store_id: string; username: string; role: 'STAFF' | 'MANAGER' | 'ADMIN' | 'WAREHOUSE' | 'INSTALLER' | 'FINANCE'; csrf_token: string };

export function LoginPage() {
  const cache = useQueryClient();
  const login = useMutation({
    mutationFn: (data: { username: string; password: string }) => api<User>('/auth/login', data),
    onSuccess: user => { setCsrfToken(user.csrf_token); cache.setQueryData(['me'], user); },
  });
  return <main className="login"><Card style={{ width: 400, maxWidth: '100%' }}>
    <Typography.Text type="secondary">营业厅 · 模拟服务环境</Typography.Text>
    <Typography.Title level={2}>登录服务工作台</Typography.Title>
    <Typography.Paragraph type="secondary">使用本地初始化的店员、店长或管理员账号。</Typography.Paragraph>
    <Form layout="vertical" onFinish={login.mutate}>
      <Form.Item label="用户名" name="username" rules={[{ required: true }]}><Input autoComplete="username" /></Form.Item>
      <Form.Item label="口令" name="password" rules={[{ required: true }]}><Input.Password autoComplete="current-password" /></Form.Item>
      {login.error && <Alert title={login.error.message} type="error" showIcon />}
      <Button type="primary" htmlType="submit" loading={login.isPending} block style={{ marginTop: 16 }}>登录</Button>
    </Form>
  </Card></main>;
}
