import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Typography } from 'antd';
import { api } from '../../lib/api';
import { date, label, money } from '../../lib/display';
import type { User } from '../auth/LoginPage';

type Product = { id: string; name: string; kind: string; tracking: string };
type Purchase = { id: string; status: string; supplier_name: string; total: string; created_at: string; lines: { id: string; product_id: string; quantity: number; received_quantity: number; unit_cost: string }[]; receipts?: unknown[] };
type Stock = { product_id: string; name: string; tracking: string; quantity: number; reserved: number; available: number };

function Receiving({ purchase, products, done }: { purchase: Purchase; products: Product[]; done: () => Promise<unknown> }) {
  const [key, setKey] = useState(() => crypto.randomUUID());
  const receive = useMutation({ mutationFn: (v: { lines: { line_id: string; quantity: number; serials?: string }[] }) => api(`/inventory/purchases/${purchase.id}/receive`, { request_key: key, lines: v.lines.filter(l => l.quantity > 0).map(l => ({ ...l, serials: l.serials?.trim().split(/\s+/).filter(Boolean) || [] })) }), onSuccess: async () => { await done(); setKey(crypto.randomUUID()); } });
  return <>{receive.error && <Alert type="error" title={receive.error.message} />}
    <Form key={purchase.lines.map(l => l.received_quantity).join('-')} layout="vertical" disabled={receive.isPending} initialValues={{ lines: purchase.lines.map(l => ({ line_id: l.id, quantity: 0 })) }} onFinish={receive.mutate}>
      <Typography.Paragraph>填写本次实际到货数量，未到货填 0。每个设备序列号占一行。</Typography.Paragraph>
      {purchase.lines.map((l, i) => <div className="grid" key={l.id}><Form.Item name={['lines', i, 'line_id']} hidden><Input /></Form.Item>
        <Form.Item label={`${products.find(p => p.id === l.product_id)?.name || l.product_id} · 待收 ${l.quantity-l.received_quantity}`} name={['lines', i, 'quantity']}><InputNumber min={0} max={l.quantity-l.received_quantity} precision={0} /></Form.Item>
        {products.find(p => p.id === l.product_id)?.tracking === 'SERIAL' && <Form.Item label="本次设备序列号" name={['lines', i, 'serials']}><Input.TextArea rows={2} /></Form.Item>}
      </div>)}<Button type="primary" htmlType="submit" loading={receive.isPending}>确认本次收货入库</Button>
    </Form></>;
}

export function InventoryPage({ user }: { user: User }) {
  const cache = useQueryClient();
  const [id, setId] = useState<string>(), [sku, setSku] = useState<string | undefined>(new URLSearchParams(location.search).get('id') || undefined);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [form] = Form.useForm();
  const products = useQuery({ queryKey: ['products'], queryFn: () => api<{ items: Product[] }>('/products?page_size=100') });
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: () => api<{ items: { id: string; name: string }[] }>('/inventory/suppliers') });
  const purchases = useQuery({ queryKey: ['purchases'], queryFn: () => api<{ items: Purchase[] }>('/inventory/purchases') });
  const detail = useQuery({ queryKey: ['purchase', id], queryFn: () => api<Purchase>(`/inventory/purchases/${id}`), enabled: !!id });
  const stock = useQuery({ queryKey: ['stock'], queryFn: () => api<{ items: Stock[] }>('/inventory/stock') });
  const serials = useQuery({ queryKey: ['serials', sku], queryFn: () => api<{ items: { id: string; serial: string; status: string; order_id?: string; installation_id?: string }[] }>(`/inventory/serials?product_id=${sku}`), enabled: !!sku });
  const movements = useQuery({ queryKey: ['movements', sku], queryFn: () => api<{ items: { id: string; quantity: number; receipt_id: string | null; order_id: string | null; installation_id: string | null; serials: string[]; created_at: string }[] }>(`/inventory/movements${sku ? '?product_id='+sku : ''}`) });
  const refresh = async () => { await Promise.all(['purchases','purchase','stock','serials','movements'].map(k => cache.invalidateQueries({ queryKey: [k] }))); };
  const supplier = useMutation({ mutationFn: (v: object) => api('/inventory/suppliers', v), onSuccess: () => cache.invalidateQueries({ queryKey: ['suppliers'] }) });
  const create = useMutation({ mutationFn: (v: object) => api<Purchase>('/inventory/purchases', { ...v, request_key: key }), onSuccess: async r => { setId(r.id); setKey(crypto.randomUUID()); form.resetFields(); await refresh(); } });
  const approve = useMutation({ mutationFn: (pid: string) => api(`/inventory/purchases/${pid}/approve`, {}), onSuccess: refresh });
  const error = products.error || suppliers.error || purchases.error || detail.error || stock.error || movements.error || serials.error || supplier.error || create.error || approve.error;
  const goods = products.data?.items.filter(p => p.kind === 'GOODS') || [];
  return <div className="stack">{error && <Alert title={error.message} type="error" />}
    <Card title="库存与设备" extra={<Button onClick={() => void refresh()}>刷新库存</Button>}><Table rowKey="product_id" dataSource={stock.data?.items} columns={[
      { title: '商品', dataIndex: 'name' }, { title: '管理方式', dataIndex: 'tracking', render: label }, { title: '在库', dataIndex: 'quantity' }, { title: '已占用', dataIndex: 'reserved' }, { title: '可用', dataIndex: 'available' }, { title: '查看', render: (_, r) => <Button onClick={() => setSku(r.product_id)}>设备与流水</Button> },
    ]} />{sku && <Table rowKey="id" dataSource={serials.data?.items} columns={[{ title: '序列号', dataIndex: 'serial' }, { title: '状态', dataIndex: 'status', render: label }, { title: '去向', render: (_, r) => r.order_id ? <a href={`/sales?id=${r.order_id}`}>销售单</a> : r.installation_id ? <a href={`/installations?id=${r.installation_id}`}>安装工单</a> : '在库' }]} />}</Card>
    <Card title="库存流水"><Table rowKey="id" dataSource={movements.data?.items} columns={[{ title: '时间', dataIndex: 'created_at', render: date }, { title: '增减数量', dataIndex: 'quantity' }, { title: '序列号', dataIndex: 'serials', render: v => v.join('、') || '数量商品' }, { title: '来源', render: (_, r) => r.order_id ? <a href={`/sales?id=${r.order_id}`}>销售出库</a> : r.installation_id ? <a href={`/installations?id=${r.installation_id}`}>安装领料</a> : `入库单 ${r.receipt_id?.slice(0, 8)}` }]} /></Card>
    <Card title="采购单"><Table rowKey="id" dataSource={purchases.data?.items} columns={[{ title: '供应商', dataIndex: 'supplier_name' }, { title: '金额', dataIndex: 'total', render: money }, { title: '状态', dataIndex: 'status', render: label }, { title: '创建时间', dataIndex: 'created_at', render: date }, { title: '操作', render: (_, r) => <Space><Button onClick={() => setId(r.id)}>查看 / 收货</Button>{r.status === 'DRAFT' && user.role !== 'WAREHOUSE' && <Button loading={approve.isPending} onClick={() => approve.mutate(r.id)}>审核通过</Button>}</Space> }]} /></Card>
    {detail.data && <Card title={`采购详情 · ${detail.data.supplier_name}`}><Table rowKey="id" pagination={false} dataSource={detail.data.lines} columns={[{ title: '商品', dataIndex: 'product_id', render: v => goods.find(g => g.id === v)?.name || v }, { title: '采购数量', dataIndex: 'quantity' }, { title: '已收数量', dataIndex: 'received_quantity' }, { title: '进价', dataIndex: 'unit_cost', render: money }]} />
      {['APPROVED','PARTIAL'].includes(detail.data.status) && <Receiving key={detail.data.id} purchase={detail.data} products={goods} done={refresh} />}<details><summary>收货依据与经手记录</summary><pre>{JSON.stringify(detail.data.receipts, null, 2)}</pre></details></Card>}
    <Card title="新建采购"><Form form={form} layout="vertical" initialValues={{ lines: [{ quantity: 1, unit_cost: '0.00' }] }} onFinish={create.mutate} disabled={create.isPending}>
      <Form.Item name="supplier_id" label="供应商" rules={[{ required: true }]}><Select options={suppliers.data?.items.map(s => ({ value: s.id, label: s.name }))} /></Form.Item>
      <Form.List name="lines">{(fields, { add, remove }) => <>{fields.map(f => <div className="grid" key={f.key}><Form.Item name={[f.name, 'product_id']} label="商品" rules={[{ required: true }]}><Select options={goods.map(p => ({ value: p.id, label: p.name }))} /></Form.Item><Form.Item name={[f.name,'quantity']} label="数量" rules={[{ required: true }]}><InputNumber min={1} max={10000} precision={0} /></Form.Item><Form.Item name={[f.name,'unit_cost']} label="采购单价" rules={[{ required: true }]}><Input /></Form.Item><Button onClick={() => remove(f.name)} disabled={fields.length === 1}>删除行</Button></div>)}<Button onClick={() => add({ quantity: 1, unit_cost: '0.00' })}>增加商品</Button></>}</Form.List>
      <Button type="primary" htmlType="submit" loading={create.isPending} style={{ marginTop: 16 }}>保存采购草稿</Button></Form></Card>
    <Card title="新增供应商"><Form layout="inline" onFinish={supplier.mutate} initialValues={{ contact: '' }}><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="contact" label="联系人 / 联系方式"><Input /></Form.Item><Button htmlType="submit" loading={supplier.isPending}>保存供应商</Button></Form></Card>
  </div>;
}
