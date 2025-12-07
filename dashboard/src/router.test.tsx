import { describe, it, expect } from 'vitest';
import { router } from '@/router';

describe('Router Configuration', () => {
  it('should have loader for workflows route', () => {
    const workflowsRoute = router.routes[0]?.children?.find(
      (r) => r.path === 'workflows'
    );
    expect(workflowsRoute).toBeDefined();
    expect(workflowsRoute?.loader).toBeDefined();
  });

  it('should have loader for workflow detail route', () => {
    const detailRoute = router.routes[0]?.children?.find(
      (r) => r.path === 'workflows/:id'
    );
    expect(detailRoute).toBeDefined();
    expect(detailRoute?.loader).toBeDefined();
  });

  it('should have loader for history route', () => {
    const historyRoute = router.routes[0]?.children?.find(
      (r) => r.path === 'history'
    );
    expect(historyRoute).toBeDefined();
    expect(historyRoute?.loader).toBeDefined();
  });
});
