import type { SecurityAssessment } from "./securityInstaller";
/** Only dependency on Decky's undocumented installer route. */
export interface StagedUpdate {
  artifact: string;
  name: string;
  version: string;
  hash: string;
  security?: SecurityAssessment;
  review_token?: string;
  security_authorized?: boolean;
  previous_version?: string | null;
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
interface LoaderUninstallDialog {
  uninstallPlugin(
    name: string,
    title: string,
    buttonText: string,
    description: string,
  ): void;
}

/** Same native modal as Loader's plugin list. Never call the direct uninstall RPC. */
export function requestUninstallConfirmation(
  name: string,
  text: { title: string; button: string; description: string },
  loader: LoaderUninstallDialog | undefined = typeof window === "undefined"
    ? undefined
    : (window as unknown as { DeckyPluginLoader?: LoaderUninstallDialog })
        .DeckyPluginLoader,
): InstallResult {
  if (!name || typeof loader?.uninstallPlugin !== "function")
    return {
      requested: false,
      error: "Open Decky Settings → Plugins to uninstall this plugin.",
    };
  try {
    loader.uninstallPlugin(name, text.title, text.button, text.description);
    return { requested: true };
  } catch {
    return {
      requested: false,
      error: "Open Decky Settings → Plugins to uninstall this plugin.",
    };
  }
}
const SELF_NAME = "Decky Direct Updater";
const SELF_REOPEN_KEY = "decky-direct-updater:self-reopen";
const REOPEN_EXPIRY = 30 * 60 * 1000;
interface SelfUpdateNavigation {
  CloseSideMenus(): void;
  OpenQuickAccessMenu(tab: number): void;
}

export interface SelfUpdateFrontend {
  version: string;
  instance: string;
}
export const FRONTEND_VERSION = "__DDU_FRONTEND_VERSION__";
const moduleFrontend: SelfUpdateFrontend = {
  version: FRONTEND_VERSION,
  instance: crypto.randomUUID(),
};

interface LoaderPanelPlugin {
  name: string;
  version?: string;
  content?: { key?: string | null };
}
interface LoaderPanelState {
  plugins: LoaderPanelPlugin[];
  deckyState: {
    publicState(): { activePlugin: LoaderPanelPlugin | null };
    closeActivePlugin(): void;
    setActivePlugin(name: string): void;
  };
}

/** QAM visibility and Loader's selected plugin are separate state. */
export function selfUpdatePanel(
  version: string,
  loader: LoaderPanelState | undefined = typeof window === "undefined"
    ? undefined
    : (window as unknown as { DeckyPluginLoader?: LoaderPanelState })
        .DeckyPluginLoader,
  instance?: string,
) {
  const replacement = () =>
    loader?.plugins.find((plugin) => plugin.name === SELF_NAME);
  const available = () =>
    Array.isArray(loader?.plugins) &&
    loader.plugins.some(
      (plugin) =>
        plugin.name === SELF_NAME &&
        plugin.version === version &&
        (instance === undefined || plugin.content?.key === instance),
    ) &&
    typeof loader.deckyState?.publicState === "function" &&
    typeof loader.deckyState?.closeActivePlugin === "function" &&
    typeof loader.deckyState?.setActivePlugin === "function";
  if (!available()) return null;
  return {
    stale() {
      if (!available()) return false;
      const active = loader!.deckyState.publicState().activePlugin;
      return (
        active?.name === SELF_NAME && active.content !== replacement()?.content
      );
    },
    close() {
      if (!available()) return false;
      loader!.deckyState.closeActivePlugin();
      return true;
    },
    select() {
      if (!available()) return false;
      const active = loader!.deckyState.publicState().activePlugin;
      if (active && active.name !== SELF_NAME) return false;
      loader!.deckyState.setActivePlugin(SELF_NAME);
      return (
        loader!.deckyState.publicState().activePlugin?.content ===
        replacement()?.content
      );
    },
  };
}

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
  frontend = moduleFrontend,
): Promise<InstallResult> {
  const storage = session();
  if (update.name !== SELF_NAME || !storage) return request(update);
  storage.setItem(
    SELF_REOPEN_KEY,
    JSON.stringify({
      version: update.version,
      created: Date.now(),
      requester: frontend.instance,
    }),
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
  navigation: SelfUpdateNavigation,
  frontend = moduleFrontend,
  isActive: () => boolean = () => true,
): Promise<void> {
  const storage = session();
  const raw = storage?.getItem(SELF_REOPEN_KEY) ?? null;
  let targetVersion = frontend.version;
  if (raw) {
    let pending: {
      version: string;
      created: number;
      requester?: string;
    } | null;
    try {
      pending = JSON.parse(raw);
    } catch {
      storage?.removeItem(SELF_REOPEN_KEY);
      return;
    }
    if (
      !pending ||
      typeof pending.version !== "string" ||
      !pending.version ||
      typeof pending.created !== "number" ||
      !Number.isFinite(pending.created) ||
      (pending.requester !== undefined &&
        typeof pending.requester !== "string") ||
      Date.now() - pending.created > REOPEN_EXPIRY ||
      Date.now() < pending.created
    ) {
      storage?.removeItem(SELF_REOPEN_KEY);
      return;
    }
    if (
      pending.version !== frontend.version ||
      pending.requester === frontend.instance
    )
      return;
    targetVersion = pending.version;
  }
  if (!isActive()) return;
  try {
    const panel = selfUpdatePanel(targetVersion, undefined, frontend.instance);
    // Loader may register the same version again after the original handoff completed.
    if (!panel || (!raw && !panel.stale())) return;
    const plugins = await installed();
    if (
      !plugins.some(
        (plugin) =>
          plugin.name === SELF_NAME && plugin.version === targetVersion,
      )
    )
      return;
    if (!isActive() || (storage?.getItem(SELF_REOPEN_KEY) ?? null) !== raw)
      return;
    if ((!raw && !panel.stale()) || !panel.close()) return;
    navigation.CloseSideMenus();
    // Let Loader render its cleared selection before selecting the replacement.
    setTimeout(() => {
      if (!isActive() || (storage?.getItem(SELF_REOPEN_KEY) ?? null) !== raw)
        return;
      try {
        if (!panel.select()) return;
        navigation.OpenQuickAccessMenu(999);
        if (raw && storage?.getItem(SELF_REOPEN_KEY) === raw)
          storage.removeItem(SELF_REOPEN_KEY);
      } catch {
        // Keep the handoff pending if Loader cannot select/open its new content yet.
      }
    }, 100);
  } catch {
    // Preserve the marker for a later mount if inventory is temporarily unavailable.
  }
}

/** Keep checking until Loader reports the replacement version or this mount ends. */
export function watchSelfUpdate(
  installed: () => Promise<{ name: string; version?: string }[]>,
  navigation: SelfUpdateNavigation,
  frontend = moduleFrontend,
): () => void {
  let active = true;
  let checking = false;
  const check = async () => {
    if (!active || checking) return;
    checking = true;
    try {
      await reopenAfterSelfUpdate(
        installed,
        navigation,
        frontend,
        () => active,
      );
    } finally {
      checking = false;
    }
  };
  void check();
  const timer = setInterval(() => void check(), 2000);
  return () => {
    active = false;
    clearInterval(timer);
  };
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
  if (update.security_authorized !== true)
    return {
      requested: false,
      error: "Review plugin access before continuing.",
    };
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
