/**
 * @fileoverview Client-side router configuration for the Amelia dashboard.
 * Uses React Router v7 with data loaders and lazy-loaded route components.
 */
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { RootErrorBoundary } from '@/components/ErrorBoundary';
import { workflowsLoader, workflowDetailLoader, historyLoader } from '@/loaders/workflows';
import { promptsLoader } from '@/loaders/prompts';
import { costsLoader } from '@/loaders';
import { approveAction, rejectAction, cancelAction } from '@/actions/workflows';

/**
 * Application router with route definitions, loaders, and actions.
 *
 * Route structure:
 * - `/` → Redirects to `/workflows`
 * - `/workflows` → Active workflows list (lazy-loaded)
 * - `/workflows/:id` → Active workflows list with specific workflow selected (lazy-loaded)
 * - `/workflows/:id/detail` → Workflow detail view (lazy-loaded)
 * - `/workflows/:id/approve` → Approve workflow action
 * - `/workflows/:id/reject` → Reject workflow action
 * - `/workflows/:id/cancel` → Cancel workflow action
 * - `/history` → Completed workflows history (lazy-loaded)
 * - `/logs` → System logs view (lazy-loaded)
 * - `/prompts` → Prompts configuration page (lazy-loaded)
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
        children: [
          {
            index: true,
            loader: workflowsLoader,
            lazy: async () => {
              const { default: Component } = await import('@/pages/WorkflowsPage');
              return { Component };
            },
          },
          {
            path: ':id',
            loader: workflowsLoader,
            lazy: async () => {
              const { default: Component } = await import('@/pages/WorkflowsPage');
              return { Component };
            },
          },
          {
            path: ':id/detail',
            loader: workflowDetailLoader,
            lazy: async () => {
              const { default: Component } = await import('@/pages/WorkflowDetailPage');
              return { Component };
            },
          },
        ],
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
        path: 'workflows/:id/cancel',
        action: cancelAction,
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
        path: 'prompts',
        loader: promptsLoader,
        lazy: async () => {
          const { default: Component } = await import('@/pages/PromptConfigPage');
          return { Component };
        },
      },
      {
        path: 'costs',
        loader: costsLoader,
        lazy: async () => {
          const { default: Component } = await import('@/pages/CostsPage');
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
