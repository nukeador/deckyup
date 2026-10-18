import { ReleaseReview } from "./ReleaseReview";
import {
  addEventListener,
  removeEventListener,
  callable,
  definePlugin,
  useQuickAccessVisible,
} from "@decky/api";
import { Focusable, Navigation, Spinner } from "@decky/ui";
import {
  useEffect,
  useLayoutEffect,
  useReducer,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { FaDownload, FaSyncAlt, FaSearch, FaCheck } from "react-icons/fa";
import {
  FRONTEND_VERSION,
  requestSelfUpdate,
  watchSelfUpdate,
  listenForInstallCompletion,
  type StagedUpdate,
} from "./deckyInstaller";
import { NavigationGroup } from "./NavigationGroup";
import type { ReleasePage } from "./ReleaseSelector";
import { PluginDetails } from "./PluginDetails";
import { PluginRow } from "./PluginRow";
import { usePanelHeight } from "./usePanelHeight";
import { createUpdateStore, type UpdateStore } from "./updateStore";
import { createFindInstaller } from "./findInstaller";
import { FindPlugins } from "./FindPlugins";
import {
  createFindStore,
  type FindStore,
  type SearchPage,
  type RepositoryDetails,
} from "./findStore";
import { styles } from "./styles";
import { LanguageProvider, useT } from "./i18n";
import {
  createSecurityInstaller,
  type SecurityInstaller,
} from "./securityInstaller";
import { SecurityReviewBoundary } from "./SecurityReview";
import {
  emptyMessage,
  emptyUpdatesState,
  initialNavigation,
  navigate,
  restoreBookmark,
  visiblePlugins,
  type Candidate,
  type InstalledPlugin,
  type View,
} from "./uiModel";

const loadSecurity = callable<
  [string],
  import("./securityInstaller").SecurityFacts | null
>("plugin_security");
const list = callable<[], InstalledPlugin[]>("list_plugins");
const check = callable<[boolean], InstalledPlugin[]>("check_updates");
const search = callable<
  [string],
  { candidates: Candidate[]; error: string | null }
>("search_source");
const verify = callable<
  [string, string],
  { candidates: Candidate[]; error: string | null }
>("verify_source");
const confirm = callable<
  [string, string],
  { success: boolean; error: string | null }
>("confirm_source");
const stage = callable<
  [string, number | string, number | string],
  { update: StagedUpdate | null; error: string | null }
>("stage_update");
const releases = callable<[string, string | null], ReleasePage>(
  "list_releases",
);
const stageRelease = callable<
  [string, string | number, string | number, boolean],
  { update: StagedUpdate | null; error: string | null }
>("stage_release");
const errorText = (error: unknown) => String(error).replace(/^Error:\s*/, "");

const findRepositories = callable<[string, number], SearchPage>(
  "find_repositories",
);
const repositoryDetails = callable<[string], RepositoryDetails>(
  "repository_details",
);
const stageRepository = callable<
  [string, string | number, string | number],
  StagedUpdate & { ticket?: string; error?: string }
>("stage_repository");
const finishRepository = callable<
  [string, boolean],
  { installed: boolean; error?: string }
>("finish_repository");
const authorizeStaged = callable<
  [string, boolean],
  { update: StagedUpdate | null; error: string | null }
>("authorize_staged");
const discardStaged = callable<[string], boolean>("discard_staged");
interface FinderActions {
  install: (selection: RepositoryDetails) => Promise<string>;
  check: () => Promise<boolean>;
  cancel: () => Promise<void>;
}
function Content({
  store,
  finder,
  finderActions,
  securityInstaller,
}: {
  store: UpdateStore;
  finder: FindStore;
  finderActions: FinderActions;
  securityInstaller: SecurityInstaller;
}) {
  const t = useT();
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const { plugins, checking: refreshing, error: checkError } = snapshot;
  const loadFailed = Boolean(checkError);
  const [navigation, dispatch] = useReducer(navigate, initialNavigation);
  const [finding, setFinding] = useState(false);
  const [releaseReview, setReleaseReview] = useState<InstalledPlugin | null>(
    null,
  );
  const reviewReturn = useRef<{
    element: HTMLElement | null;
    container: HTMLElement | null;
    scroll: number;
  } | null>(null);
  function openReleaseReview(plugin: InstalledPlugin) {
    if (workingRef.current) return;
    const element = rootRef.current?.ownerDocument
      .activeElement as HTMLElement | null;
    const container =
      element?.closest<HTMLElement>(".ddu-details,.ddu-list") || null;
    reviewReturn.current = {
      element,
      container,
      scroll: container?.scrollTop || 0,
    };
    setReleaseReview(plugin);
  }
  function closeReleaseReview() {
    setReleaseReview(null);
    requestAnimationFrame(() => {
      const saved = reviewReturn.current;
      saved?.element?.focus({ preventScroll: true });
      if (saved?.container) saved.container.scrollTop = saved.scroll;
    });
  }
  useEffect(() => {
    if (!releaseReview) return;
    const current = plugins.find((plugin) => plugin.id === releaseReview.id);
    if (
      !current ||
      current.source !== releaseReview.source ||
      current.version !== releaseReview.version ||
      current.release_id !== releaseReview.release_id ||
      current.asset_id !== releaseReview.asset_id
    )
      closeReleaseReview();
  }, [plugins, releaseReview]);

  const searchButton = useRef<HTMLDivElement>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [rowActionId, setRowActionId] = useState<string | null>(null);
  const focusedRow = useRef<string | null>(null);
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [candidates, setCandidates] = useState<Record<string, Candidate[]>>({});
  const rootRef = useRef<HTMLDivElement>(null);
  usePanelHeight(rootRef);
  const listRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLDivElement | null>(null);
  const rows = useRef(new Map<string, HTMLDivElement>());
  const restoreList = useRef(false);
  const restoreView = useRef(false);
  const pendingList = useRef<{ scrollTop: number; focused: boolean } | null>(
    null,
  );
  const mounted = useRef(true);
  const workingRef = useRef(false);
  const visible = visiblePlugins(plugins, navigation.view);
  const selected = plugins.find((plugin) => plugin.id === navigation.detailId);

  const refresh = store.refresh;
  useEffect(() => {
    mounted.current = true;
    void store.refresh(false);
    return store.subscribe(() => {
      if (listRef.current)
        pendingList.current = {
          scrollTop: listRef.current.scrollTop,
          focused: listRef.current.contains(
            listRef.current.ownerDocument.activeElement,
          ),
        };
    });
  }, [store]);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );

  useLayoutEffect(() => {
    if (finding || releaseReview) return;
    if (selected) {
      backRef.current?.focus({ preventScroll: true });
      return;
    }
    if (restoreView.current && listRef.current) {
      listRef.current.scrollTop =
        navigation.bookmarks[navigation.view].scrollTop;
      restoreView.current = false;
    }
    if (restoreList.current && listRef.current) {
      const bookmark = navigation.bookmarks[navigation.view];
      const target =
        rows.current.get(bookmark.selectedId || "") ||
        rows.current.get(visible[0]?.id);
      restoreBookmark(listRef.current, target, bookmark);
      restoreList.current = false;
    }
  }, [navigation.detailId, navigation.view]);

  useLayoutEffect(() => {
    const pending = pendingList.current;
    if (finding || releaseReview) return;
    if (selected) {
      if (
        backRef.current &&
        !backRef.current.parentElement?.contains(
          backRef.current.ownerDocument.activeElement,
        )
      ) {
        backRef.current.focus({ preventScroll: true });
      }
      pendingList.current = null;
      return;
    }
    if (!pending || !listRef.current) return;
    const bookmark = navigation.bookmarks[navigation.view];
    const target = pending.focused
      ? rows.current.get(focusedRow.current || bookmark.selectedId || "") ||
        rows.current.get(visible[0]?.id)
      : undefined;
    restoreBookmark(listRef.current, target, {
      ...bookmark,
      scrollTop: pending.scrollTop,
    });
    pendingList.current = null;
  }, [plugins]);

  function back() {
    restoreList.current = true;
    dispatch({ type: "back" });
  }
  function changeView(view: View) {
    if (view === navigation.view) return;
    // The native focus stays on the chosen segment; each list keeps its scroll bookmark.
    const scrollTop = listRef.current?.scrollTop || 0;
    restoreView.current = true;
    dispatch({ type: "view", view, scrollTop });
  }

  async function action(plugin: InstalledPlugin, run: () => Promise<void>) {
    if (workingRef.current) return;
    workingRef.current = true;
    setWorking(plugin.id);
    setMessages((previous) => ({ ...previous, [plugin.id]: "" }));
    try {
      await run();
    } catch (error) {
      if (mounted.current)
        setMessages((previous) => ({
          ...previous,
          [plugin.id]: errorText(error),
        }));
    } finally {
      workingRef.current = false;
      if (mounted.current) setWorking(null);
    }
  }

  function update(plugin: InstalledPlugin) {
    return action(plugin, async () => {
      const response = await stage(
        plugin.id,
        plugin.release_id!,
        plugin.asset_id!,
      );
      if (response.error || !response.update)
        throw new Error(response.error || "Update preparation failed");
      const result = await securityInstaller.request(response.update);
      if (!result.requested) throw new Error(result.error);
      if (mounted.current)
        setMessages((previous) => ({
          ...previous,
          [plugin.id]:
            "Confirmation requested. Accept or cancel in Decky, then refresh to read the installed version.",
        }));
    });
  }

  const updates = plugins.filter((plugin) => plugin.status === "update").length;
  const emptyState =
    navigation.view === "updates"
      ? emptyUpdatesState(plugins, refreshing, loadFailed)
      : null;
  return (
    <NavigationGroup ref={rootRef} className="ddu" flow-children="column">
      <style>{styles}</style>
      {releaseReview && (
        <ReleaseReview
          key={`${releaseReview.id}:${releaseReview.source}:${releaseReview.version}:${releaseReview.release_id}`}
          name={releaseReview.name}
          installed={releaseReview.version}
          selected={releaseReview.latest || ""}
          notes={releaseReview.release_notes}
          source={releaseReview.source}
          busy={working !== null}
          message={messages[releaseReview.id]}
          onBack={closeReleaseReview}
          onContinue={() => update(releaseReview)}
        />
      )}
      <div hidden={Boolean(releaseReview)} style={{ display: "contents" }}>
        <NavigationGroup
          className="ddu-main"
          hidden={Boolean(selected) || finding}
          flow-children="column"
        >
          <NavigationGroup className="ddu-toolbar" flow-children="row">
            <NavigationGroup
              flow-children="row"
              className="ddu-tabs"
              role="tablist"
              aria-label={t("Plugin views")}
            >
              {(["updates", "all"] as const).map((view) => (
                <Focusable
                  key={view}
                  role="tab"
                  tabIndex={0}
                  className="ddu-tab"
                  focusClassName="ddu-focused"
                  aria-selected={navigation.view === view}
                  aria-controls="ddu-plugin-list"
                  onActivate={() => changeView(view)}
                  onClick={() => changeView(view)}
                >
                  <span
                    className="ddu-tab-label"
                    title={view === "updates" ? t("Updates") : t("All")}
                  >
                    {view === "updates" ? t("Updates") : t("All")}
                  </span>
                  <span className="ddu-tab-count">
                    ({view === "updates" ? updates : plugins.length})
                  </span>
                </Focusable>
              ))}
            </NavigationGroup>
            <Focusable
              ref={searchButton}
              role="button"
              tabIndex={0}
              className="ddu-icon-button"
              focusClassName="ddu-focused"
              aria-label={t("Find Plugins")}
              onActivate={() => setFinding(true)}
              onClick={() => setFinding(true)}
              onOKActionDescription={t("Find Plugins")}
            >
              <FaSearch aria-hidden="true" />
            </Focusable>
            <Focusable
              role="button"
              tabIndex={0}
              className="ddu-icon-button"
              focusClassName="ddu-focused"
              aria-label={
                refreshing ? t("Checking for updates") : t("Refresh updates")
              }
              aria-disabled={refreshing}
              onActivate={() => {
                if (!refreshing) void refresh(true);
              }}
              onClick={() => {
                if (!refreshing) void refresh(true);
              }}
              onOKActionDescription={t("Refresh")}
            >
              {refreshing ? (
                <Spinner style={{ width: 18, height: 18 }} />
              ) : (
                <FaSyncAlt aria-hidden="true" />
              )}
            </Focusable>
          </NavigationGroup>
          {(loadFailed ||
            plugins.some((plugin) => plugin.status === "error")) && (
            <div role="status" className="ddu-notice">
              {checkError || "Some checks failed. Open a plugin to retry."}
            </div>
          )}
          {rowActionId &&
            (working === rowActionId || messages[rowActionId]) && (
              <div className="ddu-notice" role="status">
                {plugins.find((plugin) => plugin.id === rowActionId)?.name}:{" "}
                {working === rowActionId
                  ? t("Preparing update…")
                  : t(messages[rowActionId])}
              </div>
            )}
          <NavigationGroup
            flow-children="column"
            id="ddu-plugin-list"
            ref={listRef}
            className="ddu-list"
            aria-label={
              navigation.view === "updates"
                ? t("Updates and sources to review")
                : t("Installed plugins")
            }
            aria-busy={refreshing}
          >
            {visible.map((plugin) => (
              <PluginRow
                key={plugin.id}
                plugin={plugin}
                busy={working !== null}
                updating={working === plugin.id}
                onUpdate={() => {
                  if (workingRef.current) return;
                  setRowActionId(plugin.id);
                  openReleaseReview(plugin);
                }}
                registerUpdate={(element) => {
                  if (element) rows.current.set(plugin.id + ":update", element);
                  else rows.current.delete(plugin.id + ":update");
                }}
                onUpdateFocus={() => {
                  focusedRow.current = plugin.id + ":update";
                  dispatch({ type: "focus", id: plugin.id });
                }}
                register={(element) => {
                  if (element) rows.current.set(plugin.id, element);
                  else rows.current.delete(plugin.id);
                }}
                onFocus={() => {
                  focusedRow.current = plugin.id;
                  dispatch({ type: "focus", id: plugin.id });
                }}
                onOpen={() =>
                  dispatch({
                    type: "open",
                    id: plugin.id,
                    scrollTop: listRef.current?.scrollTop || 0,
                  })
                }
              />
            ))}
            {!visible.length && emptyState && (
              <div className="ddu-success-empty" role="status">
                <div className="ddu-success-icon" aria-hidden="true">
                  <FaCheck />
                </div>
                <strong>{t("You're up to date")}</strong>
              </div>
            )}
            {!visible.length && !emptyState && (
              <div className="ddu-empty" role="status">
                {t(emptyMessage(plugins, refreshing, loadFailed))}
              </div>
            )}
          </NavigationGroup>
        </NavigationGroup>
        <FindPlugins
          open={finding}
          store={finder}
          onBack={() => {
            setFinding(false);
            requestAnimationFrame(() =>
              searchButton.current?.focus({ preventScroll: true }),
            );
          }}
          details={repositoryDetails}
          install={finderActions.install}
          checkInstallation={finderActions.check}
          cancelInstallation={finderActions.cancel}
        />
        {selected && !finding && (
          <PluginDetails
            loadSecurity={loadSecurity}
            canUninstall={
              selected.valid_identity === true &&
              plugins.filter((plugin) => plugin.name === selected.name)
                .length === 1
            }
            plugin={selected}
            loadReleases={releases}
            onInstallRelease={(release, confirmed) =>
              action(selected, async () => {
                if (release.asset_id === null)
                  throw new Error("No compatible ZIP");
                const response = await stageRelease(
                  selected.id,
                  release.release_id,
                  release.asset_id,
                  confirmed,
                );
                if (response.error || !response.update)
                  throw new Error(
                    response.error || "Version preparation failed",
                  );
                const result = await securityInstaller.request(response.update);
                if (!result.requested) throw new Error(result.error);
                if (mounted.current)
                  setMessages((previous) => ({
                    ...previous,
                    [selected.id]:
                      "Confirmation requested. Accept or cancel in Decky, then refresh to read the installed version.",
                  }));
              })
            }
            busy={working !== null}
            checking={refreshing}
            message={messages[selected.id]}
            candidates={candidates[selected.id] ?? selected.suggestions}
            onBack={back}
            backRef={(element) => {
              backRef.current = element;
            }}
            onRetry={() => {
              void refresh(true);
            }}
            onVerify={(repository) => {
              void action(selected, async () => {
                const response = await verify(selected.id, repository);
                if (response.error) throw new Error(response.error);
                if (mounted.current)
                  setCandidates((previous) => ({
                    ...previous,
                    [selected.id]: response.candidates,
                  }));
              });
            }}
            onSearch={() => {
              void action(selected, async () => {
                const response = await search(selected.id);
                if (response.error) throw new Error(response.error);
                if (!mounted.current) return;
                setCandidates((previous) => ({
                  ...previous,
                  [selected.id]: response.candidates,
                }));
                if (!response.candidates.length)
                  setMessages((previous) => ({
                    ...previous,
                    [selected.id]: "Source not found",
                  }));
              });
            }}
            onConfirm={(repository) => {
              void action(selected, async () => {
                const confirmation = await confirm(selected.id, repository);
                if (!confirmation.success)
                  throw new Error(
                    confirmation.error || "Could not confirm source",
                  );
                await refresh(false);
                if (mounted.current) {
                  backRef.current?.focus({ preventScroll: true });
                  setCandidates((previous) => ({
                    ...previous,
                    [selected.id]: [],
                  }));
                }
              });
            }}
            onUpdate={() => {
              openReleaseReview(selected);
            }}
          />
        )}
      </div>
    </NavigationGroup>
  );
}

function UpdateIcon({ store }: { store: UpdateStore }) {
  const t = useT();
  const quickAccessVisible = useQuickAccessVisible();
  useEffect(() => {
    if (quickAccessVisible) void store.refreshIfDue();
  }, [store, quickAccessVisible]);
  const { hasUpdates } = useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
  );
  return (
    <span
      style={{
        position: "relative",
        display: "inline-flex",
        width: "1em",
        height: "1em",
      }}
      aria-label={
        hasUpdates ? "Direct Updater: updates available" : "Direct Updater"
      }
    >
      <FaDownload />
      {hasUpdates && (
        <span
          role="status"
          aria-label={t("Stable updates available")}
          style={{
            position: "absolute",
            top: -3,
            right: -3,
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: "#52d681",
            boxShadow: "0 0 0 1px #171d25",
            pointerEvents: "none",
          }}
        />
      )}
    </span>
  );
}

export default definePlugin(() => {
  const frontend = { version: FRONTEND_VERSION, instance: crypto.randomUUID() };
  const securityInstaller = createSecurityInstaller({
    authorize: authorizeStaged,
    discard: discardStaged,
    request: (staged) => requestSelfUpdate(staged, undefined, frontend),
  });
  const store = createUpdateStore({
    list,
    check,
    listen(callback) {
      const listener = addEventListener<[InstalledPlugin]>(
        "update_result",
        callback,
      );
      return () => removeEventListener("update_result", listener);
    },
    schedule(callback, milliseconds) {
      const timer = setInterval(callback, milliseconds);
      return () => clearInterval(timer);
    },
  });
  const finder = createFindStore(findRepositories);
  const finderActions = createFindInstaller({
    stage: stageRepository,
    finish: finishRepository,
    request: securityInstaller.request,
    refresh: () => store.refresh(false),
    installed: (repository) => finder.installed(repository),
  });
  const stopInstallListener = listenForInstallCompletion((name) => {
    void finderActions.check(name).catch(() => {});
  });
  store.start();
  const checkWhenDue = () => void store.refreshIfDue();
  window.addEventListener("online", checkWhenDue);
  window.addEventListener("focus", checkWhenDue);
  const stopSelfUpdateWatch = watchSelfUpdate(
    async () => {
      await store.refresh(false);
      return list();
    },
    Navigation,
    frontend,
  );
  return {
    name: "Decky Direct Updater",
    titleView: <div>Direct Updater</div>,
    content: (
      <LanguageProvider key={frontend.instance}>
        <SecurityReviewBoundary installer={securityInstaller}>
          <Content
            store={store}
            finder={finder}
            finderActions={finderActions}
            securityInstaller={securityInstaller}
          />
        </SecurityReviewBoundary>
      </LanguageProvider>
    ),
    icon: <UpdateIcon store={store} />,
    onDismount() {
      securityInstaller.dispose();
      window.removeEventListener("online", checkWhenDue);
      window.removeEventListener("focus", checkWhenDue);
      stopSelfUpdateWatch();
      finderActions.dispose();
      stopInstallListener();
      finder.dispose();
      store.dispose();
    },
  };
});
