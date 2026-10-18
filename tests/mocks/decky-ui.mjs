import {
  createElement,
  forwardRef,
  useImperativeHandle,
  useRef,
  useEffect,
} from "react";

// Adapt Decky's gamepad events to the DOM; review handlers and markup stay real.
export const Focusable = forwardRef(function Focusable(
  {
    onActivate,
    onCancelButton,
    onGamepadDirection,
    focusable,
    focusClassName,
    onCancelActionDescription,
    children,
    ...props
  },
  ref,
) {
  const local = useRef(null);
  useImperativeHandle(ref, () => local.current);
  useEffect(() => {
    const element = local.current;
    const activate = (event) => onActivate?.(event);
    const cancel = (event) => onCancelButton?.(event);
    const direction = (event) => onGamepadDirection?.(event);
    element.addEventListener("decky-activate", activate);
    element.addEventListener("decky-cancel", cancel);
    element.addEventListener("decky-direction", direction);
    return () => {
      element.removeEventListener("decky-activate", activate);
      element.removeEventListener("decky-cancel", cancel);
      element.removeEventListener("decky-direction", direction);
    };
  }, [onActivate, onCancelButton, onGamepadDirection]);
  return createElement("div", { ...props, ref: local }, children);
});
export function DialogButton({ onGamepadDirection, ...props }) {
  const ref = useRef(null);
  useEffect(() => {
    const element = ref.current;
    const activate = () => {
      if (!element.disabled) element.click();
    };
    const direction = (event) => {
      onGamepadDirection?.(event);
      if (onGamepadDirection) event.stopPropagation();
    };
    element.addEventListener("decky-activate", activate);
    element.addEventListener("decky-direction", direction);
    return () => {
      element.removeEventListener("decky-activate", activate);
      element.removeEventListener("decky-direction", direction);
    };
  }, [onGamepadDirection]);
  return createElement("button", { ...props, ref });
}

export function Spinner() {
  return null;
}
export function TextField(props) {
  return createElement("input", props);
}
export const Navigation = {};

export const GamepadButton = {
  DIR_UP: 9,
  DIR_DOWN: 10,
  DIR_LEFT: 11,
  DIR_RIGHT: 12,
};

export function DialogCheckbox({
  checked,
  onChange,
  label,
  controlled,
  className,
  onGamepadDirection,
}) {
  return createElement(
    Focusable,
    {
      role: "checkbox",
      "aria-checked": checked,
      "aria-label": label,
      tabIndex: 0,
      className,
      onGamepadDirection,
      onActivate: () => onChange(!checked),
      onClick: () => onChange(!checked),
      onKeyDown: (event) => {
        if (!event.repeat && (event.key === " " || event.key === "Enter")) {
          event.preventDefault();
          onChange(!checked);
        }
      },
    },
    label,
  );
}
