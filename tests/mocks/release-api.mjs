export const callable =
  (name) =>
  (...args) =>
    globalThis.releaseRpc(name, ...args);
export const definePlugin = (factory) => factory;
export const addEventListener = () => {};
export const removeEventListener = () => {};
export const useQuickAccessVisible = () => false;
