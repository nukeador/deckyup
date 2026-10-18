import { useT } from "./i18n";
import { SecurityDetails } from "./SecurityReview";
import { requestUninstallConfirmation } from "./deckyInstaller";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ReleaseSelector,
  type ReleaseOption,
  type ReleasePage,
} from "./ReleaseSelector";
import { DialogButton, Focusable, TextField, Navigation } from "@decky/ui";
import { NavigationGroup } from "./NavigationGroup";
import {
  FaArrowLeft,
  FaDownload,
  FaHistory,
  FaSearch,
  FaSyncAlt,
  FaExternalLinkAlt,
  FaExchangeAlt,
  FaTrashAlt,
} from "react-icons/fa";
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
  canUninstall = false,
}: {
  canUninstall?: boolean;
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
  const t = useT();
  const [versions, setVersions] = useState(false);
  const [manualSource, setManualSource] = useState(false);
  const [repository, setRepository] = useState("");
  const [uninstallError, setUninstallError] = useState("");
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
  const githubRepository =
    plugin.source && /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(plugin.source)
      ? plugin.source
      : null;
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
      onCancelActionDescription={t("Back")}
    >
      <Focusable
        ref={backRef}
        className="ddu-back"
        focusClassName="ddu-focused"
        role="button"
        tabIndex={0}
        onActivate={onBack}
        onClick={onBack}
        onOKActionDescription={t("Back")}
      >
        <FaArrowLeft aria-hidden="true" /> {t("Back")}
      </Focusable>
      <h2>{plugin.name}</h2>
      <dl className="ddu-versions">
        <dt>{t("Installed")}</dt>
        <dd>{plugin.version || t("Unknown version")}</dd>
        {plugin.latest && (
          <>
            <dt>{t("Latest")}</dt>
            <dd>{plugin.latest}</dd>
          </>
        )}
      </dl>
      <div className="ddu-detail-status">{t(pluginStatus(plugin).label)}</div>
      <SecurityDetails facts={plugin.security || null} installed />
      {plugin.source && (
        <div className="ddu-source">
          <span className="ddu-source-label">{t("Source")}</span>
          {plugin.source}
        </div>
      )}
      {(message ||
        plugin.error ||
        plugin.source_note ||
        plugin.metadata_error ||
        plugin.discovery_error) && (
        <div role="status" className="ddu-detail-status">
          {message
            ? t(message)
            : plugin.error ||
              plugin.discovery_error ||
              plugin.source_note ||
              plugin.metadata_error}
        </div>
      )}
      {plugin.status === "no_release" && (
        <p className="ddu-footnote">{t("No stable release notice")}</p>
      )}
      <div className="ddu-actions">
        {actions.update && (
          <DialogButton disabled={busy} onClick={onUpdate}>
            <span className="ddu-action-label">
              <FaDownload aria-hidden="true" />
              {busy ? t("Preparing…") : t("Update")}
            </span>
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
              <span className="ddu-action-label">
                <FaHistory aria-hidden="true" />
                {t("Install another version")}
              </span>
            </DialogButton>
          </div>
        )}
        {githubRepository && (
          <DialogButton
            onClick={() =>
              Navigation.NavigateToExternalWeb(
                `https://github.com/${githubRepository}`,
              )
            }
          >
            <span className="ddu-action-label">
              <FaExternalLinkAlt aria-hidden="true" />
              {t("View website")}
            </span>
          </DialogButton>
        )}
        {actions.findSource && !hasSuggestions && (
          <DialogButton disabled={busy} onClick={onSearch}>
            <span className="ddu-action-label">
              <FaSearch aria-hidden="true" />
              {busy ? t("Please wait…") : t("Find source")}
            </span>
          </DialogButton>
        )}
        {actions.retry && (
          <DialogButton disabled={busy || checking} onClick={onRetry}>
            <span className="ddu-action-label">
              <FaSyncAlt aria-hidden="true" />
              {checking ? t("Checking…") : t("Retry")}
            </span>
          </DialogButton>
        )}
        {hasSuggestions && (
          <span className="ddu-source-label">
            {t(
              candidates!.length === 1
                ? "Suggested GitHub repository"
                : "Suggested GitHub repositories",
            )}
          </span>
        )}
        {candidates?.map((candidate) => (
          <div key={candidate.repository} className="ddu-candidate">
            <span>{candidate.repository}</span>
            <small>
              {t("Owner")}:{" "}
              {candidate.owner || candidate.repository.split("/")[0]}
            </small>
            {candidate.description && <small>{candidate.description}</small>}
            <DialogButton
              disabled={busy}
              aria-label={`${t("Use this source")}: ${candidate.repository}`}
              onClick={() => onConfirm(candidate.repository)}
            >
              {t("Use this source")}
            </DialogButton>
          </div>
        ))}
        {hasSuggestions && (
          <DialogButton
            disabled={busy}
            className="ddu-secondary"
            onClick={onSearch}
          >
            {t("Search again")}
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
                {t("Enter repository")}
              </DialogButton>
            ) : (
              <>
                <TextField
                  label={t("GitHub repository")}
                  description={t("Repository hint")}
                  value={repository}
                  disabled={busy}
                  focusOnMount
                  onChange={(event) => setRepository(event.target.value)}
                />
                <DialogButton
                  disabled={busy || !repository.trim()}
                  onClick={() => onVerify(repository.trim())}
                >
                  {t("Verify source")}
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
            <span className="ddu-action-label">
              <FaExchangeAlt aria-hidden="true" />
              {t("Change source")}
            </span>
          </DialogButton>
        )}
        <DialogButton
          disabled={busy || checking || !canUninstall}
          className="ddu-uninstall"
          onClick={() => {
            if (!canUninstall || busy || checking) return;
            const result = requestUninstallConfirmation(plugin.name, {
              title: `${t("Uninstall plugin")}: ${plugin.name}`,
              button: t("Uninstall"),
              description: t("Do you want to uninstall this plugin?"),
            });
            setUninstallError(result.error || "");
          }}
        >
          <span className="ddu-action-label">
            <FaTrashAlt aria-hidden="true" />
            {t("Uninstall")}
          </span>
        </DialogButton>
      </div>
      {uninstallError && (
        <p role="status" className="ddu-footnote">
          {t(uninstallError)}
        </p>
      )}
      {actions.update && (
        <p className="ddu-footnote">{t("Developer source notice")}</p>
      )}
    </NavigationGroup>
  );
}
