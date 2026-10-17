import type { InstalledPlugin } from "./uiModel";

export const CHECK_INTERVAL = 4 * 60 * 60 * 1000;
export interface UpdateSnapshot {
  plugins: InstalledPlugin[];
  checking: boolean;
  error: string;
  hasUpdates: boolean;
}
interface Dependencies {
  now?: () => number;
  list: () => Promise<InstalledPlugin[]>;
  check: (force: boolean) => Promise<InstalledPlugin[]>;
  listen: (callback: (plugin: InstalledPlugin) => void) => () => void;
  schedule: (callback: () => void, milliseconds: number) => () => void;
}
const sameInstallation = (a: InstalledPlugin, b: InstalledPlugin) =>
  a.name === b.name &&
  a.version === b.version &&
  (a.check_source || a.source) === (b.check_source || b.source);

/** Lifetime belongs to the plugin, independent of the panel or icon mounting. */
export function createUpdateStore(dependencies: Dependencies) {
  let snapshot: UpdateSnapshot = {
    plugins: [],
    checking: true,
    error: "",
    hasUpdates: false,
  };
  const subscribers = new Set<() => void>();
  const positives = new Map<string, InstalledPlugin>();
  let active = false;
  let started = false;
  let task: Promise<void> | null = null;
  let stopTimer: (() => void) | undefined;
  let stopListener: (() => void) | undefined;
  const now = dependencies.now || Date.now;
  let lastSuccessfulCheck: number | null = null;
  let lastAttempt: number | null = null;
  function publish(patch: Partial<UpdateSnapshot>) {
    if (!active) return;
    snapshot = { ...snapshot, ...patch, hasUpdates: positives.size > 0 };
    subscribers.forEach((callback) => callback());
  }
  function accept(plugins: InstalledPlugin[], complete: boolean) {
    for (const plugin of plugins) {
      const positive = positives.get(plugin.id);
      if (plugin.status === "update") positives.set(plugin.id, plugin);
      else if (
        plugin.status !== "error" ||
        (positive && !sameInstallation(positive, plugin))
      )
        positives.delete(plugin.id);
    }
    if (complete) {
      const ids = new Set(plugins.map((plugin) => plugin.id));
      for (const id of positives.keys()) if (!ids.has(id)) positives.delete(id);
    }
    publish({
      plugins: complete
        ? plugins
        : snapshot.plugins.some((p) => p.id === plugins[0].id)
          ? snapshot.plugins.map((p) =>
              p.id === plugins[0].id ? plugins[0] : p,
            )
          : [...snapshot.plugins, ...plugins],
    });
  }
  function refresh(force = false): Promise<void> {
    if (!active) return Promise.resolve();
    if (task) return task;
    const startedAt = now();
    lastAttempt = startedAt;
    publish({ checking: true, error: "" });
    task = (async () => {
      try {
        try {
          const inventory = await dependencies.list();
          if (active) {
            const previous = new Map(
              snapshot.plugins.map((plugin) => [plugin.id, plugin]),
            );
            for (const [id, positive] of positives) {
              const installed = inventory.find((plugin) => plugin.id === id);
              if (!installed || !sameInstallation(positive, installed))
                positives.delete(id);
            }
            publish({
              plugins: inventory.map((plugin) => {
                const old = previous.get(plugin.id);
                return old &&
                  plugin.source &&
                  sameInstallation(old, plugin) &&
                  old.discovery_fingerprint === plugin.discovery_fingerprint
                  ? {
                      ...old,
                      suggestions: plugin.suggestions,
                      discovery_error: plugin.discovery_error,
                    }
                  : plugin;
              }),
            });
          }
        } catch {
          /* A check can still recover an unavailable initial inventory. */
        }
        if (!active) return;
        const expired =
          lastSuccessfulCheck !== null &&
          startedAt - lastSuccessfulCheck >= CHECK_INTERVAL;
        const plugins = await dependencies.check(force || expired);
        if (active) {
          accept(plugins, true);
          if (!plugins.some((plugin) => plugin.status === "error"))
            lastSuccessfulCheck = startedAt;
        }
      } catch (error) {
        publish({ error: String(error).replace(/^Error:\s*/, "") });
      } finally {
        task = null;
        publish({ checking: false });
      }
    })();
    return task;
  }
  function refreshIfDue(): Promise<void> {
    const time = now();
    if (
      lastSuccessfulCheck !== null &&
      time - lastSuccessfulCheck < CHECK_INTERVAL
    )
      return Promise.resolve();
    if (lastAttempt !== null && time - lastAttempt < 60_000)
      return task || Promise.resolve();
    return refresh(true);
  }
  return {
    getSnapshot: () => snapshot,
    subscribe(callback: () => void) {
      subscribers.add(callback);
      return () => {
        subscribers.delete(callback);
      };
    },
    refresh,
    refreshIfDue,
    start() {
      if (started) return;
      started = active = true;
      stopListener = dependencies.listen((plugin) => {
        if (active) accept([plugin], false);
      });
      stopTimer = dependencies.schedule(() => {
        void refresh(false);
      }, CHECK_INTERVAL);
      void refresh(false);
    },
    dispose() {
      active = false;
      stopTimer?.();
      stopListener?.();
      subscribers.clear();
    },
  };
}
export type UpdateStore = ReturnType<typeof createUpdateStore>;
