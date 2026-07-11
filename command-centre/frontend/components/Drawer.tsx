"use client";

export default function Drawer({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <>
      {/* click-away backdrop */}
      <div className="absolute inset-0 z-20" onClick={onClose} />
      {/* drawer panel */}
      <aside
        className="glass-drawer pointer-events-auto absolute left-[52px] top-14 bottom-0 z-30 w-[22rem] overflow-y-auto scroll-thin animate-slide-in"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </aside>
    </>
  );
}
