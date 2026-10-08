import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Form, Input, InputNumber, Select, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../lib/api';
import { date, label, money } from '../../lib/display';
import type { Customer, Offer, Order } from '../../lib/business';
import type { User } from '../auth/LoginPage';

type Close = { id: string; business_day: string; cashier_id: string; counted_cash: string; difference: string; confirmed_by: string | null; totals: { methods: Record<string,string>; categories: Record<string,string>; payment_ids: string[]; refunds: string; refund_methods?: Record<string,string>; net_methods?: Record<string,string> }; note: string; payments: { id: string; order_id: string; amount: string; method: string }[]; refund_records: { id: string; order_id: string; amount: string }[] };
type Draft = { status: string; error: string | null; output: { items: { policy_version_id: string; quantity: number; reason: string }[]; note: string } | null };

function DayClose({ user }: { user: User }) {
  const cache = useQueryClient();
  const [key, setKey] = useState(() => crypto.randomUUID());
  const rows = useQuery({ queryKey: ['day-closes'], queryFn: () => api<{ items: Close[] }>('/sales/day-closes') });
  const staff = useQuery({ queryKey: ['cashiers'], queryFn: () => api<{ items: { id: string; username: string }[] }>('/sales/cashiers') });
  const create = useMutation({ mutationFn: (v: object) => api('/sales/day-closes', { ...v, request_key: key }), onSuccess: async () => { setKey(crypto.randomUUID()); await cache.invalidateQueries({ queryKey: ['day-closes'] }); } });
  const review = useMutation({ mutationFn: ({ id, note }: { id: string; note: string }) => api(`/sales/day-closes/${id}/confirm`, { note }), onSuccess: () => cache.invalidateQueries({ queryKey: ['day-closes'] }) });
  return <Card title="日结与班次交接">{(rows.error || staff.error || create.error || review.error) && <Alert type="error" title={(rows.error || staff.error || create.error || review.error)?.message} />}
    <Typography.Paragraph type="secondary">每笔成功收款和退款分别只交接一次；先核清未知结果。填写本次净交接现金，退款支出大于收款时可为负，非现金按支付方式单列。</Typography.Paragraph>
    <Form layout="inline" onFinish={create.mutate} initialValues={{ cashier_id: user.role !== 'FINANCE' ? user.user_id : undefined, business_day: new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }), counted_cash: '0.00' }}>
      <Form.Item name="cashier_id" label="收银员" rules={[{ required: true }]}><Select style={{ width: 180 }} options={staff.data?.items.map(u => ({ value: u.id, label: u.username }))} /></Form.Item><Form.Item name="business_day" label="营业日" rules={[{ required: true }]}><Input type="date" /></Form.Item><Form.Item name="counted_cash" label="交接现金" rules={[{ required: true }]}><Input style={{ width: 120 }} /></Form.Item><Button htmlType="submit" loading={create.isPending}>生成交接记录</Button>
    </Form><Table rowKey="id" dataSource={rows.data?.items} style={{ marginTop: 16 }} expandable={{ expandedRowRender: r => <><Descriptions items={Object.entries(r.totals.methods).map(([k,v]) => ({ key: k, label: label(k), children: money(v) }))} /><Descriptions items={Object.entries(r.totals.categories).map(([k,v]) => ({ key: k, label: label(k), children: money(v) }))} /><Table rowKey="id" pagination={false} dataSource={r.payments} columns={[{ title: '本次交接收款', dataIndex: 'amount', render: money }, { title: '支付方式', dataIndex: 'method', render: label }, { title: '原始单据', render: (_, p) => <a href={`/sales?id=${p.order_id}`}>查看收款订单</a> }]} />{!r.confirmed_by && user.role !== 'STAFF' && <Form name={`close-review-${r.id}`} layout="inline" onFinish={v => review.mutate({ id: r.id, note: v.note })}><Form.Item name="note" label="核对说明" rules={[{ required: true }]}><Input placeholder="有差异时说明核查结果" /></Form.Item><Button htmlType="submit" loading={review.isPending}>确认交接记录</Button></Form>}{r.note}</> }} columns={[
      { title: '营业日', dataIndex: 'business_day' }, { title: '现金交接', dataIndex: 'counted_cash', render: money }, { title: '现金差异', dataIndex: 'difference', render: money }, { title: '状态', dataIndex: 'confirmed_by', render: v => v ? '已确认' : '待核对' },
    ]} /><details><summary>本次交接的退款来源与净收款</summary>{rows.data?.items.filter(r=>r.refund_records?.length).map(r=><Card size="small" key={r.id} title={`${r.business_day} · 退款 ${money(r.totals.refunds)}`}><Descriptions items={Object.entries(r.totals.net_methods || {}).map(([k,v])=>({ key:k,label:`${label(k)}净额`,children:money(v) }))} />{r.refund_records.map(a=><p key={a.id}><a href={`/aftersales?id=${a.id}`}>查看售后退款 {money(a.amount)}</a> · <a href={`/sales?id=${a.order_id}`}>原收款订单</a></p>)}</Card>)}</details></Card>;
}

export function SalesPage({ user }: { user: User }) {
  const cache = useQueryClient(), [params, setParams] = useSearchParams();
  const id = params.get('id') || undefined;
  const canSell = ['STAFF','MANAGER','ADMIN'].includes(user.role), canShip = ['WAREHOUSE','MANAGER','ADMIN'].includes(user.role);
  const [form] = Form.useForm();
  const [key, setKey] = useState(() => crypto.randomUUID());
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => api<{ items: Customer[] }>('/customers'), enabled: canSell });
  const offers = useQuery({ queryKey: ['offers'], queryFn: () => api<{ items: Offer[] }>('/sales/offers'), enabled: canSell });
  const rows = useQuery({ queryKey: ['orders'], queryFn: () => api<{ items: Order[] }>('/sales/orders') });
  const detail = useQuery({ queryKey: ['order', id], queryFn: () => api<Order>(`/sales/orders/${id}`), enabled: !!id });
  const refresh = async () => { await Promise.all(['orders','order','stock','earnings'].map(k => cache.invalidateQueries({ queryKey: [k] }))); };
  const create = useMutation({ mutationFn: (v: object) => api<Order>('/sales/orders', { ...v, request_key: key, source_service_id: params.get('source_service_id'), source_acceptance_id: params.get('source_acceptance_id') }), onSuccess: async r => { setParams({ id: r.id }); setKey(crypto.randomUUID()); await refresh(); } });
  const change = useMutation({ mutationFn: ({ path, body }: { path: string; body: object }) => api(path, body), onSuccess: refresh });
  const draft = useMutation({ mutationFn: async (v: { text: string }) => { const c = form.getFieldValue('customer_id'); if (!c) throw new Error('先在订单表单选择客户'); return api<Draft>('/sales/assist', { ...v, request_key: crypto.randomUUID(), customer_id: c, source_service_id: params.get('source_service_id') }); } });
  const order = detail.data;
  const error = customers.error || offers.error || rows.error || detail.error || create.error || change.error || draft.error;
  return <div className="stack">{error && <Alert title={error.message} type="error" />}
    <Card title="销售订单" extra={<Button onClick={() => void refresh()}>刷新单据</Button>}><Table rowKey="id" dataSource={rows.data?.items} columns={[
      { title: '商品 / 服务', render: (_, r) => r.lines.map(l => `${l.snapshot.name} × ${l.quantity}`).join('、') }, { title: '应收金额', dataIndex: 'total', render: money }, { title: '确认', dataIndex: 'status', render: label }, { title: '收款', render: (_, r) => r.payment ? r.payment.status === 'SUCCESS' ? '已收款' : label(r.payment.status) : '未收款' }, { title: '出库', dataIndex: 'stock_status', render: label }, { title: '查看', render: (_, r) => <Button onClick={() => setParams({ id: r.id })}>打开订单</Button> },
    ]} /></Card>
    {order && <Card title={`订单详情 · ${order.id.slice(0,8)}`}>
      <Descriptions items={[{ key: 'total', label: '后端核定应收', children: money(order.total) }, { key: 'status', label: '订单状态', children: label(order.status) }, { key: 'time', label: '创建时间', children: date(order.created_at) }]} />
      <Table rowKey="id" pagination={false} dataSource={order.lines} columns={[{ title: '商品', render: (_, r) => r.snapshot.name }, { title: '数量', dataIndex: 'quantity' }, { title: '单价', dataIndex: 'unit_price', render: money }, { title: '每件优惠', dataIndex: 'discount', render: money }, { title: '行应收', dataIndex: 'amount', render: money }, { title: '归类', render: (_, r) => label(r.snapshot.receipt_category) }, { title: '价格依据', render: (_, r) => `V${r.snapshot.version} · ${r.snapshot.source}` }]} />
      <Space wrap style={{ margin: '16px 0' }}>{canSell && order.status === 'DRAFT' && <Button type="primary" loading={change.isPending} onClick={() => change.mutate({ path: `/sales/orders/${order.id}/confirm`, body: {} })}>核对金额并确认订单</Button>}
        {canSell && order.status !== 'CANCELLED' && (!order.payment || order.payment.status === 'FAILED') && <Button danger onClick={() => change.mutate({ path: `/sales/orders/${order.id}/cancel`, body: {} })}>取消未收款订单</Button>}
        {canShip && order.payment?.status === 'SUCCESS' && order.stock_status === 'RESERVED' && <Button type="primary" loading={change.isPending} onClick={() => change.mutate({ path: `/sales/orders/${order.id}/dispatch`, body: {} })}>确认设备出库</Button>}
        {canSell && <Button href={`/customers?id=${order.customer_id}`}>客户全景</Button>}{order.source_service_id && canSell && <Button href={`/services?id=${order.source_service_id}`}>来源接待</Button>}
        {canSell && order.payment?.status === 'SUCCESS' && <Button href={`/installations?source_order_id=${order.id}`}>预约安装</Button>}
        {canSell && order.payment?.status === 'SUCCESS' && <Button href={`/aftersales?order_id=${order.id}`}>申请售后退款</Button>}
        {['FINANCE','MANAGER','ADMIN'].includes(user.role) && order.payment?.status === 'SUCCESS' && <Button onClick={() => change.mutate({ path: '/finance/accruals', body: { source_type: 'SALE', source_id: order.id } })}>计入收益台账</Button>}
      </Space>
      {order.after_sales?.map(a=><p key={a.id}><a href={`/aftersales?id=${a.id}`}>售后 {money(a.amount)} · {label(a.status)} / {a.refund_status==='NONE'?'未退款':label(a.refund_status)}</a></p>)}
      {canSell && order.status === 'CONFIRMED' && !order.payment && <Form layout="inline" initialValues={{ method: 'WECHAT', scenario: 'NORMAL' }} onFinish={v => change.mutate({ path: `/sales/orders/${order.id}/pay`, body: v })}>
        <Form.Item name="method" label="付款方式"><Select style={{ width: 130 }} options={['CASH','CARD','WECHAT','ALIPAY'].map(value => ({ value, label: label(value) }))} /></Form.Item><Form.Item name="scenario" label="模拟情形"><Select style={{ width: 170 }} options={[{ value: 'NORMAL', label: '正常收款' }, { value: 'SUCCESS_TIMEOUT', label: '到账后返回超时' }, { value: 'DECLINED', label: '模拟拒付' }]} /></Form.Item><Button type="primary" htmlType="submit" loading={change.isPending}>提交模拟收款</Button>
      </Form>}
      {order.payment && <><Alert type={order.payment.status === 'SUCCESS' ? 'success' : 'warning'} title={`收款：${order.payment.status === 'SUCCESS' ? '已收款' : label(order.payment.status)} · ${money(order.payment.amount)} · ${label(order.payment.method)}`} description={order.payment.last_error} style={{ marginTop: 12 }} />
        {['UNKNOWN','PENDING'].includes(order.payment.status) && user.role !== 'WAREHOUSE' && <Button loading={change.isPending} onClick={() => change.mutate({ path: `/sales/orders/${order.id}/reconcile`, body: {} })}>按原付款号核对</Button>}
        <Typography.Paragraph type="secondary">付款请求号：{order.payment.external_request_id}</Typography.Paragraph>
        {order.payment.allocations.map(a => <p key={a.product_id}>分配设备：{a.serials.join('、') || `${a.quantity} 件数量商品`}</p>)}
      </>}
      <details><summary>订单审计记录</summary>{order.events?.map((e,i) => <p key={i}>{date(e.at)} · {e.action}</p>)}</details>
    </Card>}
    {canSell && <><Card title="新建销售草稿"><Form form={form} layout="vertical" initialValues={{ customer_id: params.get('customer_id') || undefined, lines: [{ quantity: 1 }] }} onFinish={create.mutate} disabled={create.isPending}>
      <Form.Item label="客户" name="customer_id" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" disabled={!!params.get('source_service_id')} options={customers.data?.items.map(c => ({ value: c.id, label: `${c.display_name} · ${c.contact || c.id.slice(0,8)}` }))} /></Form.Item>
      {params.get('source_service_id') && <Tag>已关联来源接待与客户</Tag>}
      <Form.List name="lines">{(fields, { add, remove }) => <>{fields.map(f => <div className="grid" key={f.key}><Form.Item label="商品 / 有效政策" name={[f.name,'policy_version_id']} rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={offers.data?.items.map(o => ({ value: o.id, label: `${o.name} · 一次费 ${o.price} · 优惠 ${o.discount} · V${o.version}` }))} /></Form.Item><Form.Item label="数量" name={[f.name,'quantity']} rules={[{ required: true }]}><InputNumber min={1} max={10000} precision={0} /></Form.Item><Button disabled={fields.length === 1} onClick={() => remove(f.name)}>删除行</Button></div>)}<Button onClick={() => add({ quantity: 1 })}>增加商品 / 服务</Button></>}</Form.List>
      <Typography.Paragraph type="secondary">仅收一次费用；套餐月费不计入本次收银。最终资格、折扣和金额由系统核定。</Typography.Paragraph><Button type="primary" htmlType="submit" loading={create.isPending}>生成订单并核算金额</Button>
    </Form></Card>
    <Card title="销售方案辅助"><Form layout="vertical" onFinish={draft.mutate}><Form.Item name="text" label="客户需求" rules={[{ required: true }]}><Input.TextArea placeholder="例如：已有宽带，需要一台路由器并预约上门安装" /></Form.Item><Button htmlType="submit" loading={draft.isPending}>生成选品草稿</Button></Form>
      {draft.data && (draft.data.status === 'SUCCEEDED' && draft.data.output ? <><p>{draft.data.output.note}</p>{draft.data.output.items.map(i => <p key={i.policy_version_id}>{offers.data?.items.find(o => o.id === i.policy_version_id)?.name} × {i.quantity}：{i.reason}</p>)}<Button onClick={() => form.setFieldsValue({ lines: draft.data!.output!.items.map(i => ({ policy_version_id: i.policy_version_id, quantity: i.quantity })) })}>采用草稿填入表单，再人工核对</Button></> : <Alert type="warning" title={draft.data.error || '辅助未完成，可继续手工选品'} />)}
    </Card></>}
    {user.role !== 'WAREHOUSE' && <DayClose user={user} />}
  </div>;
}
