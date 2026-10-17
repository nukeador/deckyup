import { DialogButton, Focusable, TextField, Navigation } from "@decky/ui";
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { FaArrowLeft, FaSearch } from "react-icons/fa";
import { NavigationGroup } from "./NavigationGroup";
import {
  formatStars,
  type FindStore,
  type Repository,
  type RepositoryDetails,
} from "./findStore";

export function FindPlugins({
  open,
  store,
  onBack,
  details,
  install,
  checkInstallation,
  cancelInstallation,
}: {
  open: boolean;
  store: FindStore;
  onBack: () => void;
  details: (repository: string) => Promise<RepositoryDetails>;
  install: (selection: RepositoryDetails) => Promise<string>;
  checkInstallation: () => Promise<boolean>;
  cancelInstallation: () => Promise<void>;
}) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [selected, setSelected] = useState<Repository | null>(null);
  const [detail, setDetail] = useState<RepositoryDetails | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [requested, setRequested] = useState(false);
  const detailCache = useRef(
    new Map<string, { time: number; detail: RepositoryDetails }>(),
  );
  const backRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const rows = useRef(new Map<string, HTMLDivElement>());
  const bookmark = useRef({ id: "", scroll: 0 });
  const generation = useRef(0);
  const running = useRef(false);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  async function select(row: Repository) {
    bookmark.current = {
      id: row.repository,
      scroll: listRef.current?.scrollTop || 0,
    };
    const current = ++generation.current;
    setSelected(row);
    setDetail(null);
    setMessage("");
    setRequested(false);
    try {
      const cached = detailCache.current.get(row.repository);
      const result =
        cached && Date.now() - cached.time < 14400000
          ? cached.detail
          : await details(row.repository);
      if (generation.current !== current) return;
      if (!result.error)
        detailCache.current.set(row.repository, {
          time: Date.now(),
          detail: result,
        });
      setDetail(result);
    } catch {
      if (generation.current === current)
        setMessage("Could not check compatibility. Try again.");
    }
  }
  useEffect(() => {
    if (state.direct) {
      void select(state.direct);
      store.clearDirect();
    }
  }, [state.direct]);
  useEffect(() => {
    if (state.installedRepository) {
      detailCache.current.delete(state.installedRepository);
      if (selected?.repository === state.installedRepository) {
        setRequested(false);
        setMessage("Installed. Available under All.");
        setDetail((previous) =>
          previous ? { ...previous, status: "current" } : previous,
        );
      }
    }
  }, [state.installedRepository]);
  useLayoutEffect(() => {
    if (!open) return;
    if (selected) backRef.current?.focus({ preventScroll: true });
    else if (bookmark.current.id) {
      rows.current.get(bookmark.current.id)?.focus({ preventScroll: true });
      if (listRef.current) listRef.current.scrollTop = bookmark.current.scroll;
    } else backRef.current?.focus({ preventScroll: true });
  }, [open, selected?.repository]);
  function back() {
    if (selected) {
      generation.current++;
      setSelected(null);
      setDetail(null);
      setMessage("");
    } else onBack();
  }
  async function action(run: () => Promise<void>) {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    try {
      await run();
    } catch {
      setMessage("Installation failed. Try again.");
    } finally {
      running.current = false;
      setBusy(false);
    }
  }
  const row = selected;
  return (
    <NavigationGroup
      className="ddu-main"
      hidden={!open}
      flow-children="column"
      onCancelButton={(event) => {
        event.stopPropagation();
        if (document.activeElement?.matches("input,textarea")) {
          backRef.current?.focus({ preventScroll: true });
          return;
        }
        back();
      }}
    >
      <Focusable
        className="ddu-back"
        ref={backRef}
        role="button"
        tabIndex={0}
        focusClassName="ddu-focused"
        onActivate={back}
        onClick={back}
      >
        <FaArrowLeft /> {row ? "Back" : "Find Plugins"}
      </Focusable>
      <NavigationGroup
        className="ddu-main"
        hidden={Boolean(row)}
        flow-children="column"
      >
        <NavigationGroup className="ddu-find-input" flow-children="column">
          <TextField
            label="Search GitHub"
            value={state.query}
            onChange={(event) => store.type(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void store.submit();
              }
            }}
          />
          <DialogButton
            disabled={state.loading && state.query.trim() === state.submitted}
            onClick={() => void store.submit()}
          >
            <FaSearch /> Search
          </DialogButton>
        </NavigationGroup>
        <div className="ddu-notice">
          {state.loading
            ? "Searching GitHub…"
            : state.submitted
              ? "Relevant matches · most starred first"
              : "Enter a plugin name or owner/repository."}
        </div>
        {state.error && (
          <div role="status" className="ddu-notice">
            {state.error}
          </div>
        )}
        <NavigationGroup
          ref={listRef}
          className="ddu-list"
          flow-children="column"
          aria-label="GitHub repositories"
          aria-busy={state.loading}
        >
          {state.results.slice(0, state.visible).map((item) => (
            <Focusable
              key={item.repository}
              ref={(el) => {
                if (el) rows.current.set(item.repository, el);
                else rows.current.delete(item.repository);
              }}
              className="ddu-row"
              role="button"
              tabIndex={0}
              focusClassName="ddu-focused"
              onActivate={() => void select(item)}
              onClick={() => void select(item)}
              onOKActionDescription="Details"
            >
              <span className="ddu-row-text">
                <span className="ddu-name">{item.name}</span>
                <span className="ddu-subtitle">
                  {item.owner}
                  {item.fork ? " · Fork" : ""}
                  {item.archived ? " · Archived" : ""}
                  {item.disabled ? " · Disabled" : ""}
                  {item.description ? ` · ${item.description}` : ""}
                </span>
              </span>
              <span className="ddu-stars">★ {formatStars(item.stars)}</span>
            </Focusable>
          ))}
          {!state.loading &&
            state.submitted &&
            !state.results.length &&
            !state.error && (
              <div className="ddu-empty">No repositories found.</div>
            )}
          {(state.visible < state.results.length || state.next) && (
            <div className="ddu-actions">
              <DialogButton
                disabled={state.loading}
                onClick={() => void store.more()}
              >
                Show more
              </DialogButton>
            </div>
          )}
        </NavigationGroup>
      </NavigationGroup>
      {row && (
        <NavigationGroup className="ddu-details" flow-children="column">
          <h2>{row.name}</h2>
          <div>
            {row.owner} · ★ {formatStars(row.stars)}
            {row.fork ? " · Fork" : ""}
          </div>
          <p className="ddu-source">{row.description}</p>
          {!detail && !message && (
            <div role="status">Checking compatibility…</div>
          )}
          {detail?.version && (
            <dl className="ddu-versions">
              <dt>Latest Decky release</dt>
              <dd>{detail.version}</dd>
              {detail.installed_version && (
                <>
                  <dt>Installed</dt>
                  <dd>{detail.installed_version}</dd>
                </>
              )}
            </dl>
          )}
          {detail?.error && <p role="status">{detail.error}</p>}
          {message && (
            <p className="ddu-detail-status" role="status">
              {message}
            </p>
          )}
          <NavigationGroup className="ddu-actions" flow-children="column">
            <DialogButton
              disabled={
                busy ||
                requested ||
                !detail?.token ||
                !["install", "update"].includes(detail.status)
              }
              onClick={() =>
                void action(async () => {
                  const result = await install(detail!);
                  if (!result.startsWith("Confirmation requested"))
                    detailCache.current.delete(row.repository);
                  setMessage(result);
                  setRequested(result.startsWith("Confirmation requested"));
                })
              }
            >
              {detail?.status === "update"
                ? "Update"
                : detail?.status === "current"
                  ? "Up to date"
                  : detail?.status === "version_unavailable"
                    ? "Version unavailable"
                    : "Install"}
            </DialogButton>
            {requested && (
              <>
                <DialogButton
                  disabled={busy}
                  onClick={() =>
                    void action(async () => {
                      const completed = await checkInstallation();
                      setMessage(
                        completed
                          ? "Installed. Available under All."
                          : "Installation not confirmed. Accept or cancel in Decky.",
                      );
                      if (completed) {
                        setRequested(false);
                        detailCache.current.delete(row.repository);
                        setDetail({ ...detail!, status: "current" });
                      }
                    })
                  }
                >
                  Check installation
                </DialogButton>
                <DialogButton
                  disabled={busy}
                  onClick={() =>
                    void action(async () => {
                      await cancelInstallation();
                      setRequested(false);
                      setMessage(
                        "If you cancelled in Decky, nothing was installed.",
                      );
                    })
                  }
                >
                  I cancelled in Decky
                </DialogButton>
              </>
            )}
            {detail?.error && (
              <DialogButton disabled={busy} onClick={() => void select(row)}>
                Retry
              </DialogButton>
            )}
            <DialogButton
              onClick={() =>
                Navigation.NavigateToExternalWeb(
                  `https://github.com/${row.repository}`,
                )
              }
            >
              View on GitHub
            </DialogButton>
          </NavigationGroup>
        </NavigationGroup>
      )}
    </NavigationGroup>
  );
}
