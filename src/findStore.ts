export interface Repository {
  repository: string;
  name: string;
  owner: string;
  stars: number;
  description: string;
  fork: boolean;
  archived: boolean;
  disabled: boolean;
}
export interface SearchPage {
  results?: Repository[];
  next_page?: number | null;
  direct?: boolean;
  error?: string | null;
}
export interface RepositoryDetails extends Repository {
  token?: string;
  status: string;
  version?: string;
  installed_version?: string;
  release_id?: string | number;
  asset_id?: string | number;
  error?: string | null;
}
export const formatStars = (stars: number) =>
  stars < 1000
    ? String(stars)
    : `${Number((stars / 1000).toFixed(stars < 10000 ? 1 : 0))}k`;
export function createFindStore(
  search: (query: string, page: number) => Promise<SearchPage>,
) {
  let state = {
    installedRepository: null as string | null,
    query: "",
    submitted: "",
    results: [] as Repository[],
    visible: 5,
    next: null as number | null,
    loading: false,
    error: "",
    direct: null as Repository | null,
  };
  let generation = 0;
  let disposed = false;
  const listeners = new Set<() => void>();
  const cached = new Map<string, { time: number; data: SearchPage }>();
  const pending = new Map<string, Promise<SearchPage>>();
  const set = (change: Partial<typeof state>) => {
    if (disposed) return;
    state = { ...state, ...change };
    listeners.forEach((fn) => fn());
  };
  async function load(query: string, page: number, append: boolean) {
    const key = `${query.toLowerCase()}:${page}`;
    const current = ++generation;
    set({ loading: true, error: "", direct: null, submitted: query });
    try {
      let data: SearchPage;
      const saved = cached.get(key);
      if (
        saved &&
        Date.now() - saved.time <
          (saved.data.results?.length ? 21600000 : 1200000)
      )
        data = saved.data;
      else {
        let request = pending.get(key);
        if (!request) {
          request = search(query, page);
          pending.set(key, request);
          void request.finally(() => pending.delete(key)).catch(() => {});
        }
        data = await request;
        if (!data.error) {
          cached.set(key, { time: Date.now(), data });
          if (cached.size > 40) cached.delete(cached.keys().next().value!);
        }
      }
      if (current !== generation || disposed) return;
      const results = append
        ? [
            ...state.results,
            ...(data.results || []).filter(
              (row) =>
                !state.results.some((old) => old.repository === row.repository),
            ),
          ]
        : data.results || [];
      set({
        results,
        visible: append ? state.visible + 5 : 5,
        next: data.next_page || null,
        loading: false,
        error: data.error || "",
        direct: data.direct ? results[0] || null : null,
      });
    } catch {
      if (current === generation)
        set({ loading: false, error: "Could not reach GitHub." });
    }
  }
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    type(query: string) {
      set({ query });
    },
    submit() {
      const query = state.query.trim().replace(/\s+/g, " ");
      if (!query) return Promise.resolve();
      return load(query, 1, false);
    },
    more() {
      if (state.loading) return Promise.resolve();
      if (state.visible < state.results.length) {
        set({ visible: state.visible + 5 });
        return Promise.resolve();
      }
      return state.next
        ? load(state.submitted, state.next, true)
        : Promise.resolve();
    },
    installed(repository: string) {
      set({ installedRepository: repository });
    },
    clearDirect() {
      set({ direct: null });
    },
    dispose() {
      disposed = true;
      generation++;
      listeners.clear();
    },
  };
}
export type FindStore = ReturnType<typeof createFindStore>;
