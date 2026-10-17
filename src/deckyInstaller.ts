/** Only dependency on Decky's undocumented installer route. */
export interface StagedUpdate {
  artifact: string;
  name: string;
  version: string;
  hash: string;
  install_type?: "update" | "downgrade" | "install";
}
export interface Router {
  addEventListener?(
    event: string,
    listener: (...args: unknown[]) => void,
  ): unknown;
  removeEventListener?(
    event: string,
    listener: (...args: unknown[]) => void,
  ): void;
  call(route: string, ...args: unknown[]): Promise<unknown>;
}
export type InstallResult = { requested: boolean; error?: string };
const SELF_NAME = "Decky Direct Updater";
const SELF_REOPEN_KEY = "decky-direct-updater:self-reopen";
const REOPEN_EXPIRY = 30 * 60 * 1000;

function session(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.sessionStorage;
  } catch {
    return undefined;
  }
}

/** A later frontend mount can reopen Decky only after inventory proves installation. */
export async function requestSelfUpdate(
  update: StagedUpdate,
  request: (update: StagedUpdate) => Promise<InstallResult> = requestUpdate,
): Promise<InstallResult> {
  const storage = session();
  if (update.name !== SELF_NAME || !storage) return request(update);
  storage.setItem(
    SELF_REOPEN_KEY,
    JSON.stringify({ version: update.version, created: Date.now() }),
  );
  try {
    const result = await request(update);
    if (!result.requested) storage.removeItem(SELF_REOPEN_KEY);
    return result;
  } catch (error) {
    storage.removeItem(SELF_REOPEN_KEY);
    throw error;
  }
}

export async function reopenAfterSelfUpdate(
  installed: () => Promise<{ name: string; version?: string }[]>,
  navigation: {
    CloseSideMenus(): void;
    OpenQuickAccessMenu(tab: number): void;
  },
): Promise<void> {
  const storage = session();
  const raw = storage?.getItem(SELF_REOPEN_KEY);
  if (!raw || !storage) return;
  let pending: { version: string; created: number };
  try {
    pending = JSON.parse(raw);
  } catch {
    storage.removeItem(SELF_REOPEN_KEY);
    return;
  }
  if (
    typeof pending.version !== "string" ||
    typeof pending.created !== "number" ||
    Date.now() - pending.created > REOPEN_EXPIRY ||
    Date.now() < pending.created
  ) {
    storage.removeItem(SELF_REOPEN_KEY);
    return;
  }
  try {
    const plugins = await installed();
    if (
      !plugins.some(
        (plugin) =>
          plugin.name === SELF_NAME && plugin.version === pending.version,
      )
    )
      return;
    storage.removeItem(SELF_REOPEN_KEY);
    navigation.CloseSideMenus();
    setTimeout(() => navigation.OpenQuickAccessMenu(999), 100);
  } catch {
    // Preserve the marker for a later mount if inventory is temporarily unavailable.
  }
}

function loaderRouter(): Router | undefined {
  return typeof window === "undefined"
    ? undefined
    : (window as unknown as { DeckyBackend?: Router }).DeckyBackend;
}

export async function requestUpdate(
  update: StagedUpdate,
  router: Router | undefined = loaderRouter(),
): Promise<InstallResult> {
  const fallback =
    "Decky installer unavailable. Use Decky Settings → Install Plugin from ZIP to update manually.";
  if (typeof router?.call !== "function")
    return { requested: false, error: fallback };
  if (
    !/^file:\/\/\/[^\0\r\n]*\/staged\/update-[A-Za-z0-9_-]+\.zip$/.test(
      update.artifact,
    ) ||
    !/^[a-f0-9]{64}$/.test(update.hash) ||
    !update.name ||
    !update.version ||
    (update.install_type !== undefined &&
      !["update", "downgrade", "install"].includes(update.install_type))
  ) {
    return {
      requested: false,
      error: "Invalid staged update; check for updates again.",
    };
  }
  try {
    const result = await router.call(
      "utilities/install_plugin",
      update.artifact,
      update.name,
      update.version,
      update.hash,
      update.install_type === "install"
        ? 0
        : update.install_type === "downgrade"
          ? 3
          : 2,
    );
    if (
      result === false ||
      (result &&
        typeof result === "object" &&
        "success" in result &&
        result.success === false)
    ) {
      return { requested: false, error: fallback };
    }
    return { requested: true };
  } catch {
    return { requested: false, error: fallback };
  }
}

/** Loader emits this after its installation operation; inventory still decides success. */
export function listenForInstallCompletion(
  callback: (name: string) => void,
  router = loaderRouter(),
): () => void {
  if (!router?.addEventListener || !router.removeEventListener) return () => {};
  const listener = (...args: unknown[]) => {
    if (typeof args[0] === "string") callback(args[0]);
  };
  router.addEventListener("loader/plugin_download_finish", listener);
  return () =>
    router.removeEventListener?.("loader/plugin_download_finish", listener);
}
