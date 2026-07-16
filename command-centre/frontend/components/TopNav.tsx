"use client";

import { useState, useRef } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
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
  const navRef = useRef<HTMLElement>(null);
  const pillRef = useRef<HTMLSpanElement>(null);

  useGSAP(() => {
    // fromTo (not from) + clearProps: the tween ALWAYS lands on the visible
    // end-state and then GSAP strips its inline styles, so even if React 19
    // StrictMode double-invokes / reverts the effect, elements never get
    // stranded at opacity:0 (the "invisible nav" bug).
    gsap.fromTo(container.current,
      { y: -50, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.8, ease: "power3.out", clearProps: "all" },
    );

    gsap.fromTo(".gsap-nav-item",
      { y: -20, opacity: 0 },
      {
        y: 0, opacity: 1, duration: 0.5, stagger: 0.05,
        ease: "back.out(1.5)", delay: 0.2, clearProps: "all",
      },
    );
  }, { scope: container });

  // Slide the active-tab pill to the newly active button instead of it
  // teleporting — a lightweight manual FLIP: measure the target button's
  // offset/width relative to the nav, then tween the pill there.
  useGSAP(() => {
    const nav = navRef.current;
    const pill = pillRef.current;
    if (!nav || !pill) return;
    const active = nav.querySelector<HTMLElement>(`[data-tab="${activeTab}"]`);
    if (!active) return;
    const navBox = nav.getBoundingClientRect();
    const btnBox = active.getBoundingClientRect();
    const x = btnBox.left - navBox.left;
    gsap.to(pill, {
      x, width: btnBox.width, duration: 0.35, ease: "power3.out",
    });
  }, { scope: container, dependencies: [activeTab] });

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

      <nav
        ref={navRef as React.RefObject<HTMLElement>}
        className="glass gsap-nav-item relative flex items-center gap-1 !rounded-full !border-white/6 p-1"
      >
        {/* single pill that slides between tabs, positioned via GSAP above */}
        <span
          ref={pillRef}
          className="pointer-events-none absolute left-0 top-1 bottom-1 -z-10 rounded-full bg-zinc-100 shadow"
          style={{ width: 0 }}
        />
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            data-tab={key}
            onClick={() => onTabChange(key)}
            aria-current={activeTab === key ? "page" : undefined}
            className={`rounded-full px-4 py-1.5 text-sm transition-colors duration-200 ${
              activeTab === key
                ? "font-medium text-zinc-900"
                : "font-normal text-zinc-400 hover:text-zinc-100"
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
            <form onSubmit={handleSearch} className="glass !rounded-full flex items-center pl-3 pr-1 py-1 w-48 animate-fade-in">
              <button type="submit" className="text-zinc-400 transition-colors hover:text-zinc-200">
                <Search className="h-3.5 w-3.5 mr-2" />
              </button>
              <input
                autoFocus
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search city..."
                className="bg-transparent border-none outline-none text-sm text-zinc-100 w-full placeholder-zinc-500"
              />
              <button type="button" onClick={() => setSearchOpen(false)} className="p-1 text-zinc-500 transition-colors hover:text-zinc-200">
                <X className="h-3 w-3" />
              </button>
            </form>
          ) : (
            <button onClick={() => setSearchOpen(true)} className="flex items-center gap-2 rounded-full px-2 py-1 text-xs text-zinc-500 transition-colors hover:text-zinc-100">
              <Search className="h-3.5 w-3.5" />
              <span>Search</span>
            </button>
          )}
        </div>

        {/* Backend Status */}
        <span className="gsap-nav-item relative flex" title={backendUp ? "backend online" : "backend unreachable"}>
          <Wifi className={`h-4 w-4 ${backendUp ? "text-emerald-400" : "text-red-400"}`} />
          {backendUp && (
            <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
          )}
        </span>

        {/* Alerts Bell */}
        <button
          onClick={onBell}
          title="View alerts"
          className="relative rounded-full p-1 text-zinc-300 transition-colors hover:text-zinc-100 gsap-nav-item"
        >
          <Bell className="h-4 w-4" />
          {alertCount > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white shadow-[0_0_8px_rgba(239,68,68,0.6)]">
              {alertCount}
            </span>
          )}
        </button>

        {/* Clock instead of PM icon */}
        <div className="gsap-nav-item tabular-nums">
          <Clock />
        </div>
      </div>
    </header>
  );
}
