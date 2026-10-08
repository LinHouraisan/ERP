import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Select, Table, Tag } from 'antd';
import { api } from '../../lib/api';
import { date, label } from '../../lib/display';
import type { User } from '../auth/LoginPage';
type Todo = { key: string; kind: string; title: string; url: string; owner_id: string; owner_name: string; due_at: string; overdue: boolean; status: string };

export function TodosPage({ user }: { user: User }) {
  const [scope,setScope] = useState('all');
  const tasks = useQuery({ queryKey: ['todos'], queryFn: () => api<{ items: Todo[]; definition?: string }>('/todos') });
  return <Card title="统一待办" extra={<Button onClick={() => void tasks.refetch()}>刷新待办</Button>}>{tasks.error && <Alert type="error" title={tasks.error.message} />}<p>{tasks.data?.definition}</p><Select aria-label="待办范围" value={scope} onChange={setScope} options={[{ value:'all',label:'本岗位可见的全部待办' },{ value:'mine',label:'分配给我的待办' },{ value:'overdue',label:'已超过复核期限' }]} style={{ width:240 }} /><Table rowKey="key" dataSource={tasks.data?.items.filter(t => scope==='mine'?t.owner_id===user.user_id:scope==='overdue'?t.overdue:true)} columns={[{ title:'事项',dataIndex:'title' },{ title:'负责人',dataIndex:'owner_name' },{ title:'状态',dataIndex:'status',render:v=>v.split('/').map(label).join(' / ') },{ title:'处理期限',render:(_,r)=><>{date(r.due_at)} {r.overdue && <Tag color="orange">待复核</Tag>}</> },{ title:'处理',render:(_,r)=><a href={r.url}>打开原单</a> }]} /></Card>;
}
