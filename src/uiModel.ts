export interface InstalledPlugin {
  valid_identity?: boolean;
  security?: import("./securityInstaller").SecurityFacts | null;
  id: string;
  name: string;
  version?: string;
  source?: string;
  check_source?: string;
  discovery_fingerprint?: string;
  discovery_error?: string;
  suggestions?: Candidate[];
  source_note?: string;
  metadata_error?: string;
  status: string;
  latest?: string;
  release_id?: number | string;
  asset_id?: number | string;
  error?: string;
}
export interface Candidate {
  repository: string;
  description?: string;
  owner?: string;
}
export type View = "updates" | "all";
export type StatusIcon =
  "download" | "check" | "question" | "warning" | "clock" | "unavailable";
const statuses: Record<string, { label: string; icon: StatusIcon }> = {
  update: { label: "Update available", icon: "download" },
  current: { label: "Up to date", icon: "check" },
  source_missing: { label: "Source unknown", icon: "question" },
  source_suggested: { label: "Source suggested", icon: "question" },
  source_not_found: { label: "Source not found", icon: "question" },
  unchecked: { label: "Not checked", icon: "clock" },
  error: { label: "Check failed", icon: "warning" },
  no_release: { label: "No stable GitHub release", icon: "unavailable" },
  no_compatible_release: {
    label: "No compatible release",
    icon: "unavailable",
  },
  ambiguous: { label: "Ambiguous release", icon: "warning" },
  version_unavailable: { label: "Version unavailable", icon: "warning" },
};
export function pluginStatus(plugin: InstalledPlugin) {
  const status = statuses[plugin.status] || statuses.unchecked;
  const version = plugin.version || "Unknown version";
  return {
    ...status,
    subtitle:
      plugin.status === "update" && plugin.latest
        ? `${version} → ${plugin.latest}`
        : `${version} · ${status.label}`,
  };
}
export function needsSource(plugin: InstalledPlugin) {
  return (
    !plugin.source &&
    ["source_missing", "source_suggested", "source_not_found"].includes(
      plugin.status,
    )
  );
}
export function visiblePlugins(plugins: InstalledPlugin[], view: View) {
  return plugins
    .filter(
      (plugin) =>
        view === "all" || plugin.status === "update" || needsSource(plugin),
    )
    .sort(
      (left, right) =>
        Number(right.status === "update") - Number(left.status === "update") ||
        left.name.localeCompare(right.name),
    );
}
export function pluginActions(plugin: InstalledPlugin) {
  return {
    update:
      plugin.status === "update" &&
      plugin.release_id !== undefined &&
      plugin.asset_id !== undefined,
    findSource: !plugin.source,
    changeSource: Boolean(plugin.source),
    retry: plugin.status === "error" || plugin.status === "unchecked",
  };
}
export function emptyMessage(
  plugins: InstalledPlugin[],
  loading: boolean,
  failed: boolean,
) {
  if (loading) return "Checking for updates…";
  if (failed) return "Could not check for updates. Try refreshing.";
  if (!plugins.length) return "No installed plugins found.";
  if (plugins.every((plugin) => plugin.status === "current"))
    return "Everything is up to date.";
  return "No confirmed updates. See All for plugin status.";
}

/** An empty Updates view can mean all checked or merely no confirmed updates. */
export function emptyUpdatesState(
  plugins: InstalledPlugin[],
  loading: boolean,
  failed: boolean,
) {
  if (
    loading ||
    failed ||
    plugins.length === 0 ||
    visiblePlugins(plugins, "updates").length
  )
    return null;
  return plugins.every((plugin) => plugin.status === "current")
    ? "current"
    : "unconfirmed";
}
export interface Bookmark {
  selectedId: string | null;
  scrollTop: number;
}
export interface Navigation {
  view: View;
  detailId: string | null;
  bookmarks: Record<View, Bookmark>;
}
export const initialNavigation: Navigation = {
  view: "updates",
  detailId: null,
  bookmarks: {
    updates: { selectedId: null, scrollTop: 0 },
    all: { selectedId: null, scrollTop: 0 },
  },
};
export type NavigationAction =
  | { type: "view"; view: View; scrollTop: number }
  | { type: "open"; id: string; scrollTop: number }
  | { type: "back" }
  | { type: "focus"; id: string };
export function navigate(
  state: Navigation,
  action: NavigationAction,
): Navigation {
  if (action.type === "back") return { ...state, detailId: null };
  if (action.type === "focus")
    return {
      ...state,
      bookmarks: {
        ...state.bookmarks,
        [state.view]: { ...state.bookmarks[state.view], selectedId: action.id },
      },
    };
  const bookmark = {
    ...state.bookmarks[state.view],
    scrollTop: action.scrollTop,
  };
  if (action.type === "open") bookmark.selectedId = action.id;
  return {
    ...state,
    view: action.type === "view" ? action.view : state.view,
    detailId: action.type === "open" ? action.id : null,
    bookmarks: { ...state.bookmarks, [state.view]: bookmark },
  };
}
export function restoreBookmark(
  container: { scrollTop: number },
  target: { focus(options?: FocusOptions): void } | undefined,
  bookmark: Bookmark,
) {
  target?.focus({ preventScroll: true });
  container.scrollTop = bookmark.scrollTop;
}
