import '@testing-library/jest-dom/vitest';

global.ResizeObserver = vi.fn().mockImplementation((callback: ResizeObserverCallback) => ({
  observe: vi.fn().mockImplementation((target: Element) => {
    callback([{ contentRect: { width: 500, height: 300 } } as ResizeObserverEntry], {} as ResizeObserver);
  }),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})) as unknown as typeof ResizeObserver;
