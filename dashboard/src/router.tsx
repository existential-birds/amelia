import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { RootErrorBoundary } from '@/components/ErrorBoundary';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    errorElement: <RootErrorBoundary />,
    children: [
      {
        index: true,
        element: <Navigate to="/workflows" replace />
      },
      {
        path: 'workflows',
        lazy: async () => {
          const { default: Component } = await import('@/pages/WorkflowsPage');
          return { Component };
        },
      },
      {
        path: 'workflows/:id',
        lazy: async () => {
          const { default: Component } = await import('@/pages/WorkflowDetailPage');
          return { Component };
        },
      },
      {
        path: 'history',
        lazy: async () => {
          const { default: Component } = await import('@/pages/HistoryPage');
          return { Component };
        },
      },
      {
        path: 'logs',
        lazy: async () => {
          const { default: Component } = await import('@/pages/LogsPage');
          return { Component };
        },
      },
      {
        path: '*',
        element: <Navigate to="/workflows" replace />,
      },
    ],
  },
]);
