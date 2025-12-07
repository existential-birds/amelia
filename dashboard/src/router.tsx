/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { RootErrorBoundary } from '@/components/ErrorBoundary';
import { workflowsLoader, workflowDetailLoader, historyLoader } from '@/loaders/workflows';

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
        loader: workflowsLoader,
        lazy: async () => {
          const { default: Component } = await import('@/pages/WorkflowsPage');
          return { Component };
        },
      },
      {
        path: 'workflows/:id',
        loader: workflowDetailLoader,
        lazy: async () => {
          const { default: Component } = await import('@/pages/WorkflowDetailPage');
          return { Component };
        },
      },
      {
        path: 'history',
        loader: historyLoader,
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
