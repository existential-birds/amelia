/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Client-side router configuration for the Amelia dashboard.
 * Uses React Router v6 with data loaders and lazy-loaded route components.
 */
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { RootErrorBoundary } from '@/components/ErrorBoundary';
import { workflowsLoader, workflowDetailLoader, historyLoader } from '@/loaders/workflows';
import { approveAction, rejectAction } from '@/actions/workflows';

/**
 * Application router with route definitions, loaders, and actions.
 *
 * Route structure:
 * - `/` → Redirects to `/workflows`
 * - `/workflows` → Active workflows list (lazy-loaded)
 * - `/workflows/:id` → Workflow detail view (lazy-loaded)
 * - `/workflows/:id/approve` → Approve workflow action
 * - `/workflows/:id/reject` → Reject workflow action
 * - `/history` → Completed workflows history (lazy-loaded)
 * - `/logs` → System logs view (lazy-loaded)
 * - `*` → Fallback redirect to `/workflows`
 *
 * All page components are lazy-loaded for optimal initial bundle size.
 */
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
        path: 'workflows/:id/approve',
        action: approveAction,
      },
      {
        path: 'workflows/:id/reject',
        action: rejectAction,
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
