import { ReleaseReview, type ReleaseNotes } from "./ReleaseReview";
import { useT } from "./i18n";
import { DialogButton, Focusable, Spinner } from "@decky/ui";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { FaArrowLeft, FaChevronRight } from "react-icons/fa";
import { NavigationGroup } from "./NavigationGroup";
import type { InstalledPlugin } from "./uiModel";

export interface ReleaseOption {
  release_notes?: ReleaseNotes;
  release_id: string | number;
  asset_id: string | number | null;
  tag: string;
  version: string | null;
  prerelease: boolean;
  installed: boolean;
  downgrade: boolean;
  installable: boolean;
  reason: string | null;
}
export interface ReleasePage {
  releases: ReleaseOption[];
  next_cursor: string | null;
  installed_version?: string;
  error: string | null;
}
export function mergeReleases(
  previous: ReleaseOption[],
  next: ReleaseOption[],
) {
  const merged = new Map(
    previous.map((release) => [release.release_id, release]),
  );
  next.forEach((release) => merged.set(release.release_id, release));
  return [...merged.values()];
}
export function ReleaseSelector({
  plugin,
  busy,
  message,
  load,
  install,
  onBack,
}: {
  plugin: InstalledPlugin;
  busy: boolean;
  message?: string;
  load: (id: string, cursor: string | null) => Promise<ReleasePage>;
  install: (release: ReleaseOption, confirmed: boolean) => Promise<void>;
  onBack: () => void;
}) {
  const t = useT();
  const [releases, setReleases] = useState<ReleaseOption[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState<ReleaseOption | null>(null);
  const [pendingRelease, setPendingRelease] = useState<string | number | null>(
    null,
  );
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const back = useRef<HTMLDivElement>(null);
  const rows = useRef(new Map<string | number, HTMLDivElement>());
  const returnTo = useRef<string | number | null>(null);
  const restore = useRef(false);
  const container = useRef<HTMLDivElement>(null);
  const scroll = useRef<number | null>(null);
  const warningScroll = useRef(0);
  const loadActions = useRef<HTMLDivElement>(null);
  const restoreLoadFocus = useRef(false);
  const firstAdded = useRef<string | number | null>(null);
  // A source/version change invalidates the catalogue and any downgrade consent.
  const identity = `${plugin.id}\0${plugin.source}\0${plugin.version}`;
  async function more(next: string | null) {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError("");
    scroll.current = container.current?.scrollTop ?? 0;
    restoreLoadFocus.current = Boolean(
      loadActions.current?.contains(
        loadActions.current.ownerDocument.activeElement,
      ),
    );
    try {
      const page = await load(plugin.id, next);
      if (!mounted.current) return;
      if (page.error) throw new Error(page.error);
      firstAdded.current =
        page.releases.find(
          (item) => !releases.some((old) => old.release_id === item.release_id),
        )?.release_id ?? null;
      setReleases((previous) =>
        mergeReleases(next ? previous : [], page.releases),
      );
      setCursor(page.next_cursor);
    } catch (error) {
      if (mounted.current) setError(String(error).replace(/^Error:\s*/, ""));
    } finally {
      inFlight.current = false;
      if (mounted.current) setLoading(false);
    }
  }
  useEffect(() => {
    mounted.current = true;
    void more(null);
    back.current?.focus({ preventScroll: true });
    return () => {
      mounted.current = false;
    };
  }, []);
  useLayoutEffect(() => {
    if (!loading && scroll.current !== null && container.current) {
      container.current.scrollTop = scroll.current;
      scroll.current = null;
      if (restoreLoadFocus.current) {
        const button =
          loadActions.current?.querySelector<HTMLButtonElement>("button");
        const target = button || rows.current.get(firstAdded.current!);
        target?.focus({ preventScroll: true });
        if (!button) target?.scrollIntoView({ block: "nearest" });
        restoreLoadFocus.current = false;
      }
    }
  }, [releases, loading]);
  useLayoutEffect(() => {
    if (!warning && restore.current) {
      rows.current.get(returnTo.current!)?.focus({ preventScroll: true });
      if (container.current)
        container.current.scrollTop = warningScroll.current;
      restore.current = false;
    }
  }, [warning]);
  function cancelWarning() {
    restore.current = true;
    setWarning(null);
  }
  function choose(release: ReleaseOption) {
    if (!release.installable || busy || loading || pendingRelease !== null)
      return;
    returnTo.current = release.release_id;
    warningScroll.current = container.current?.scrollTop || 0;
    setWarning(release);
  }
  async function startInstall(release: ReleaseOption, confirmed: boolean) {
    if (pendingRelease !== null || busy) return;
    setPendingRelease(release.release_id);
    try {
      await install(release, confirmed);
    } finally {
      if (mounted.current) setPendingRelease(null);
    }
  }
  return (
    <NavigationGroup
      ref={container}
      flow-children="column"
      className={warning ? "ddu-release-review-host" : "ddu-details"}
      onCancelButton={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (warning) cancelWarning();
        else onBack();
      }}
      onCancelActionDescription={t("Back")}
      key={identity}
    >
      <div hidden={Boolean(warning)}>
        <Focusable
          ref={back}
          className="ddu-back"
          focusClassName="ddu-focused"
          role="button"
          tabIndex={0}
          onActivate={warning ? cancelWarning : onBack}
          onClick={warning ? cancelWarning : onBack}
        >
          <FaArrowLeft aria-hidden="true" /> {t("Back")}
        </Focusable>
        <h2>
          {plugin.name}: {t("Install another version")}
        </h2>
        <p>
          {t("Installed")}: {plugin.version}
        </p>
        <p className="ddu-footnote">{t("Prerelease notice")}</p>
      </div>
      {warning && (
        <ReleaseReview
          key={`${identity}:${warning.release_id}`}
          name={plugin.name}
          installed={plugin.version}
          selected={warning.version || warning.tag}
          notes={warning.release_notes}
          source={plugin.source}
          downgrade={warning.downgrade}
          busy={busy}
          message={message}
          onBack={cancelWarning}
          onContinue={() => startInstall(warning, warning.downgrade)}
        />
      )}
      <div hidden={Boolean(warning)}>
        {pendingRelease !== null && (
          <div
            className="ddu-release-progress"
            role="status"
            aria-live="polite"
          >
            <Spinner style={{ width: 22, height: 22 }} />
            <span>{t("Preparing ZIP…")}</span>
          </div>
        )}
        <NavigationGroup
          flow-children="column"
          aria-label={t("Plugin releases")}
          aria-busy={loading || pendingRelease !== null}
        >
          {releases.map((release) => (
            <Focusable
              key={release.release_id}
              ref={(element: HTMLDivElement | null) => {
                if (element) rows.current.set(release.release_id, element);
                else rows.current.delete(release.release_id);
              }}
              className="ddu-release"
              focusClassName="ddu-focused"
              role="button"
              tabIndex={0}
              aria-disabled={
                !release.installable ||
                busy ||
                loading ||
                pendingRelease !== null
              }
              onActivate={() => choose(release)}
              onClick={() => choose(release)}
            >
              <span className="ddu-release-text">
                <span>
                  {release.version || release.tag}
                  {release.prerelease ? ` · ${t("Prerelease")}` : ""}
                  {release.installed ? ` · ${t("Installed")}` : ""}
                </span>
                {release.reason && !release.installed && (
                  <small>{t(release.reason)}</small>
                )}
              </span>
              {pendingRelease === release.release_id ? (
                <Spinner style={{ width: 18, height: 18, flexShrink: 0 }} />
              ) : release.installable ? (
                <FaChevronRight
                  className="ddu-release-arrow"
                  aria-hidden="true"
                />
              ) : null}
            </Focusable>
          ))}
        </NavigationGroup>
        {!loading && !error && !releases.length && (
          <p>{t("No published GitHub releases.")}</p>
        )}
        {loading && <p role="status">{t("Loading releases…")}</p>}
        {error && <p role="alert">{error}</p>}
        <div ref={loadActions} className="ddu-actions">
          {(cursor || error) && (
            <DialogButton
              disabled={loading || busy}
              onClick={() => void more(cursor)}
            >
              {error ? t("Retry loading releases") : t("Load more")}
            </DialogButton>
          )}
        </div>
      </div>
      {!warning && message && <p role="status">{t(message)}</p>}
    </NavigationGroup>
  );
}
