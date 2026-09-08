import '@testing-library/jest-dom/vitest'

// antd 组件在 jsdom 下依赖的浏览器 API（matchMedia 用于栅格/主题断点，ResizeObserver 用于表格测量）
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,      // 旧 API，antd 仍在用
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  })
}

if (!('ResizeObserver' in globalThis)) {
  globalThis.ResizeObserver = class {
    observe() { /* noop */ }
    unobserve() { /* noop */ }
    disconnect() { /* noop */ }
  } as unknown as typeof ResizeObserver
}

// antd 弹层挂载在 body 上，滚动方法在 jsdom 中不存在
Element.prototype.scrollTo = Element.prototype.scrollTo || (() => undefined)
