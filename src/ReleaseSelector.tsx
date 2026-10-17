import { DialogButton, Focusable } from "@decky/ui";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { FaArrowLeft, FaChevronRight } from "react-icons/fa";
import { NavigationGroup } from "./NavigationGroup";
import type { InstalledPlugin } from "./uiModel";

export interface ReleaseOption {
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
  const [releases, setReleases] = useState<ReleaseOption[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState<ReleaseOption | null>(null);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const back = useRef<HTMLDivElement>(null);
  const warningRef = useRef<HTMLDivElement>(null);
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
      loadActions.current?.contains(document.activeElement),
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
    if (warning) {
      const buttons =
        warningRef.current?.querySelectorAll<HTMLButtonElement>("button");
      buttons?.[buttons.length - 1]?.focus();
    } else if (restore.current) {
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
    if (!release.installable || busy || loading) return;
    returnTo.current = release.release_id;
    if (release.downgrade) {
      warningScroll.current = container.current?.scrollTop || 0;
      setWarning(release);
    } else void install(release, false);
  }
  return (
    <NavigationGroup
      ref={container}
      flow-children="column"
      className="ddu-details"
      onCancelButton={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (warning) cancelWarning();
        else onBack();
      }}
      onCancelActionDescription="Back"
      key={identity}
    >
      <Focusable
        ref={back}
        className="ddu-back"
        focusClassName="ddu-focused"
        role="button"
        tabIndex={0}
        onActivate={warning ? cancelWarning : onBack}
        onClick={warning ? cancelWarning : onBack}
      >
        <FaArrowLeft aria-hidden="true" /> Back
      </Focusable>
      <h2>{plugin.name}: Install another version</h2>
      <p>Installed: {plugin.version}</p>
      <p className="ddu-footnote">
        Prereleases may be unstable. Selecting one does not change future update
        checks, which continue to use stable releases.
      </p>
      {warning ? (
        <NavigationGroup
          ref={warningRef}
          flow-children="column"
          role="alertdialog"
          aria-label="Confirm downgrade"
          className="ddu-actions"
        >
          <h3>
            Downgrade from {plugin.version} to {warning.version}?
          </h3>
          <p>
            Older versions may not understand your current settings. Confirm
            before preparing this ZIP. Decky will also ask you to approve the
            installation.
          </p>
          <DialogButton
            disabled={busy}
            onClick={() => {
              const selected = warning;
              cancelWarning();
              void install(selected, true);
            }}
          >
            Confirm downgrade
          </DialogButton>
          <DialogButton disabled={busy} onClick={cancelWarning}>
            Cancel
          </DialogButton>
        </NavigationGroup>
      ) : (
        <>
          <NavigationGroup
            flow-children="column"
            aria-label="Plugin releases"
            aria-busy={loading}
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
                aria-disabled={!release.installable || busy || loading}
                onActivate={() => choose(release)}
                onClick={() => choose(release)}
              >
                <span className="ddu-release-text">
                  <span>
                    {release.version || release.tag}
                    {release.prerelease ? " · Prerelease" : ""}
                    {release.installed ? " · Installed" : ""}
                  </span>
                  {release.reason && !release.installed && (
                    <small>{release.reason}</small>
                  )}
                </span>
                {release.installable && (
                  <FaChevronRight
                    className="ddu-release-arrow"
                    aria-hidden="true"
                  />
                )}
              </Focusable>
            ))}
          </NavigationGroup>
          {!loading && !error && !releases.length && (
            <p>No published GitHub releases.</p>
          )}
          {loading && <p role="status">Loading releases…</p>}
          {error && <p role="alert">{error}</p>}
          <div ref={loadActions} className="ddu-actions">
            {(cursor || error) && (
              <DialogButton
                disabled={loading || busy}
                onClick={() => void more(cursor)}
              >
                {error ? "Retry loading releases" : "Load more"}
              </DialogButton>
            )}
          </div>
        </>
      )}
      {message && <p role="status">{message}</p>}
      {busy && <p role="status">Preparing ZIP…</p>}
    </NavigationGroup>
  );
}
