"use client";

import { useState, useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { HealthResponse } from "@/lib/api";
import type { TabKey } from "./types";
import { Bell, Search, Shield, Wifi, X } from "./Icons";
import Clock from "./Clock";

const TABS: { key: TabKey; label: string }[] = [
  { key: "map", label: "Live Map" },
  { key: "modules", label: "Modules" },
  { key: "fraud-rings", label: "Fraud Rings" },
  { key: "alerts", label: "Alerts & Analytics" },
];

export default function TopNav({
  health,
  alertCount,
  activeTab,
  onTabChange,
  onBell,
  onSearch,
}: {
  health: HealthResponse | null;
  alertCount: number;
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
  onBell?: () => void;
  onSearch?: (query: string) => void;
}) {
  const backendUp = health?.status === "ok";
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const container = useRef<HTMLElement>(null);

  useGSAP(() => {
    gsap.from(container.current, {
      y: -50,
      opacity: 0,
      duration: 0.8,
      ease: "power3.out",
    });
    
    gsap.from(".gsap-nav-item", {
      y: -20,
      opacity: 0,
      duration: 0.5,
      stagger: 0.05,
      ease: "back.out(1.5)",
      delay: 0.2
    });
  }, { scope: container });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim() && onSearch) {
      onSearch(searchQuery.trim());
    }
  };

  return (
    <header ref={container} className="pointer-events-auto absolute inset-x-0 top-0 z-40 flex items-center gap-5 px-5 py-3">
      {/* Animated Shield Logo */}
      <div className="glass flex h-10 w-10 items-center justify-center !rounded-xl transition-transform duration-500 hover:rotate-12 hover:scale-110 shadow-[0_0_15px_rgba(139,92,246,0.3)]">
        <Shield className="h-5 w-5 text-zinc-100 animate-pulse" />
      </div>

      <nav className="flex items-center gap-1">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => onTabChange(key)}
            className={`gsap-nav-item ${
              activeTab === key
                ? "rounded-full bg-zinc-100 px-4 py-1.5 text-sm font-medium text-zinc-900 shadow"
                : "rounded-full px-4 py-1.5 text-sm text-zinc-400 transition hover:text-zinc-100"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-4">
        {/* Search */}
        <div className="relative flex items-center gsap-nav-item">
          {searchOpen ? (
            <form onSubmit={handleSearch} className="flex items-center bg-zinc-900/80 backdrop-blur-md rounded-full border border-zinc-800 pl-3 pr-1 py-1 w-48 transition-all">
              <button type="submit" className="hover:text-zinc-300">
                <Search className="h-3.5 w-3.5 text-zinc-400 mr-2" />
              </button>
              <input
                autoFocus
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search city..."
                className="bg-transparent border-none outline-none text-sm text-zinc-100 w-full placeholder-zinc-500"
              />
              <button type="button" onClick={() => setSearchOpen(false)} className="p-1 hover:text-zinc-300 text-zinc-500">
                <X className="h-3 w-3" />
              </button>
            </form>
          ) : (
            <button onClick={() => setSearchOpen(true)} className="flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300 transition px-2 py-1">
              <Search className="h-3.5 w-3.5" />
              <span>Search</span>
            </button>
          )}
        </div>

        {/* Backend Status */}
        <span className="gsap-nav-item" title={backendUp ? "backend online" : "backend unreachable"}>
          <Wifi className={`h-4 w-4 ${backendUp ? "text-emerald-400" : "text-red-400"}`} />
        </span>

        {/* Alerts Bell */}
        <button
          onClick={onBell}
          title="View alerts"
          className="relative transition hover:text-zinc-100 gsap-nav-item"
        >
          <Bell className="h-4 w-4 text-zinc-300" />
          {alertCount > 0 && (
            <span className="absolute -right-2 -top-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">
              {alertCount}
            </span>
          )}
        </button>

        {/* Clock instead of PM icon */}
        <div className="gsap-nav-item">
          <Clock />
        </div>
      </div>
    </header>
  );
}
