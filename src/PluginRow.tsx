import { Focusable, Spinner } from "@decky/ui";
import {
  FaCheck,
  FaClock,
  FaDownload,
  FaExclamationTriangle,
  FaMinus,
  FaQuestion,
} from "react-icons/fa";
import { NavigationGroup } from "./NavigationGroup";
import { pluginActions, pluginStatus, type InstalledPlugin } from "./uiModel";

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
  busy,
  updating,
  onUpdate,
  registerUpdate,
  onUpdateFocus,
  onOpen,
  onFocus,
  register,
}: {
  plugin: InstalledPlugin;
  busy: boolean;
  updating: boolean;
  onUpdate: () => void;
  onUpdateFocus: () => void;
  registerUpdate: (element: HTMLDivElement | null) => void;
  onOpen: () => void;
  onFocus: () => void;
  register: (element: HTMLDivElement | null) => void;
}) {
  const status = pluginStatus(plugin);
  const Icon = icons[status.icon];
  const canUpdate = pluginActions(plugin).update;
  return (
    <NavigationGroup className="ddu-plugin-row" flow-children="row">
      <Focusable
        ref={register}
        role="button"
        tabIndex={0}
        className="ddu-row ddu-plugin-details"
        focusClassName="ddu-focused"
        onActivate={onOpen}
        onClick={onOpen}
        onFocus={onFocus}
        onGamepadFocus={onFocus}
        onOKActionDescription="Details"
        aria-label={`${plugin.name}. ${status.subtitle}. Details`}
      >
        <span className="ddu-row-text">
          <span className="ddu-name">{plugin.name}</span>
          <span className="ddu-subtitle">{status.subtitle}</span>
        </span>
        {!canUpdate && <Icon className="ddu-status-icon" aria-hidden="true" />}
      </Focusable>
      {canUpdate && (
        <Focusable
          ref={registerUpdate}
          role="button"
          tabIndex={0}
          className="ddu-quick-update"
          focusClassName="ddu-focused"
          aria-label={`Update ${plugin.name}`}
          aria-disabled={busy}
          aria-busy={updating}
          onFocus={onUpdateFocus}
          onGamepadFocus={onUpdateFocus}
          onActivate={() => {
            if (!busy) onUpdate();
          }}
          onClick={() => {
            if (!busy) onUpdate();
          }}
          onOKActionDescription="Update"
        >
          {updating ? (
            <Spinner style={{ width: 18, height: 18 }} />
          ) : (
            <FaDownload aria-hidden="true" />
          )}
        </Focusable>
      )}
    </NavigationGroup>
  );
}
