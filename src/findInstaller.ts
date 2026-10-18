import type { StagedUpdate, InstallResult } from "./deckyInstaller";
import type { RepositoryDetails } from "./findStore";

export function createFindInstaller(deps: {
  stage: (
    token: string,
    release: string | number,
    asset: string | number,
  ) => Promise<StagedUpdate & { ticket?: string; error?: string }>;
  finish: (
    ticket: string,
    cancelled: boolean,
  ) => Promise<{ installed: boolean; error?: string }>;
  request: (staged: StagedUpdate) => Promise<InstallResult>;
  refresh: () => Promise<unknown>;
  installed: (repository: string) => void;
}) {
  const tickets = new Map<string, { repository: string; name: string }>();
  let preparing = false;
  let disposed = false;
  let completed = false;
  let checking: Promise<boolean> | null = null;
  return {
    async install(selection: RepositoryDetails) {
      if (
        preparing ||
        !selection.token ||
        selection.release_id === undefined ||
        selection.asset_id === undefined
      )
        return "Installation already being prepared.";
      if (tickets.size)
        return "Confirmation requested. Accept or cancel the pending installation in Decky.";
      completed = false;
      preparing = true;
      try {
        const staged = await deps.stage(
          selection.token,
          selection.release_id,
          selection.asset_id,
        );
        if (staged.error || !staged.ticket)
          return staged.error || "Installation failed. Try again.";
        if (disposed) {
          await deps.finish(staged.ticket, true);
          return "Installation cancelled.";
        }
        tickets.set(staged.ticket, {
          repository: selection.repository,
          name: staged.name,
        });
        let result: InstallResult;
        try {
          result = await deps.request(staged);
        } catch {
          tickets.delete(staged.ticket);
          await deps.finish(staged.ticket, true);
          return "Installation failed. Try again.";
        }
        if (!result.requested) {
          tickets.delete(staged.ticket);
          await deps.finish(staged.ticket, true);
          return result.error || "Installation failed. Try again.";
        }
        return "Confirmation requested. Accept or cancel in Decky. Use Check installation if the status has not refreshed.";
      } finally {
        preparing = false;
      }
    },
    check(pluginName?: string) {
      if (checking) return checking;
      checking = (async () => {
        let changed = false;
        for (const [ticket, plugin] of tickets) {
          if (pluginName !== undefined && plugin.name !== pluginName) continue;
          const result = await deps.finish(ticket, false);
          if (result.installed && !disposed) {
            tickets.delete(ticket);
            completed = true;
            changed = true;
            deps.installed(plugin.repository);
          }
        }
        if (changed && !disposed) await deps.refresh();
        return completed;
      })().finally(() => {
        checking = null;
      });
      return checking;
    },
    async cancel() {
      for (const ticket of tickets.keys()) await deps.finish(ticket, true);
      tickets.clear();
    },
    dispose() {
      disposed = true;
    },
  };
}
