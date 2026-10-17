import {
  addEventListener,
  removeEventListener,
  callable,
  definePlugin,
} from "@decky/api";
import { Focusable, Spinner } from "@decky/ui";
import {
  useEffect,
  useLayoutEffect,
  useReducer,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { FaDownload, FaSyncAlt } from "react-icons/fa";
import { requestUpdate, type StagedUpdate } from "./deckyInstaller";
import { NavigationGroup } from "./NavigationGroup";
import type { ReleasePage } from "./ReleaseSelector";
import { PluginDetails } from "./PluginDetails";
import { PluginRow } from "./PluginRow";
import { usePanelHeight } from "./usePanelHeight";
import { createUpdateStore, type UpdateStore } from "./updateStore";
import { styles } from "./styles";
import {
  emptyMessage,
  initialNavigation,
  navigate,
  restoreBookmark,
  visiblePlugins,
  type Candidate,
  type InstalledPlugin,
  type View,
} from "./uiModel";

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

function Content({ store }: { store: UpdateStore }) {
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const { plugins, checking: refreshing, error: checkError } = snapshot;
  const loadFailed = Boolean(checkError);
  const [navigation, dispatch] = useReducer(navigate, initialNavigation);
  const [working, setWorking] = useState<string | null>(null);
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
          focused: listRef.current.contains(document.activeElement),
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
    if (selected) {
      if (
        backRef.current &&
        !backRef.current.parentElement?.contains(document.activeElement)
      ) {
        backRef.current.focus({ preventScroll: true });
      }
      pendingList.current = null;
      return;
    }
    if (!pending || !listRef.current) return;
    const bookmark = navigation.bookmarks[navigation.view];
    const target = pending.focused
      ? rows.current.get(bookmark.selectedId || "") ||
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

  const updates = plugins.filter((plugin) => plugin.status === "update").length;
  return (
    <NavigationGroup ref={rootRef} className="ddu" flow-children="column">
      <style>{styles}</style>
      <NavigationGroup
        className="ddu-main"
        hidden={Boolean(selected)}
        flow-children="column"
      >
        <NavigationGroup className="ddu-toolbar" flow-children="row">
          <NavigationGroup
            flow-children="row"
            className="ddu-tabs"
            role="tablist"
            aria-label="Plugin views"
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
                {view === "updates"
                  ? `Updates (${updates})`
                  : `All (${plugins.length})`}
              </Focusable>
            ))}
          </NavigationGroup>
          <Focusable
            role="button"
            tabIndex={0}
            className="ddu-icon-button"
            focusClassName="ddu-focused"
            aria-label={refreshing ? "Checking for updates" : "Refresh updates"}
            aria-disabled={refreshing}
            onActivate={() => {
              if (!refreshing) void refresh(true);
            }}
            onClick={() => {
              if (!refreshing) void refresh(true);
            }}
            onOKActionDescription="Refresh"
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
        <NavigationGroup
          flow-children="column"
          id="ddu-plugin-list"
          ref={listRef}
          className="ddu-list"
          aria-label={
            navigation.view === "updates"
              ? "Updates and sources to review"
              : "Installed plugins"
          }
          aria-busy={refreshing}
        >
          {visible.map((plugin) => (
            <PluginRow
              key={plugin.id}
              plugin={plugin}
              register={(element) => {
                if (element) rows.current.set(plugin.id, element);
                else rows.current.delete(plugin.id);
              }}
              onFocus={() => dispatch({ type: "focus", id: plugin.id })}
              onOpen={() =>
                dispatch({
                  type: "open",
                  id: plugin.id,
                  scrollTop: listRef.current?.scrollTop || 0,
                })
              }
            />
          ))}
          {!visible.length && (
            <div className="ddu-empty" role="status">
              {emptyMessage(plugins, refreshing, loadFailed)}
            </div>
          )}
        </NavigationGroup>
      </NavigationGroup>
      {selected && (
        <PluginDetails
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
                throw new Error(response.error || "Version preparation failed");
              const result = await requestUpdate(response.update);
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
            void action(selected, async () => {
              const response = await stage(
                selected.id,
                selected.release_id!,
                selected.asset_id!,
              );
              if (response.error || !response.update)
                throw new Error(response.error || "Update preparation failed");
              const result = await requestUpdate(response.update);
              if (!result.requested) throw new Error(result.error);
              if (mounted.current)
                setMessages((previous) => ({
                  ...previous,
                  [selected.id]:
                    "Confirmation requested. Accept or cancel in Decky, then refresh to read the installed version.",
                }));
            });
          }}
        />
      )}
    </NavigationGroup>
  );
}

function UpdateIcon({ store }: { store: UpdateStore }) {
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
          aria-label="Stable updates available"
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
  store.start();
  return {
    name: "Decky Direct Updater",
    titleView: <div>Direct Updater</div>,
    content: <Content store={store} />,
    icon: <UpdateIcon store={store} />,
    onDismount() {
      store.dispose();
    },
  };
});
