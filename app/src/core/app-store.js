export function createAppStore(initialState) {
  let state = Object.freeze({ ...initialState });
  const listeners = new Set();

  return Object.freeze({
    get() {
      return state;
    },
    update(patch) {
      const nextPatch = typeof patch === "function" ? patch(state) : patch;
      state = Object.freeze({ ...state, ...nextPatch });
      for (const listener of listeners) listener(state);
      return state;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  });
}
