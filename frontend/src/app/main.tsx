import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { Routes } from './routes';
import './style.css';

const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
createRoot(document.getElementById('root')!).render(
  <React.StrictMode><QueryClientProvider client={client}><ConfigProvider locale={zhCN}>
    <Routes />
  </ConfigProvider></QueryClientProvider></React.StrictMode>,
);
