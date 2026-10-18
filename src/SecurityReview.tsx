import {
  DialogButton,
  DialogCheckbox,
  Focusable,
  type GamepadEvent,
} from "@decky/ui";
import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { FaExclamationTriangle, FaChevronRight } from "react-icons/fa";
import { Capabilities } from "./Capabilities";
import { NavigationGroup } from "./NavigationGroup";
import { useControllerNavigation } from "./useControllerNavigation";
import { useT } from "./i18n";
import { styles } from "./styles";
import type {
  SecurityFacts,
  SecurityInstaller,
  PendingReview,
} from "./securityInstaller";

export function SecurityDetails({
  facts,
  installed = false,
  onGamepadDirection,
}: {
  facts: SecurityFacts | null;
  installed?: boolean;
  onGamepadDirection?: (event: GamepadEvent) => void;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  return (
    <div className="ddu-security-details">
      <Focusable
        onGamepadDirection={onGamepadDirection}
        className="ddu-security-disclosure"
        focusClassName="ddu-focused"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-controls={detailsId}
        onActivate={() => setExpanded(!expanded)}
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(event) => {
          if (!event.repeat && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            setExpanded(!expanded);
          }
        }}
      >
        <FaChevronRight
          aria-hidden="true"
          className={expanded ? "ddu-disclosure-open" : undefined}
        />
        <span>{t("Security details")}</span>
      </Focusable>
      {expanded && (
        <div id={detailsId}>
          {installed && (
            <small className="ddu-source-label">{t("Installed version")}</small>
          )}
          {!facts ? (
            <p>{t("Installed access information is unavailable.")}</p>
          ) : (
            <>
              <Capabilities
                analysis={facts.capabilities}
                changes={facts.capability_changes}
                rootRequested={facts.root_requested}
                externalBinaries={facts.external_binaries}
              />
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function SecurityReview({
  review,
  installer,
}: {
  review: PendingReview;
  installer: SecurityInstaller;
}) {
  const t = useT();
  const cancel = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLDivElement>(null);
  const navigationRef = useRef<HTMLDivElement>(null);
  const controllerNavigation = useControllerNavigation(navigationRef);
  const staged = review.staged;
  const assessment = staged.security!;
  const token = staged.review_token!;
  const kinds = new Set(
    assessment.findings
      .filter((f) => f.severity === "warning")
      .map((f) => f.kind),
  );
  const root = kinds.has("root_added") || kinds.has("root_requested");
  const title = kinds.has("root_added")
    ? "This update requests more access"
    : root
      ? "This plugin requests administrator access"
      : kinds.has("privileged_execution")
        ? "Review administrator commands"
        : kinds.has("privileged_execution")
          ? "I understand this version will try to run administrator commands."
          : kinds.has("insecure_code_download")
            ? "I understand these code downloads are not protected by HTTPS."
            : kinds.has("downloaded_code_execution")
              ? "Review downloaded code execution"
              : assessment.updating
                ? "This update changes executable downloads"
                : "Review executable downloads";
  const acknowledgment = root
    ? "I understand it will have administrator access."
    : kinds.has("downloaded_code_execution")
      ? "I understand this version can run downloaded code."
      : "I understand Decky will download additional executable files.";
  useLayoutEffect(() => {
    const button = cancel.current?.querySelector<HTMLButtonElement>("button");
    button?.focus({ preventScroll: true });
    const panel = navigationRef.current;
    if (
      button &&
      panel &&
      button.getBoundingClientRect().bottom >
        panel.getBoundingClientRect().bottom
    ) {
      button.scrollIntoView({ block: "nearest" });
    }
  }, [token]);
  const onCancel = () => installer.cancel(token);
  return (
    <NavigationGroup
      ref={navigationRef}
      onGamepadDirection={controllerNavigation.onGamepadDirection}
      className="ddu ddu-security-review"
      flow-children="column"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="ddu-security-title"
      aria-describedby="ddu-security-explanation"
      onCancelButton={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onCancel();
      }}
      onCancelActionDescription={t("Cancel")}
      onKeyDown={(event) => {
        controllerNavigation.onKeyDown(event);
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          onCancel();
        }
      }}
    >
      <div className="ddu-security-body">
        <Focusable
          id="ddu-security-title"
          className="ddu-review-heading"
          ref={heading}
          role="heading"
          aria-level={2}
          tabIndex={0}
        >
          <FaExclamationTriangle aria-hidden="true" /> {t(title)}
        </Focusable>
        <p>
          {staged.name} ·{" "}
          {staged.previous_version ? `${staged.previous_version} → ` : ""}
          {staged.version}
        </p>
        <div id="ddu-security-explanation">
          {root && (
            <p>
              {t(
                "It can modify SteamOS files and settings. Install it only if you trust its developer.",
              )}
            </p>
          )}
          {kinds.has("privileged_execution") && (
            <p>
              {t(
                "This version tries to run commands with administrator privileges.",
              )}
            </p>
          )}
          {kinds.has("insecure_code_download") && (
            <p>
              {t(
                "Executable code is downloaded over HTTP. It could be changed in transit.",
              )}
            </p>
          )}
          {kinds.has("external_binary_project_changed") && (
            <div>
              <p>
                {t(
                  "An executable download now comes from a different project.",
                )}
              </p>
              <ul>
                {assessment.changed_binary_projects?.map((name) => {
                  const old = assessment.previous_external_binaries?.find(
                    (binary) => binary.name === name,
                  );
                  const next = assessment.external_binaries.find(
                    (binary) => binary.name === name,
                  );
                  return (
                    <li key={name}>
                      {name}: {old?.source_project || old?.source_host} →{" "}
                      {next?.source_project || next?.source_host}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          {kinds.has("downloaded_code_execution") && (
            <p>
              {t(
                "A command may download and run code. Review the details before continuing.",
              )}
            </p>
          )}
          {assessment.external_binaries.length > 0 && (
            <p>
              {t("Decky will download additional executable files.")}
              {kinds.has("external_binary_origin_changed") && (
                <> {t("Download source domains changed")}.</>
              )}
            </p>
          )}
          {kinds.has("comparison_unavailable") && (
            <p>
              {t("Installed access is unknown; changes cannot be compared.")}
            </p>
          )}
        </div>
        <Capabilities
          analysis={assessment.capabilities}
          changes={assessment.capability_changes}
          rootRequested={assessment.root_requested}
          externalBinaries={assessment.external_binaries}
          onGamepadDirection={controllerNavigation.onGamepadDirection}
        />
        <DialogCheckbox
          className="ddu-security-checkbox"
          controlled
          checked={review.acknowledged}
          label={t(acknowledgment)}
          onChange={(checked) => installer.acknowledge(token, checked)}
          onGamepadDirection={controllerNavigation.onGamepadDirection}
        />
      </div>
      <div className="ddu-actions ddu-security-actions" data-controller-row>
        <div ref={cancel}>
          <DialogButton
            onGamepadDirection={controllerNavigation.onGamepadDirection}
            onClick={onCancel}
          >
            {t("Cancel")}
          </DialogButton>
        </div>
        <DialogButton
          onGamepadDirection={controllerNavigation.onGamepadDirection}
          disabled={!review.acknowledged}
          onClick={() => installer.continue(token)}
        >
          {t("Continue")}
        </DialogButton>
      </div>
    </NavigationGroup>
  );
}

/** Hide rather than unmount the originating screen, preserving its selection and scroll. */
export function SecurityReviewBoundary({
  installer,
  children,
}: {
  installer: SecurityInstaller;
  children: ReactNode;
}) {
  const origin = useRef<HTMLElement | null>(null);
  const content = useRef<HTMLDivElement>(null);
  const lastFocused = useRef<HTMLElement | null>(null);
  const scroll = useRef<{ element: HTMLElement; top: number }[]>([]);
  const lastToken = useRef<string | null>(null);
  useEffect(
    () => () => {
      const token = installer.getSnapshot()?.staged.review_token;
      if (token) installer.cancel(token);
    },
    [installer],
  );
  const review = useSyncExternalStore(
    (callback) =>
      installer.subscribe(() => {
        const token = installer.getSnapshot()?.staged.review_token || null;
        if (token && token !== lastToken.current) {
          const active = content.current?.ownerDocument.activeElement;
          origin.current =
            active && content.current?.contains(active)
              ? (active as HTMLElement)
              : lastFocused.current;
          scroll.current = [];
          for (
            let element = origin.current;
            element;
            element = element.parentElement
          )
            scroll.current.push({ element, top: element.scrollTop });
        }
        lastToken.current = token;
        callback();
      }),
    installer.getSnapshot,
  );
  useLayoutEffect(() => {
    if (review || !origin.current || !installer.wasCancelled()) return;
    const target = origin.current;
    const saved = scroll.current;
    const frame = requestAnimationFrame(() => {
      if (target.isConnected) target.focus({ preventScroll: true });
      saved.forEach(({ element, top }) => {
        element.scrollTop = top;
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [review]);
  return (
    <>
      <style>{styles}</style>
      <div
        ref={content}
        hidden={Boolean(review)}
        onFocusCapture={(event) => {
          lastFocused.current = event.target as HTMLElement;
        }}
      >
        {children}
      </div>
      {review && (
        <SecurityReview
          key={review.staged.review_token}
          review={review}
          installer={installer}
        />
      )}
    </>
  );
}
