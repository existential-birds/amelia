/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

/**
 * @fileoverview Logs monitoring page - coming soon placeholder.
 *
 * Will display system logs and monitoring information once implemented.
 */

import { Loader2 } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';

/**
 * Displays a placeholder for the logs monitoring page.
 *
 * Currently under development. Will eventually show system logs,
 * agent output, and monitoring information for workflow debugging.
 *
 * @returns The logs page UI with coming soon message
 */
export default function LogsPage() {
  return (
    <div className="flex flex-col h-full w-full">
      <PageHeader>
        <PageHeader.Left>
          <PageHeader.Label>MONITORING</PageHeader.Label>
          <PageHeader.Title>Logs</PageHeader.Title>
        </PageHeader.Left>
      </PageHeader>

      {/* Coming soon placeholder */}
      <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
        <p className="text-muted-foreground font-heading text-lg tracking-wide">
          Coming soon
        </p>
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    </div>
  );
}

// No loader needed for logs page
