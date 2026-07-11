"use client";

import { MapPin, Network, Shield, AlertTriangle, Activity, Settings } from "./Icons";

export type TabKey = "map" | "modules" | "fraud-rings" | "alerts" | "analytics";

const RAIL_ITEMS: { key: TabKey; icon: typeof MapPin; label: string }[] = [
  { key: "map", icon: MapPin, label: "Live Map" },
  { key: "modules", icon: Shield, label: "Modules" },
  { key: "fraud-rings", icon: Network, label: "Fraud Rings" },
  { key: "alerts", icon: AlertTriangle, label: "Alerts" },
  { key: "analytics", icon: Activity, label: "Analytics" },
];

export default function IconRail({
  activeTab,
  onTabChange,
  drawerOpen,
  onSettings,
}: {
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
  drawerOpen: boolean;
  onSettings?: () => void;
}) {
  return (
    <aside className="glass-rail pointer-events-auto absolute left-0 top-14 bottom-0 z-30 flex w-[52px] flex-col items-center gap-1 pt-4 pb-3">
      {RAIL_ITEMS.map(({ key, icon: Icon, label }) => (
        <button
          key={key}
          onClick={() => onTabChange(key)}
          title={label}
          className={`flex h-10 w-10 items-center justify-center rounded-xl transition
            ${
              activeTab === key && (drawerOpen || key === "map")
                ? "bg-violet-500/20 text-violet-300"
                : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
            }`}
        >
          <Icon className="h-5 w-5" />
        </button>
      ))}
      <div className="mt-auto">
        <button
          onClick={onSettings}
          title="Settings"
          className="flex h-10 w-10 items-center justify-center rounded-xl text-zinc-600 transition hover:bg-white/5 hover:text-zinc-400"
        >
          <Settings className="h-5 w-5" />
        </button>
      </div>
    </aside>
  );
}
