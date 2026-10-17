/** Only dependency on Decky's undocumented installer route. */
export interface StagedUpdate {
  artifact: string;
  name: string;
  version: string;
  hash: string;
  install_type?: "update" | "downgrade";
}
export interface Router {
  call(route: string, ...args: unknown[]): Promise<unknown>;
}
export type InstallResult = { requested: boolean; error?: string };

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
      !["update", "downgrade"].includes(update.install_type))
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
      update.install_type === "downgrade" ? 3 : 2,
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
