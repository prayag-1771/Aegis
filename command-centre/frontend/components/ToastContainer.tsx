"use client";

import { X } from "./Icons";

export type Toast = { id: string; msg: string; type: "error" | "success" };

export default function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none absolute bottom-20 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`glass pointer-events-auto flex items-center gap-3 px-4 py-3 text-[12px] animate-slide-up ${
            t.type === "error"
              ? "!border-red-500/30 text-red-200"
              : "!border-emerald-500/30 text-emerald-200"
          }`}
        >
          <span className="flex-1">{t.msg}</span>
          <button
            onClick={() => onDismiss(t.id)}
            className="shrink-0 text-zinc-500 transition hover:text-zinc-200"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
