import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ReleaseSelector,
  type ReleaseOption,
  type ReleasePage,
} from "./ReleaseSelector";
import { DialogButton, Focusable, TextField } from "@decky/ui";
import { NavigationGroup } from "./NavigationGroup";
import { FaArrowLeft } from "react-icons/fa";
import {
  pluginActions,
  pluginStatus,
  type Candidate,
  type InstalledPlugin,
} from "./uiModel";

export function PluginDetails({
  plugin,
  busy,
  checking,
  message,
  candidates,
  onBack,
  onUpdate,
  onSearch,
  onVerify,
  onConfirm,
  onRetry,
  backRef,
  loadReleases,
  onInstallRelease,
}: {
  loadReleases: (id: string, cursor: string | null) => Promise<ReleasePage>;
  onInstallRelease: (
    release: ReleaseOption,
    confirmed: boolean,
  ) => Promise<void>;
  plugin: InstalledPlugin;
  busy: boolean;
  checking: boolean;
  message?: string;
  candidates?: Candidate[];
  onBack: () => void;
  onUpdate: () => void;
  onSearch: () => void;
  onVerify: (repository: string) => void;
  onConfirm: (repository: string) => void;
  onRetry: () => void;
  backRef: (element: HTMLDivElement | null) => void;
}) {
  const [versions, setVersions] = useState(false);
  const [manualSource, setManualSource] = useState(false);
  const [repository, setRepository] = useState("");
  useEffect(() => {
    setManualSource(false);
    setRepository("");
  }, [plugin.source]);
  const hasSuggestions = Boolean(candidates?.length);
  const versionButton = useRef<HTMLDivElement>(null);
  const restoring = useRef(false);
  const detailsScroll = useRef(0);
  useLayoutEffect(() => {
    if (!versions && restoring.current) {
      versionButton.current
        ?.querySelector<HTMLElement>("button,[tabindex='0']")
        ?.focus({ preventScroll: true });
      const details =
        versionButton.current?.closest<HTMLElement>(".ddu-details");
      if (details) details.scrollTop = detailsScroll.current;
      restoring.current = false;
    }
  }, [versions]);
  const actions = pluginActions(plugin);
  if (versions)
    return (
      <ReleaseSelector
        key={`${plugin.id}:${plugin.source}:${plugin.version}`}
        plugin={plugin}
        busy={busy}
        message={message}
        load={loadReleases}
        install={onInstallRelease}
        onBack={() => {
          restoring.current = true;
          setVersions(false);
        }}
      />
    );
  return (
    <NavigationGroup
      className="ddu-details"
      flow-children="column"
      onCancelButton={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onBack();
      }}
      onCancelActionDescription="Back"
    >
      <Focusable
        ref={backRef}
        className="ddu-back"
        focusClassName="ddu-focused"
        role="button"
        tabIndex={0}
        onActivate={onBack}
        onClick={onBack}
        onOKActionDescription="Back"
      >
        <FaArrowLeft aria-hidden="true" /> Back
      </Focusable>
      <h2>{plugin.name}</h2>
      <dl className="ddu-versions">
        <dt>Installed</dt>
        <dd>{plugin.version || "Unknown"}</dd>
        {plugin.latest && (
          <>
            <dt>Latest</dt>
            <dd>{plugin.latest}</dd>
          </>
        )}
      </dl>
      <div className="ddu-detail-status">{pluginStatus(plugin).label}</div>
      {plugin.source && (
        <div className="ddu-source">
          <span className="ddu-source-label">Source</span>
          {plugin.source}
        </div>
      )}
      {(message ||
        plugin.error ||
        plugin.source_note ||
        plugin.metadata_error ||
        plugin.discovery_error) && (
        <div role="status" className="ddu-detail-status">
          {message ||
            plugin.error ||
            plugin.discovery_error ||
            plugin.source_note ||
            plugin.metadata_error}
        </div>
      )}
      {plugin.status === "no_release" && (
        <p className="ddu-footnote">
          This repository has no stable GitHub release to install. Check the
          Decky Store for updates.
        </p>
      )}
      <div className="ddu-actions">
        {actions.update && (
          <DialogButton disabled={busy} onClick={onUpdate}>
            {busy ? "Preparing…" : "Update"}
          </DialogButton>
        )}
        {plugin.source && (
          <div ref={versionButton}>
            <DialogButton
              disabled={busy}
              onClick={() => {
                detailsScroll.current =
                  versionButton.current?.closest<HTMLElement>(".ddu-details")
                    ?.scrollTop || 0;
                setVersions(true);
              }}
            >
              Install another version
            </DialogButton>
          </div>
        )}
        {actions.findSource && !hasSuggestions && (
          <DialogButton disabled={busy} onClick={onSearch}>
            {busy ? "Please wait…" : "Find source"}
          </DialogButton>
        )}
        {actions.retry && (
          <DialogButton disabled={busy || checking} onClick={onRetry}>
            {checking ? "Checking…" : "Retry"}
          </DialogButton>
        )}
        {hasSuggestions && (
          <span className="ddu-source-label">
            Suggested GitHub{" "}
            {candidates!.length === 1 ? "repository" : "repositories"}
          </span>
        )}
        {candidates?.map((candidate) => (
          <div key={candidate.repository} className="ddu-candidate">
            <span>{candidate.repository}</span>
            <small>
              Owner: {candidate.owner || candidate.repository.split("/")[0]}
            </small>
            {candidate.description && <small>{candidate.description}</small>}
            <DialogButton
              disabled={busy}
              aria-label={`Use this source: ${candidate.repository}`}
              onClick={() => onConfirm(candidate.repository)}
            >
              Use this source
            </DialogButton>
          </div>
        ))}
        {hasSuggestions && (
          <DialogButton
            disabled={busy}
            className="ddu-secondary"
            onClick={onSearch}
          >
            Search again
          </DialogButton>
        )}
        {(!plugin.source || manualSource) && (
          <>
            {!manualSource ? (
              <DialogButton
                disabled={busy}
                className="ddu-secondary"
                onClick={() => setManualSource(true)}
              >
                Enter repository
              </DialogButton>
            ) : (
              <>
                <TextField
                  label="GitHub repository"
                  description="owner/repo or GitHub URL"
                  value={repository}
                  disabled={busy}
                  focusOnMount
                  onChange={(event) => setRepository(event.target.value)}
                />
                <DialogButton
                  disabled={busy || !repository.trim()}
                  onClick={() => onVerify(repository.trim())}
                >
                  Verify source
                </DialogButton>
              </>
            )}
          </>
        )}
        {actions.changeSource && (
          <DialogButton
            disabled={busy}
            className="ddu-secondary"
            onClick={() => {
              setManualSource(true);
              onSearch();
            }}
          >
            Change source
          </DialogButton>
        )}
      </div>
      {actions.update && (
        <p className="ddu-footnote">
          From the developer. May not have official Store review. Decky will ask
          you to confirm.
        </p>
      )}
    </NavigationGroup>
  );
}
