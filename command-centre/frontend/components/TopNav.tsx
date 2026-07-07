"use client";

import type { HealthResponse } from "@/lib/api";
import { Bell, Search, Shield, Wifi } from "./Icons";

const TABS = ["Live Map", "Modules", "Fraud Rings", "Alerts", "Analytics", "Team"];

export default function TopNav({
  health,
  alertCount,
}: {
  health: HealthResponse | null;
  alertCount: number;
}) {
  const backendUp = health?.status === "ok";

  return (
    <header className="pointer-events-auto absolute inset-x-0 top-0 z-30 flex items-center gap-5 px-5 py-3">
      <div className="glass flex h-10 w-10 items-center justify-center !rounded-xl">
        <Shield className="h-5 w-5 text-zinc-100" />
      </div>

      <nav className="flex items-center gap-1">
        {TABS.map((t, i) => (
          <button
            key={t}
            className={
              i === 0
                ? "rounded-full bg-zinc-100 px-4 py-1.5 text-sm font-medium text-zinc-900 shadow"
                : "rounded-full px-4 py-1.5 text-sm text-zinc-400 transition hover:text-zinc-100"
            }
          >
            {t}
          </button>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-4">
        <div className="hidden items-center gap-2 text-xs text-zinc-400 md:flex">
          <Search className="h-3.5 w-3.5" />
          <span>
            Search <span className="text-zinc-500">Ctrl+K</span>
          </span>
        </div>
        <span title={backendUp ? "backend online" : "backend unreachable"}>
          <Wifi className={`h-4 w-4 ${backendUp ? "text-emerald-400" : "text-red-400"}`} />
        </span>
        <div className="relative">
          <Bell className="h-4 w-4 text-zinc-300" />
          {alertCount > 0 && (
            <span className="absolute -right-2 -top-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">
              {alertCount}
            </span>
          )}
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-[11px] font-semibold text-white">
          PM
        </div>
      </div>
    </header>
  );
}
