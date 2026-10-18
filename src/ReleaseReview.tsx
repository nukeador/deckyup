import { DialogButton, Focusable, Spinner } from "@decky/ui";
import { useId, useLayoutEffect, useRef, useState } from "react";
import { FaArrowLeft, FaChevronDown, FaChevronUp } from "react-icons/fa";
import { NavigationGroup } from "./NavigationGroup";
import { useControllerNavigation } from "./useControllerNavigation";
import { useT } from "./i18n";

export interface ReleaseNotes {
  notes?: string | null;
  notes_truncated?: boolean | null;
  release_url?: string | null;
}

export function notesPreview(body: string) {
  const lines = body.split("\n").filter((line) => line.trim());
  const preview: string[] = [];
  let length = 0;
  for (const line of lines) {
    if (preview.length >= 3 || length >= 320) break;
    const remaining = 360 - length;
    if (line.length > remaining) {
      const cut = line.slice(0, remaining);
      preview.push(
        cut.slice(
          0,
          cut.lastIndexOf(" ") > 0 ? cut.lastIndexOf(" ") : cut.length,
        ) + "…",
      );
      break;
    }
    preview.push(line);
    length += line.length;
  }
  const text = preview.join("\n");
  return { text, more: text !== lines.join("\n") };
}

export function ReleaseReview({
  name,
  installed,
  selected,
  notes,
  source,
  downgrade = false,
  busy = false,
  message,
  onBack,
  onContinue,
}: {
  name: string;
  installed?: string;
  selected: string;
  notes?: ReleaseNotes;
  source?: string;
  downgrade?: boolean;
  busy?: boolean;
  message?: string;
  onBack: () => void;
  onContinue: () => void | Promise<void>;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const notesId = useId();
  const [pending, setPending] = useState(false);
  const active = useRef(false);
  const back = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const navigation = useControllerNavigation(root);
  useLayoutEffect(() => {
    back.current?.focus({ preventScroll: true });
  }, []);
  const body = notes?.notes || "";
  const preview = notesPreview(body);
  async function proceed() {
    if (active.current || busy) return;
    active.current = true;
    setPending(true);
    try {
      await onContinue();
    } finally {
      active.current = false;
      setPending(false);
    }
  }
  function cancel() {
    if (!active.current && !busy) onBack();
  }
  return (
    <NavigationGroup
      ref={root}
      {...navigation}
      className="ddu-details"
      flow-children="column"
      onCancelButton={(event) => {
        event.preventDefault();
        event.stopPropagation();
        cancel();
      }}
      onCancelActionDescription={t("Back")}
    >
      <Focusable
        ref={back}
        onGamepadDirection={navigation.onGamepadDirection}
        className="ddu-back"
        focusClassName="ddu-focused"
        role="button"
        tabIndex={0}
        onActivate={cancel}
        onClick={cancel}
      >
        <FaArrowLeft aria-hidden="true" /> {t("Back")}
      </Focusable>
      <h2>{name}</h2>
      <p>
        {installed} → {selected}
      </p>
      {downgrade && <p role="alert">{t("Downgrade warning")}</p>}
      <strong>{t("What's new")}</strong>
      <p
        id={notesId}
        style={{ whiteSpace: "pre-line", overflowWrap: "anywhere" }}
      >
        {body
          ? expanded
            ? body
            : preview.text
          : t("No release notes provided")}
      </p>
      {preview.more && (
        <Focusable
          role="button"
          tabIndex={0}
          onGamepadDirection={navigation.onGamepadDirection}
          className="ddu-notes-toggle"
          focusClassName="ddu-focused"
          aria-label={t(expanded ? "Show less" : "Show more")}
          aria-expanded={expanded}
          aria-controls={notesId}
          onActivate={() => setExpanded((value) => !value)}
          onClick={() => setExpanded((value) => !value)}
          onKeyDown={(event) => {
            if (!event.repeat && (event.key === "Enter" || event.key === " ")) {
              event.preventDefault();
              event.stopPropagation();
              setExpanded((value) => !value);
            }
          }}
        >
          {expanded ? (
            <FaChevronUp aria-hidden="true" />
          ) : (
            <FaChevronDown aria-hidden="true" />
          )}
        </Focusable>
      )}
      {notes?.notes_truncated && (
        <small>{t("More release notes available on GitHub")}</small>
      )}
      {source && (
        <p className="ddu-footnote">
          {t("Source")}: {source}
        </p>
      )}
      <DialogButton
        onGamepadDirection={navigation.onGamepadDirection}
        disabled={busy || pending}
        onClick={() => void proceed()}
      >
        {busy || pending ? (
          <span className="ddu-action-label">
            <Spinner style={{ width: 18, height: 18 }} />
            {t("Preparing ZIP…")}
          </span>
        ) : (
          t(downgrade ? "Continue with downgrade" : "Continue")
        )}
      </DialogButton>
      {message && <p role="status">{t(message)}</p>}
    </NavigationGroup>
  );
}
