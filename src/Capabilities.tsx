import { useId, useState } from "react";
import { Focusable, type GamepadEvent } from "@decky/ui";
import {
  FaWifi,
  FaFolder,
  FaSteam,
  FaTerminal,
  FaShieldAlt,
  FaUsb,
  FaCog,
  FaBox,
  FaChevronRight,
} from "react-icons/fa";
import { useT } from "./i18n";
import type {
  CapabilityAnalysis,
  CapabilityChanges,
  SecurityFacts,
} from "./securityInstaller";

const categories = {
  network: [
    FaWifi,
    "Network access",
    "Can connect to the internet and exchange data.",
  ],
  filesystem: [
    FaFolder,
    "Access to your files",
    "Can read or change files accessible to your SteamOS user.",
  ],
  steam_data: [
    FaSteam,
    "Access to Steam files",
    "Can access Steam settings, user data or library files.",
  ],
  process_execution: [
    FaTerminal,
    "Run system commands",
    "Can start other programs or run commands on your Deck.",
  ],
  root: [
    FaShieldAlt,
    "Administrator access",
    "Administrator access allows changes to files and settings across SteamOS.",
  ],
  devices: [
    FaUsb,
    "Access to devices",
    "May interact with connected devices or their controls.",
  ],
  system_config: [
    FaCog,
    "Change system settings",
    "May change SteamOS settings, such as power options or services.",
  ],
  native_binaries: [
    FaBox,
    "Additional programs",
    "Includes or downloads these programs. Their behavior has not been analyzed.",
  ],
} as const;

function deviceLabel(path: string): string {
  if (/^\/dev\/snd\/pcm.*c$/.test(path))
    return "Audio input (such as a microphone)";
  if (path === "/dev/snd" || path.startsWith("/dev/snd/"))
    return "Audio devices";
  if (path === "/dev/input" || path.startsWith("/dev/input/"))
    return "Input devices";
  if (path.startsWith("/dev/hidraw")) return "Connected input devices";
  if (path === "/dev/dri" || path.startsWith("/dev/dri/"))
    return "Graphics hardware";
  if (/^\/dev\/video\d+(?:$|\/)/.test(path)) return "Video capture devices";
  return path;
}
const targetNotes: Record<string, string> = {
  network: "It may also connect to other unidentified destinations.",
  filesystem: "It may also access other files and folders.",
  process_execution: "It may also run other unidentified commands.",
  devices: "It may also access other unidentified devices.",
};

export function Capabilities({
  analysis,
  changes,
  rootRequested = false,
  externalBinaries = [],
  onGamepadDirection,
}: {
  analysis?: CapabilityAnalysis;
  changes?: CapabilityChanges;
  rootRequested?: boolean;
  externalBinaries?: SecurityFacts["external_binaries"];
  onGamepadDirection?: (event: GamepadEvent) => void;
}) {
  const t = useT();
  const detailsId = useId();
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <section
      className="ddu-capabilities"
      aria-label={t("Detected capabilities")}
    >
      <strong className="ddu-capabilities-title">
        {t("Detected capabilities")}
      </strong>
      {!analysis && <p>{t("Analysis unavailable")}</p>}
      <>
        {Object.entries(categories).map(
          ([category, [Icon, label, explanation]]) => {
            const findings = (analysis?.findings || []).filter(
              (f) => f.category === category,
            );
            if (
              !findings.length &&
              !(category === "root" && rootRequested) &&
              !(category === "native_binaries" && externalBinaries.length)
            )
              return null;
            const filenames =
              category === "native_binaries"
                ? [
                    ...new Set([
                      ...findings
                        .filter((f) => f.origin === "binary")
                        .map((f) => f.file.split("/").at(-1)!),
                      ...externalBinaries.map((binary) => binary.name),
                    ]),
                  ]
                : [];
            const targets = [
              ...new Set(
                findings
                  .flatMap((f) => f.targets || [])
                  .map((value) =>
                    category === "devices" ? t(deviceLabel(value)) : value,
                  ),
              ),
            ]
              .sort()
              .slice(0, 16);
            const open = expanded === category;
            const toggle = () => setExpanded(open ? null : category);
            return (
              <div key={category}>
                <Focusable
                  onGamepadDirection={onGamepadDirection}
                  className="ddu-capability-row"
                  focusClassName="ddu-focused"
                  role="button"
                  tabIndex={0}
                  aria-expanded={open}
                  aria-controls={`${detailsId}-${category}`}
                  onActivate={toggle}
                  onClick={toggle}
                  onKeyDown={(event) => {
                    if (!event.repeat && ["Enter", " "].includes(event.key)) {
                      event.preventDefault();
                      toggle();
                    }
                  }}
                >
                  <Icon aria-hidden="true" /> <span>{t(label)}</span>
                  {changes?.added.includes(category) && (
                    <small>{t("Newly detected")}</small>
                  )}
                  <FaChevronRight
                    aria-hidden="true"
                    className={open ? "ddu-disclosure-open" : undefined}
                  />
                </Focusable>
                {open && (
                  <div
                    id={`${detailsId}-${category}`}
                    className="ddu-capability-explanation"
                  >
                    <p>{t(explanation)}</p>
                    {targets.length > 0 && (
                      <ul className="ddu-capability-targets">
                        {targets.map((target) => (
                          <li key={target}>{target}</li>
                        ))}
                      </ul>
                    )}
                    {targetNotes[category] && <p>{t(targetNotes[category])}</p>}
                    {filenames.length > 0 && (
                      <ul>
                        {filenames.map((name) => (
                          <li key={name}>{name}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            );
          },
        )}
        {analysis &&
          !analysis.findings.length &&
          !rootRequested &&
          !externalBinaries.length && <p>{t("No capabilities identified")}</p>}
        {changes?.status === "unknown" && (
          <p>{t("Previous capabilities unknown")}</p>
        )}
        {analysis && (
          <p className="ddu-capabilities-note">
            {t(
              analysis.complete
                ? "Analysis of plugin files. It does not limit the plugin's access."
                : "Partial analysis of plugin files. It does not limit the plugin's access.",
            )}
          </p>
        )}
      </>
    </section>
  );
}
