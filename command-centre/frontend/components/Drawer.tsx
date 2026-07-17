"use client";

import { useEffect, useRef } from "react";
import { playPanelExit, usePanelEntrance } from "@/lib/gsap";

export default function Drawer({
  children,
  onClose,
  scopeRef,
}: {
  children: React.ReactNode;
  onClose: () => void;
  /** Lets the parent tween this drawer out before unmounting it. The drawer
   *  sits below the top nav, so switching tabs is a real close path — and the
   *  parent owns that decision, not this shell. */
  scopeRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const own = useRef<HTMLDivElement>(null);
  const scope = scopeRef ?? own;
  // Replaces the CSS `animate-slide-in`, which drove translateX(-100%) on this
  // blur(20px) surface right across the live map — a full re-blur every frame.
  // Anchored left so it still reads as opening from the rail.
  usePanelEntrance(scope, ".gsap-panel");
  // Closing has to defer the unmount, or React removes the drawer before the
  // tween can run and the exit is a hard cut.
  const close = () => playPanelExit(scope, onClose);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div ref={scope}>
      {/* click-away backdrop */}
      <div className="absolute inset-0 z-20" onClick={close} />
      {/* drawer panel */}
      <aside
        className="gsap-panel glass-drawer pointer-events-auto absolute left-[52px] top-14 bottom-0 z-30 w-[22rem] origin-left overflow-y-auto scroll-thin"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </aside>
    </div>
  );
}
