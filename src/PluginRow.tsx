import { Focusable } from "@decky/ui";
import {
  FaCheck,
  FaClock,
  FaDownload,
  FaExclamationTriangle,
  FaMinus,
  FaQuestion,
} from "react-icons/fa";
import { pluginStatus, type InstalledPlugin } from "./uiModel";

const icons = {
  download: FaDownload,
  check: FaCheck,
  question: FaQuestion,
  warning: FaExclamationTriangle,
  clock: FaClock,
  unavailable: FaMinus,
};
export function PluginRow({
  plugin,
  onOpen,
  onFocus,
  register,
}: {
  plugin: InstalledPlugin;
  onOpen: () => void;
  onFocus: () => void;
  register: (element: HTMLDivElement | null) => void;
}) {
  const status = pluginStatus(plugin);
  const Icon = icons[status.icon];
  return (
    <Focusable
      ref={register}
      role="button"
      tabIndex={0}
      className="ddu-row"
      focusClassName="ddu-focused"
      onActivate={onOpen}
      onClick={onOpen}
      onFocus={onFocus}
      onGamepadFocus={onFocus}
      onOKActionDescription="Details"
      aria-label={`${plugin.name}. ${status.subtitle}. ${status.label}`}
    >
      <span className="ddu-row-text">
        <span className="ddu-name">{plugin.name}</span>
        <span className="ddu-subtitle">{status.subtitle}</span>
      </span>
      <Icon className="ddu-status-icon" aria-hidden="true" />
    </Focusable>
  );
}
