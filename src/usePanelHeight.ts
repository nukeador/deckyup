import { useLayoutEffect, type RefObject } from "react";

export function usePanelHeight(root: RefObject<HTMLDivElement | null>) {
  useLayoutEffect(() => {
    const element = root.current;
    if (!element) return;
    let viewport = element.parentElement;
    while (
      viewport &&
      !["auto", "scroll"].includes(getComputedStyle(viewport).overflowY)
    ) {
      viewport = viewport.parentElement;
    }
    const update = () => {
      const bottom =
        viewport?.getBoundingClientRect().bottom || window.innerHeight;
      const height = Math.max(
        144,
        bottom - element.getBoundingClientRect().top - 8,
      );
      element.style.setProperty("--ddu-height", `${height}px`);
    };
    update();
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    if (viewport) observer?.observe(viewport);
    window.addEventListener("resize", update);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [root]);
}
