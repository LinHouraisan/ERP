import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Checkbox, Descriptions, Form, Input, InputNumber, Select, Space, Table, Tag } from 'antd';
import { api } from '../../lib/api';
import type { User } from '../auth/LoginPage';

type Product = { id: string; name: string; kind: string };
type Policy = { id: string; version: number; status: string; monthly_fee: string | null; one_time_fee: string | null; contract_months: number; promotion_months: number | null; broadband: boolean | null; conditions: { verified_required: boolean; new_customer_only: boolean; minimum_tenure_months: number; excludes_discount: string | null }; valid_from: string; valid_to: string; source: string };

export function CatalogPage({ user }: { user: User }) {
  const [pid, setPid] = useState<string>();
  const [editing, setEditing] = useState<string>();
  const [policyForm] = Form.useForm();
  const cache = useQueryClient();
  const products = useQuery({ queryKey: ['products'], queryFn: () => api<{ items: Product[] }>('/products') });
  const policies = useQuery({ queryKey: ['policies', pid], queryFn: () => api<{ items: Policy[] }>(`/products/${pid}/policy-versions`), enabled: !!pid });
  const write = useMutation({ mutationFn: ({ path, body }: { path: string; body: unknown }) => api(path, body), onSuccess: () => { void cache.invalidateQueries({ queryKey: ['products'] }); void cache.invalidateQueries({ queryKey: ['policies', pid] }); } });
  return <div className="stack">
    {(products.error || policies.error || write.error) && <Alert type="error" title={(products.error || policies.error || write.error)?.message} showIcon />}
    <Card title="产品与政策版本"><Select aria-label="选择产品" showSearch optionFilterProp="label" style={{ width: '100%', maxWidth: 420 }} placeholder="选择产品，查看当时政策" value={pid} onChange={id => { setPid(id); setEditing(undefined); policyForm.resetFields(); }} options={products.data?.items.map(p => ({ value: p.id, label: `${p.name} · ${p.kind}` }))} />
      {pid && <Table rowKey="id" dataSource={policies.data?.items} scroll={{ x: 800 }} expandable={{ expandedRowRender: p => <Descriptions column={1} items={[
        { key: 'verified', label: '实名要求', children: p.conditions.verified_required ? '需要' : '不要求' }, { key: 'new', label: '新客限定', children: p.conditions.new_customer_only ? '仅限新客' : '不限' },
        { key: 'tenure', label: '最少在网月数', children: p.conditions.minimum_tenure_months }, { key: 'excludes', label: '互斥优惠', children: p.conditions.excludes_discount || '无' }, { key: 'promotion', label: '优惠月数', children: p.promotion_months ?? '未单列期限' },
      ]} /> }} columns={[
        { title: '版本', dataIndex: 'version' }, { title: '状态', dataIndex: 'status', render: s => <Tag>{s}</Tag> },
        { title: '月费', dataIndex: 'monthly_fee', render: v => v ?? '未知' }, { title: '一次费', dataIndex: 'one_time_fee', render: v => v ?? '未知' },
        { title: '合约月数', dataIndex: 'contract_months' }, { title: '生效日', dataIndex: 'valid_from' }, { title: '截止日', dataIndex: 'valid_to' }, { title: '来源', dataIndex: 'source' },
        { title: '操作', render: (_, p) => <Space><Button disabled={p.status === 'PUBLISHED' || user.role !== 'ADMIN'} loading={write.isPending} onClick={() => write.mutate({ path: `/policy-versions/${p.id}/publish`, body: {} })}>{p.status === 'PUBLISHED' ? '已发布不可覆盖' : '发布版本'}</Button>{p.status === 'DRAFT' && user.role === 'ADMIN' && <Button onClick={() => { setEditing(p.id); policyForm.setFieldsValue(p); }}>编辑草稿</Button>}</Space> },
      ]} />}</Card>
    {user.role === 'ADMIN' && <Card title="新建产品"><Form layout="inline" onFinish={v => write.mutate({ path: '/products', body: v })} initialValues={{ kind: 'PACKAGE', tracking: 'NONE' }}>
      <Form.Item label="产品名称" name="name" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="sku" label="两店共用商品编码" rules={[{ pattern:/^[A-Z0-9_-]+$/,message:'使用大写字母、数字、下划线或短横线' }]}><Input placeholder="需调拨的商品填写" /></Form.Item><Form.Item name="kind" label="类型"><Select style={{ width: 120 }} options={[{ value: 'PACKAGE', label: '套餐' }, { value: 'SERVICE', label: '服务' }, { value: 'GOODS', label: '实物商品' }]} /></Form.Item><Form.Item name="tracking" label="库存管理"><Select style={{ width: 160 }} options={[{ value: 'NONE', label: '套餐 / 服务不计库存' }, { value: 'QUANTITY', label: '实物按数量' }, { value: 'SERIAL', label: '实物按序列号' }]} /></Form.Item><Button htmlType="submit" loading={write.isPending}>新建产品</Button>
    </Form></Card>}
    {user.role === 'ADMIN' && pid && <Card title={editing ? '编辑未发布草稿' : '新增政策草稿（保留所有历史版本）'} extra={editing && <Button onClick={() => { setEditing(undefined); policyForm.resetFields(); }}>另建新版本</Button>}><Form form={policyForm} layout="vertical" initialValues={{ contract_months: 0, broadband: true, source: '本地模拟政策', valid_from: '2026-10-02', valid_to: '2027-12-31', conditions: { verified_required: true, new_customer_only: false, minimum_tenure_months: 0 } }} onFinish={v => write.mutate({ path: editing ? `/policy-versions/${editing}/edit` : `/products/${pid}/policy-versions`, body: { ...v, monthly_fee: v.monthly_fee || null, one_time_fee: v.one_time_fee || null, conditions: { ...v.conditions, excludes_discount: v.conditions.excludes_discount || null } } })}>
      <div className="grid"><Form.Item label="月费，留空为未知" name="monthly_fee"><Input /></Form.Item><Form.Item label="一次费，留空为未知" name="one_time_fee"><Input /></Form.Item>
      <Form.Item label="合约月数" name="contract_months" rules={[{ required: true }]}><InputNumber min={0} max={120} /></Form.Item>
      <Form.Item label="优惠月数（留空表示未单列）" name="promotion_months"><InputNumber min={1} max={120} /></Form.Item>
      <Form.Item label="是否包含宽带" name="broadband"><Select options={[{ value: true, label: '包含' }, { value: false, label: '不含' }]} /></Form.Item>
      <Form.Item label="生效日" name="valid_from" rules={[{ required: true }]}><Input type="date" /></Form.Item><Form.Item label="截止日" name="valid_to" rules={[{ required: true }]}><Input type="date" /></Form.Item>
      <Form.Item label="政策来源" name="source" rules={[{ required: true }]}><Input /></Form.Item>
      <Form.Item label="最少在网月数" name={['conditions','minimum_tenure_months']}><InputNumber min={0} /></Form.Item><Form.Item label="互斥优惠代码" name={['conditions','excludes_discount']}><Input /></Form.Item>
      <Form.Item label="适用地区（留空不限；本店为演示市）" name={['conditions','region']}><Input /></Form.Item>
      <Form.Item label="每件一次费优惠金额" name={['conditions','sale_discount']} initialValue="0.00"><Input /></Form.Item>
      <Form.Item label="一次费收款分类" name={['conditions','receipt_category']} initialValue="OPERATING"><Select options={[{ value: 'OPERATING', label: '经营类收入' }, { value: 'COLLECTION', label: '代收款' }, { value: 'DEPOSIT', label: '押金' }]} /></Form.Item>
      <Form.Item name={['conditions','verified_required']} valuePropName="checked"><Checkbox>需要实名核验</Checkbox></Form.Item><Form.Item name={['conditions','new_customer_only']} valuePropName="checked"><Checkbox>仅限新客户</Checkbox></Form.Item></div><Button htmlType="submit" type="primary" loading={write.isPending}>保存政策草稿</Button>
    </Form></Card>}
  </div>;
}
