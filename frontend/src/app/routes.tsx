import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Layout, Spin, Typography, Tabs } from 'antd';
import { BrowserRouter, Routes as RouterRoutes, Route, useLocation, useNavigate } from 'react-router-dom';
import { api, setCsrfToken } from '../lib/api';
import { LoginPage, type User } from '../features/auth/LoginPage';
import { ServicePage } from '../features/services/ServicePage';
import { CatalogPage } from '../features/catalog/CatalogPage';
import { QueuePage, PublicQueuePage } from '../features/queue/QueuePage';
import { FeedbackPage } from '../features/feedback/FeedbackPage';
import { QualityPage } from '../features/quality/QualityPage';
import { ImprovementPage } from '../features/improvements/ImprovementPage';
import { EvaluationPage } from '../features/evaluations/EvaluationPage';
import { PromptPage } from '../features/prompts/PromptPage';
import { CustomerPage } from '../features/customers/CustomerPage';
import { InventoryPage } from '../features/inventory/InventoryPage';
import { SalesPage } from '../features/sales/SalesPage';
import { InstallationPage } from '../features/installations/InstallationPage';
import { FinancePage } from '../features/finance/FinancePage';
import { OperationsPage } from '../features/operations/OperationsPage';
import { AftersalesPage } from '../features/aftersales/AftersalesPage';
import { ReversalsPage } from '../features/aftersales/ReversalsPage';
import { TransactionPage } from '../features/transactions/TransactionPage';
import { SettlementPage } from '../features/finance/SettlementPage';
import { TransfersPage } from '../features/inventory/TransfersPage';
import { TodosPage } from '../features/operations/TodosPage';

function Workspace() {
  const cache = useQueryClient();
  const location = useLocation(), navigate = useNavigate();
  const me = useQuery({ queryKey: ['me'], queryFn: async () => { const u = await api<User>('/auth/me'); setCsrfToken(u.csrf_token); return u; } });
  const health = useQuery({ queryKey: ['health'], queryFn: async () => { const r = await fetch('/health/ready'); if (!r.ok) throw new Error('服务尚未就绪'); return r.json() as Promise<{ ai_mode: string }>; } });
  if (me.isPending) return <Spin fullscreen />;
  if (!me.data) return <LoginPage />;
  const user = me.data, serviceAccess = ['STAFF','MANAGER','ADMIN'].includes(user.role), management = ['MANAGER','ADMIN'].includes(user.role);
  const items = [
    { key: 'todos', label: '统一待办', children: <TodosPage user={user} /> },
    ...(serviceAccess ? [
      { key: 'services', label: '服务工作台', children: <ServicePage /> }, { key: 'customers', label: '客户全景', children: <CustomerPage /> },
      { key: 'queue', label: '排队与窗口', children: <QueuePage user={user} /> }, { key: 'quality', label: '文本质检', children: <QualityPage /> },
      { key: 'catalog', label: '资料管理', children: <CatalogPage user={user} /> }, { key: 'prompts', label: '提示词与运行', children: <PromptPage user={user} /> },
      { key: 'transactions', label: '组合交易', children: <TransactionPage user={user} /> }, { key: 'reversals', label: '通信冲正', children: <ReversalsPage user={user} /> },
    ] : []),
    ...(user.role !== 'INSTALLER' ? [{ key: 'sales', label: '销售收银', children: <SalesPage user={user} /> }] : []),
    ...(user.role !== 'INSTALLER' ? [{ key: 'aftersales', label: '售后退款', children: <AftersalesPage user={user} /> }] : []),
    ...(['WAREHOUSE','MANAGER','ADMIN'].includes(user.role) ? [{ key: 'inventory', label: '采购库存', children: <InventoryPage user={user} /> }] : []),
    ...(['WAREHOUSE','MANAGER','ADMIN'].includes(user.role) ? [{ key: 'transfers', label: '调拨盘点', children: <TransfersPage user={user} /> }] : []),
    ...(user.role !== 'FINANCE' ? [{ key: 'installations', label: '安装交付', children: <InstallationPage user={user} /> }] : []),
    ...(['FINANCE','MANAGER','ADMIN'].includes(user.role) ? [{ key: 'finance', label: '收益对账', children: <FinancePage user={user} /> }] : []),
    ...(['FINANCE','MANAGER','ADMIN'].includes(user.role) ? [{ key: 'settlements', label: '结算与差异', children: <SettlementPage user={user} /> }] : []),
    ...(management ? [{ key: 'operations', label: '经营与 GEO', children: <OperationsPage /> }, { key: 'improvements', label: '统计与改进', children: <ImprovementPage /> }, { key: 'evaluations', label: '评测记录', children: <EvaluationPage /> }] : []),
  ];
  return <Layout style={{ minHeight: '100vh' }}><main className="page">
    <div className="toolbar"><Typography.Title level={2}>营业厅服务工作台</Typography.Title>
      <Button onClick={async () => { await api('/auth/logout', {}); setCsrfToken(''); cache.clear(); }}>退出 {me.data.username}</Button></div>
    <Alert title={`模拟数据 · ${health.error ? '服务尚未就绪' : health.data?.ai_mode === 'deepseek' ? 'DeepSeek 辅助已启用' : '离线模式（固定输出，无模型费用）'}`} type="info" showIcon />
    <Tabs activeKey={items.some(i => i.key === location.pathname.slice(1)) ? location.pathname.slice(1) : items[0].key} onChange={key => navigate('/' + key)} destroyOnHidden items={items} />
  </main></Layout>;
}

export function Routes() { return <BrowserRouter><RouterRoutes><Route path="/take-number" element={<PublicQueuePage />} /><Route path="/public-board" element={<PublicQueuePage boardOnly />} /><Route path="/feedback" element={<FeedbackPage />} /><Route path="*" element={<Workspace />} /></RouterRoutes></BrowserRouter>; }
