import type { InstallResult, StagedUpdate } from "./deckyInstaller";

export interface SecurityFacts {
  root_requested: boolean;
  flags: string[];
  has_python_backend: boolean;
  external_binaries: {
    name: string;
    source_host: string;
    declared_hash: string | null;
  }[];
}
export interface SecurityAssessment extends SecurityFacts {
  previous_root_requested: boolean | null;
  previous_has_python_backend: boolean | null;
  previous_external_binaries: SecurityFacts["external_binaries"] | null;
  added_binary_names: string[];
  changed_binary_source_hosts: string[];
  comparison_available: boolean;
  updating: boolean;
  requires_acknowledgment: boolean;
  findings: { kind: string; severity: "information" | "warning" }[];
}
export interface PendingReview {
  staged: StagedUpdate;
  acknowledged: boolean;
}
const invalid =
  "Prepared package or installed plugin changed. Prepare it again.";

/** One gate for all installation paths; the backend owns review policy. */
export function createSecurityInstaller(deps: {
  authorize: (
    token: string,
    acknowledged: boolean,
  ) => Promise<{ update: StagedUpdate | null; error: string | null }>;
  discard: (token: string) => Promise<unknown>;
  request: (staged: StagedUpdate) => Promise<InstallResult>;
}) {
  let pending: PendingReview | null = null;
  let resolveReview: ((accepted: boolean) => void) | null = null;
  let active = false;
  let activeToken: string | undefined;
  let disposed = false;
  let cancelled = false;
  const subscribers = new Set<() => void>();
  const publish = () => subscribers.forEach((subscriber) => subscriber());
  function settle(token: string, accepted: boolean) {
    if (
      !pending ||
      pending.staged.review_token !== token ||
      (accepted && !pending.acknowledged)
    )
      return;
    const resolve = resolveReview;
    cancelled = !accepted;
    pending = null;
    resolveReview = null;
    publish();
    resolve?.(accepted);
  }
  return {
    getSnapshot: () => pending,
    wasCancelled: () => cancelled,
    subscribe(callback: () => void) {
      subscribers.add(callback);
      return () => {
        subscribers.delete(callback);
      };
    },
    acknowledge(token: string, checked: boolean) {
      if (!pending || pending.staged.review_token !== token) return;
      pending = { ...pending, acknowledged: checked };
      publish();
    },
    continue(token: string) {
      settle(token, true);
    },
    cancel(token: string) {
      settle(token, false);
    },
    async request(staged: StagedUpdate): Promise<InstallResult> {
      const token = staged.review_token;
      if (disposed || active) {
        if (token && token !== activeToken) await deps.discard(token);
        return {
          requested: false,
          error: "Installation already being prepared.",
        };
      }
      if (!token || !staged.security) {
        if (token) await deps.discard(token);
        return { requested: false, error: invalid };
      }
      active = true;
      cancelled = false;
      activeToken = token;
      let requested = false;
      try {
        if (staged.security.requires_acknowledgment) {
          const accepted = await new Promise<boolean>((resolve) => {
            resolveReview = resolve;
            pending = { staged, acknowledged: false };
            publish();
          });
          if (!accepted || disposed)
            return { requested: false, error: "Installation cancelled." };
        }
        const result = await deps.authorize(
          token,
          staged.security.requires_acknowledgment,
        );
        const authorized = result.update;
        if (disposed)
          return { requested: false, error: "Installation cancelled." };
        if (
          result.error ||
          !authorized ||
          !authorized.security_authorized ||
          authorized.hash !== staged.hash ||
          authorized.name !== staged.name ||
          authorized.version !== staged.version ||
          authorized.artifact !== staged.artifact ||
          authorized.review_token !== token
        )
          return { requested: false, error: result.error || invalid };
        const native = await deps.request(authorized);
        requested = native.requested;
        return native;
      } catch {
        return { requested: false, error: invalid };
      } finally {
        try {
          if (!requested) await deps.discard(token);
        } finally {
          active = false;
          activeToken = undefined;
        }
      }
    },
    dispose() {
      disposed = true;
      if (pending) settle(pending.staged.review_token!, false);
      subscribers.clear();
    },
  };
}
export type SecurityInstaller = ReturnType<typeof createSecurityInstaller>;
