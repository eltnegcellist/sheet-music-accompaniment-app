import { useEffect, useRef, useState } from "react";

/** Keep pointer-driven controls reachable by keyboard and accessibility tools. */
export function useAutoHideControls(enabled = true) {
  const [headerVisible, setHeaderVisible] = useState(true);
  const [footerVisible, setFooterVisible] = useState(false);
  const [controlsPinned, setControlsPinned] = useState(false);
  const hideTimers = useRef<{ h?: number; f?: number }>({});

  useEffect(() => {
    if (!enabled) return;
    const focusedWithin = (selector: string) =>
      document.activeElement?.closest(selector) != null;
    const onMove = (event: MouseEvent) => {
      window.clearTimeout(hideTimers.current.h);
      window.clearTimeout(hideTimers.current.f);
      if (event.clientY < 110) {
        setHeaderVisible(true);
      } else {
        hideTimers.current.h = window.setTimeout(() => {
          if (!focusedWithin(".topbar")) setHeaderVisible(false);
        }, 1200);
      }
      if (event.clientY > window.innerHeight - 140) {
        setFooterVisible(true);
      } else {
        hideTimers.current.f = window.setTimeout(() => {
          if (!focusedWithin(".transport")) setFooterVisible(false);
        }, 1500);
      }
    };
    const onFocus = (event: FocusEvent) => {
      if (!(event.target instanceof Element)) return;
      if (event.target.closest(".topbar")) {
        window.clearTimeout(hideTimers.current.h);
        setHeaderVisible(true);
      }
      if (event.target.closest(".transport")) {
        window.clearTimeout(hideTimers.current.f);
        setFooterVisible(true);
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("focusin", onFocus);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("focusin", onFocus);
      Object.values(hideTimers.current).forEach(window.clearTimeout);
    };
  }, [enabled]);

  return {
    headerVisible: controlsPinned || headerVisible,
    footerVisible: controlsPinned || footerVisible,
    controlsPinned,
    toggleControlsPinned: () => setControlsPinned((pinned) => !pinned),
  };
}
