import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Input, Select, Table } from 'antd';
import { api } from '../../lib/api';
import { label as commonLabel, money } from '../../lib/display';
import type { Customer } from '../../lib/business';
import type { User } from '../auth/LoginPage';
type Transaction = { id: string; title: string; customer_id: string; status: string; required: string[]; remaining: string[]; original_amount: string; refunded_amount: string; net_amount: string | null; children: { id: string; link_id: string; kind: string; state: string; completed: boolean; attention: boolean; url: string; resolution_note: string }[] };
type Sources = { orders: { id: string; label: string }[]; acceptances: { id: string; label: string }[]; installations: { id: string; label: string }[] };
const names: Record<string,string> = { SALE: '商品 / 服务销售', TELECOM: '通信办理', INSTALLATION: '安装交付' };
const label = (value: string) => ({ PARTIAL:'部分完成',COMPLETED:'已完成',BLOCKED:'施工受阻' }[value] || commonLabel(value));

export function TransactionPage({ user }: { user: User }) {
  const cache = useQueryClient(), [params,setParams] = useSearchParams(), [form] = Form.useForm(), [key,setKey] = useState(() => crypto.randomUUID());
  const id = params.get('id'), customer = Form.useWatch('customer_id',form);
  const rows = useQuery({ queryKey: ['transactions'], queryFn: () => api<{ items: Transaction[] }>('/transactions') });
  const detail = useQuery({ queryKey: ['transaction',id], queryFn: () => api<Transaction>(`/transactions/${id}`), enabled: !!id });
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => api<{ items: Customer[] }>('/customers') });
  const sourceCustomer = id ? detail.data?.customer_id : customer;
  const sources = useQuery({ queryKey: ['transaction-sources',sourceCustomer], queryFn: () => api<Sources>(`/transactions/sources?customer_id=${sourceCustomer}`), enabled: !!sourceCustomer });
  const refresh = async () => { await Promise.all(['transactions','transaction','todos'].map(k => cache.invalidateQueries({ queryKey: [k] }))); };
  const create = useMutation({ mutationFn: (v: object) => api<Transaction>('/transactions',{ ...v,request_key:key }), onSuccess: async r => { setParams({ id:r.id }); setKey(crypto.randomUUID()); await refresh(); } });
  const link = useMutation({ mutationFn: (v: object) => api(`/transactions/${id}/links`,v), onSuccess: refresh });
  const resolve = useMutation({ mutationFn: (v: object) => api(`/transactions/${id}/resolve-component`,v), onSuccess: refresh });
  const fields = (prefix: string) => <>{(['orders','acceptances','installations'] as const).map((kind,i) => <Form.Item key={kind} name={['order_ids','acceptance_ids','installation_ids'][i]} label={['销售子单','通信子单','安装子单'][i]}><Select mode="multiple" showSearch optionFilterProp="label" options={sources.data?.[kind].map(o => ({ value:o.id,label:o.label }))} aria-label={prefix+['销售子单','通信子单','安装子单'][i]} /></Form.Item>)}</>;
  const row = detail.data, error = rows.error || detail.error || customers.error || sources.error || create.error || link.error || resolve.error;
  return <div className="stack">{error && <Alert type="error" title={error.message} />}<Card title="组合交易" extra={<Button onClick={() => void refresh()}>刷新组合状态</Button>}><Table rowKey="id" dataSource={rows.data?.items} columns={[{ title:'交易',dataIndex:'title' },{ title:'整体进度',dataIndex:'status',render:label },{ title:'原金额',dataIndex:'original_amount',render:money },{ title:'已退款',dataIndex:'refunded_amount',render:money },{ title:'操作',render:(_,r)=><Button onClick={() => setParams({ id:r.id })}>查看组合</Button> }]} /></Card>
    {row && <Card title={row.title}><p>{label(row.status)} · 原金额 {money(row.original_amount)} · 已退 {money(row.refunded_amount)} · 净收 {money(row.net_amount)}</p>{row.remaining.length>0 && <Alert type="warning" title={`仍须关联：${row.remaining.map(k=>names[k]).join('、')}`} />}<Table rowKey="link_id" dataSource={row.children} pagination={false} columns={[{ title:'子业务',dataIndex:'kind',render:k=>names[k] },{ title:'各自状态',dataIndex:'state',render:s=>s.split('/').map(label).join(' / ') },{ title:'交付',render:(_,r)=>r.attention?'需处理异常':r.completed?'已完成':'处理中' },{ title:'异常处理依据',dataIndex:'resolution_note' },{ title:'原单',render:(_,r)=><a href={r.url}>打开子单</a> }]} /><Form name="transaction-links" layout="vertical" onFinish={link.mutate}>{fields('补充')}<Button htmlType="submit" loading={link.isPending}>关联后续子单</Button></Form>
      {['MANAGER','ADMIN'].includes(user.role) && <details><summary>记录失败或已取消子单的处理依据</summary><Form name="transaction-resolution" layout="vertical" onFinish={resolve.mutate}><Form.Item name="link_id" label="已核实的异常子单" rules={[{ required:true }]}><Select options={row.children.filter(c=>!c.resolution_note).map(c=>({ value:c.link_id,label:`${names[c.kind]} ${c.id.slice(0,8)} · ${c.state}` }))} /></Form.Item><Form.Item name="replacement_link_id" label="替代子单（取消该项时可不选）"><Select allowClear options={row.children.filter(c=>!c.resolution_note).map(c=>({ value:c.link_id,label:`${names[c.kind]} ${c.id.slice(0,8)}` }))} /></Form.Item><Form.Item name="note" label="客户确认、补偿或替代交付依据" rules={[{ required:true,whitespace:true }]}><Input.TextArea /></Form.Item><Button htmlType="submit" loading={resolve.isPending}>确认异常处理依据</Button></Form></details>}
    </Card>}
    <Card title="新建组合交易" extra={id && <Button onClick={() => setParams({})}>切换到新建</Button>}><Form name="transaction-create" form={form} layout="vertical" initialValues={{ required:['SALE'] }} onFinish={create.mutate} disabled={!!id}><Form.Item name="title" label="交易说明" rules={[{ required:true,whitespace:true }]}><Input placeholder="例如：宽带升级、路由器和上门安装" /></Form.Item><Form.Item name="customer_id" label="客户" rules={[{ required:true }]}><Select showSearch optionFilterProp="label" options={customers.data?.items.map(c=>({ value:c.id,label:c.display_name }))} onChange={() => form.setFieldsValue({ order_ids:[],acceptance_ids:[],installation_ids:[] })} /></Form.Item><Form.Item name="required" label="约定需要交付的业务" rules={[{ required:true }]}><Select mode="multiple" options={Object.entries(names).map(([value,label])=>({ value,label }))} /></Form.Item>{fields('新建')}<Button type="primary" htmlType="submit" loading={create.isPending}>建立组合交易</Button></Form></Card>
  </div>;
}
