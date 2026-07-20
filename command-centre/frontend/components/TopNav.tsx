"use client";

import { useState, useRef, useEffect, Fragment } from "react";
import { gsap, useGSAP, prefersReducedMotion } from "@/lib/gsap";
import type { HealthResponse } from "@/lib/api";
import type { TabKey } from "./types";
import { Bell, Search, Wifi, X, ChevronLeft, ChevronRight } from "./Icons";
import Clock from "./Clock";

const TABS: { key: TabKey; label: string }[] = [
  { key: "map", label: "Live Map" },
  { key: "modules", label: "Modules" },
  { key: "fraud-rings", label: "Fraud Rings" },
  { key: "alerts", label: "Alerts & Analytics" },
  { key: "disrupt", label: "Disrupt" },
  { key: "metrics", label: "Metrics" },
  { key: "research", label: "Research Lab" },
];

export default function TopNav({
  health,
  alertCount,
  activeTab,
  onTabChange,
  onBell,
  onSearch,
  onSearchClear,
  onLogoClick,
  isRightPanelOpen,
  hideArrows,
}: {
  health: HealthResponse | null;
  alertCount: number;
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
  onBell?: () => void;
  onSearch?: (query: string) => void;
  onSearchClear?: () => void;
  /** Hard-reset the map to the India overview (owl-logo click). */
  onLogoClick?: () => void;
  isRightPanelOpen?: boolean;
  hideArrows?: boolean;
}) {
  const backendUp = health?.status === "ok";
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [hasSearched, setHasSearched] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (searchOpen) inputRef.current?.focus();
  }, [searchOpen]);

  useEffect(() => {
    if (!localStorage.getItem("aegis_has_searched")) {
      setHasSearched(false);
    }
  }, []);

  // Global Ctrl+K shortcut to open search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const container = useRef<HTMLElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const pillRef = useRef<HTMLSpanElement>(null);
  const logoRef = useRef<HTMLImageElement>(null);

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

  // Sizes are viewport-relative (clamp), so tab widths change on resize —
  // snap the pill back under the active tab or it drifts off-target.
  useEffect(() => {
    const measure = () => {
      const nav = navRef.current;
      const pill = pillRef.current;
      if (!nav || !pill) return;
      const active = nav.querySelector<HTMLElement>(`[data-tab="${activeTab}"]`);
      if (!active) return;
      const navBox = nav.getBoundingClientRect();
      const btnBox = active.getBoundingClientRect();
      gsap.set(pill, { x: btnBox.left - navBox.left, width: btnBox.width });
    };
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [activeTab]);

  const handlePrevTab = () => {
    const currentIndex = TABS.findIndex((t) => t.key === activeTab);
    const prevIndex = currentIndex > 0 ? currentIndex - 1 : TABS.length - 1;
    onTabChange(TABS[prevIndex].key);
  };

  const handleNextTab = () => {
    const currentIndex = TABS.findIndex((t) => t.key === activeTab);
    const nextIndex = currentIndex < TABS.length - 1 ? currentIndex + 1 : 0;
    onTabChange(TABS[nextIndex].key);
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (document.activeElement?.tagName === "INPUT") return;
      
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        e.stopPropagation();
        handlePrevTab();
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        e.stopPropagation();
        handleNextTab();
      }
    };
    // Use capture phase so we intercept the event BEFORE Mapbox processes it
    window.addEventListener("keydown", handleKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", handleKeyDown, { capture: true });
  }, [activeTab, onTabChange]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim() && onSearch) {
      onSearch(searchQuery.trim());
      localStorage.setItem("aegis_has_searched", "true");
      setHasSearched(true);
    }
  };

  // Spin the owl once for tactile feedback, then fire the map hard-reset.
  const handleLogoClick = () => {
    if (logoRef.current && !prefersReducedMotion()) {
      gsap.to(logoRef.current, { rotate: "+=360", duration: 0.6, ease: "power2.out" });
    }
    // A hard reset also restores the "search any place" hint callout.
    localStorage.removeItem("aegis_has_searched");
    setHasSearched(false);
    onLogoClick?.();
  };

  return (
    <>
      <header ref={container} className="pointer-events-none absolute inset-x-0 top-0 z-50 flex items-center gap-[clamp(0.5rem,1.4vw,1.25rem)] px-[clamp(0.6rem,1.4vw,1.25rem)] py-3">
      {/* Aegis owl logo — click to hard-reset the map to the India overview */}
      <button
        type="button"
        onClick={handleLogoClick}
        aria-label="Reset map to India view"
        title="Reset to India view"
        className="pointer-events-auto glass flex h-[clamp(2.5rem,3.4vw,3rem)] w-[clamp(2.5rem,3.4vw,3rem)] shrink-0 cursor-pointer items-center justify-center !rounded-xl shadow-[0_0_22px_rgba(139,92,246,0.55)] focus-visible:outline-none"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img ref={logoRef} src="/logo-owl-shield.png" alt="Aegis" className="h-full w-full rounded-[10px] object-cover" />
      </button>

      <nav
        ref={navRef as React.RefObject<HTMLElement>}
        className="pointer-events-auto glass gsap-nav-item relative flex items-center gap-1 !rounded-full !border-white/6 p-1"
      >
        {/* single pill that slides between tabs, positioned via GSAP above */}
        <span
          ref={pillRef}
          className="pointer-events-none absolute left-0 top-1 bottom-1 z-10 rounded-full bg-white shadow-lg"
          style={{ width: 0, backgroundColor: "#ffffff" }}
        />
        {TABS.map(({ key, label }) => {
          const isActive = activeTab === key;
          return (
            <Fragment key={key}>
              {isActive && (
                <button
                  onClick={handlePrevTab}
                  className="relative z-20 rounded-full p-1 text-white hover:bg-zinc-800/50 hover:text-white transition-colors focus-visible:outline-none"
                  title="Previous tab"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
              )}
              
              <button
                data-tab={key}
                onClick={() => onTabChange(key)}
                aria-current={isActive ? "page" : undefined}
                className={`relative z-20 focus-visible:outline-none whitespace-nowrap rounded-full px-[clamp(0.55rem,1.05vw,1rem)] py-1.5 text-[clamp(0.72rem,0.92vw,0.875rem)] transition-colors duration-200 ${
                  isActive
                    ? "font-medium text-zinc-900"
                    : "font-normal text-zinc-400 hover:text-zinc-100"
                }`}
              >
                {label}
              </button>

              {isActive && (
                <button
                  onClick={handleNextTab}
                  className="relative z-20 rounded-full p-1 text-white hover:bg-zinc-800/50 hover:text-white transition-colors focus-visible:outline-none"
                  title="Next tab"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              )}
            </Fragment>
          );
        })}
      </nav>

      <div className="pointer-events-auto ml-auto flex shrink-0 items-center gap-[clamp(0.5rem,1.1vw,1rem)]">
        {/* Search */}
        <div className="relative flex items-center gsap-nav-item">
          <div className={`grid items-center transition-[width] duration-300 ease-out overflow-hidden ${searchOpen ? "w-[clamp(10rem,16vw,12rem)]" : "w-[clamp(2.25rem,9vw,8.25rem)]"}`}>
            
            {/* Open Form State */}
            <form 
              onSubmit={handleSearch} 
              className={`col-start-1 row-start-1 glass !rounded-full flex items-center pl-3 pr-1 py-1 w-[clamp(10rem,16vw,12rem)] transition-all duration-300 ${
                searchOpen ? "opacity-100 scale-100" : "opacity-0 scale-95 pointer-events-none"
              }`}
            >
              <button type="submit" className="text-zinc-400 transition-colors hover:text-zinc-200 shrink-0">
                <Search className="h-3.5 w-3.5 mr-2" />
              </button>
              <input
                ref={inputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setSearchOpen(false);
                    setSearchQuery("");
                    onSearchClear?.();
                  }
                }}
                onBlur={(e) => {
                  if (!e.currentTarget.form?.contains(e.relatedTarget as Node)) {
                    if (!searchQuery.trim()) {
                      setSearchOpen(false);
                    }
                  }
                }}
                placeholder="Search city..."
                className="bg-transparent border-none outline-none text-sm text-zinc-100 w-full placeholder-zinc-500"
              />
              <button
                type="button"
                onClick={() => {
                  setSearchOpen(false);
                  setSearchQuery("");
                  onSearchClear?.();
                }}
                className="p-1 text-zinc-500 transition-colors hover:text-zinc-200 shrink-0"
              >
                <X className="h-3 w-3" />
              </button>
            </form>

            <button
              onClick={() => setSearchOpen(true)}
              className={`col-start-1 row-start-1 flex items-center gap-2 rounded-full px-2 py-1 w-auto min-w-0 text-xs text-zinc-500 transition-all duration-300 hover:text-zinc-100 ${
                searchOpen ? "opacity-0 scale-105 pointer-events-none" : "opacity-100 scale-100"
              }`}
            >
              <Search className="h-3.5 w-3.5 shrink-0" />
              <span className="hidden lg:inline">Search</span>
              <kbd className="ml-1.5 hidden xl:inline-flex h-3.5 items-center justify-center rounded border border-zinc-700/60 bg-zinc-800/40 px-1.5 font-sans text-[8px] font-medium text-zinc-500 shrink-0 whitespace-nowrap">
                Ctrl K
              </kbd>
            </button>
          </div>

          {/* Callout Dialogue Box */}
              {/* First-run hint, anchored BELOW the search box. It used to sit
                  `right-full` (to the left), which floated it straight over the
                  tab row; the `2xl:block` gate bought space back for a while,
                  but the rail has since grown to seven tabs and it collided
                  again — and the hint was invisible under 1536px meanwhile.
                  Dropping down clears the rail at every width instead of
                  betting on a breakpoint.

                  The `hidden 2xl:block` gate is gone for that reason: 1536px is
                  wider than most laptops (1366-1512), so on the deployed site
                  the hint simply never rendered for anyone. */}
              {!hasSearched && (
                <div className="absolute right-0 top-full mt-3 w-44 max-w-[calc(100vw-2rem)] p-2.5 text-[11px] leading-relaxed text-zinc-300 bg-zinc-800/90 backdrop-blur-md border border-white/10 rounded-lg shadow-xl z-50">
                  Search any place here to view its details.
                  {/* Arrow pointing up at the search box */}
                  <div className="absolute -top-1.5 right-6 w-3 h-3 bg-zinc-800/90 border-t border-l border-white/10 transform rotate-45"></div>
                </div>
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
        <div className="gsap-nav-item tabular-nums whitespace-nowrap text-[clamp(0.72rem,0.95vw,0.875rem)]">
          <Clock />
        </div>
      </div>
    </header>

      {/* Floating Global Tab Navigation Arrows */}
      {!hideArrows && (
        <>
          <button
            onClick={handlePrevTab}
            className="pointer-events-auto fixed left-2 top-1/2 z-[100] p-1 text-white transition-all duration-300 ease-in-out hover:scale-125 focus-visible:outline-none -translate-y-1/2"
            title="Previous tab"
          >
            <ChevronLeft className="h-8 w-8 drop-shadow-md" />
          </button>

          <button
            onClick={handleNextTab}
            className={`pointer-events-auto fixed right-0 top-1/2 z-[100] p-1 text-white transition-transform duration-300 ease-in-out hover:scale-125 focus-visible:outline-none -translate-y-1/2 ${
              isRightPanelOpen ? "translate-x-0" : "-translate-x-2"
            }`}
            title="Next tab"
          >
            <ChevronRight className="h-8 w-8 drop-shadow-md" />
          </button>
        </>
      )}
    </>
  );
}
