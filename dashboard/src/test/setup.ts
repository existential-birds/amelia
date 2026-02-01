import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock scrollIntoView for Radix UI Select tests
Element.prototype.scrollIntoView = vi.fn();

// Mock ResizeObserver for React Flow tests
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock matchMedia for Sidebar responsive tests
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
