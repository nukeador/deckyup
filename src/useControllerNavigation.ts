import { GamepadButton, type GamepadEvent } from "@decky/ui";
import type { KeyboardEvent, RefObject } from "react";

/** These long detail views need control order, rather than spatial group entry. */
export function useControllerNavigation(root: RefObject<HTMLElement | null>) {
  function move(direction: -1 | 1, horizontal = false): boolean {
    const container = root.current;
    // Decky renders QAM portals in a different document from the plugin module.
    const current = container?.ownerDocument.activeElement;
    if (!container || !current || !container.contains(current)) return false;
    const scope = horizontal
      ? current.closest<HTMLElement>("[data-controller-row]")
      : container;
    if (!scope || !container.contains(scope)) return false;
    // Steam uses roving tabindex: inactive gamepad controls can have tabindex=-1.
    // That excludes keyboard Tab entry, not controller navigation.
    const controls = [
      ...scope.querySelectorAll<HTMLElement>(
        'button,[role="button"][tabindex],[role="checkbox"],[data-controller-content][tabindex],input,select,textarea',
      ),
    ].filter(
      (element) =>
        !element.matches(':disabled,.Disabled,[aria-disabled="true"]') &&
        !element.closest('[hidden],[inert],[aria-hidden="true"]'),
    );
    const index = controls.findIndex(
      (element) => element === current || element.contains(current),
    );
    const next =
      index < 0
        ? 0
        : Math.max(0, Math.min(controls.length - 1, index + direction));
    const target = controls[next];
    if (!target) return false;
    target.focus({ preventScroll: true });
    target.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    return true;
  }
  return {
    onGamepadDirection(event: GamepadEvent) {
      const button = event.detail.button;
      const horizontal =
        button === GamepadButton.DIR_LEFT || button === GamepadButton.DIR_RIGHT;
      if (
        !horizontal &&
        button !== GamepadButton.DIR_DOWN &&
        button !== GamepadButton.DIR_UP
      )
        return;
      if (
        move(
          button === GamepadButton.DIR_DOWN ||
            button === GamepadButton.DIR_RIGHT
            ? 1
            : -1,
          horizontal,
        )
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    },
    onKeyDown(event: KeyboardEvent<HTMLElement>) {
      if ((event.target as HTMLElement).matches("input,textarea,select"))
        return;
      const horizontal =
        event.key === "ArrowLeft" || event.key === "ArrowRight";
      if (!horizontal && event.key !== "ArrowDown" && event.key !== "ArrowUp")
        return;
      if (
        move(
          event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : -1,
          horizontal,
        )
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    },
  };
}
