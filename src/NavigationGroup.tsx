import { Focusable, type FocusableProps } from "@decky/ui";
import { forwardRef, type ComponentType, type RefAttributes } from "react";

// Steam's Focusable supports focusable:false for navigation-only containers;
// @decky/ui 4.13 omits that prop from its declaration.
const NativeGroup = Focusable as ComponentType<
  FocusableProps & RefAttributes<HTMLDivElement> & { focusable: boolean }
>;
export const NavigationGroup = forwardRef<HTMLDivElement, FocusableProps>(
  function NavigationGroup(props, ref) {
    return <NativeGroup {...props} ref={ref} focusable={false} />;
  },
);
