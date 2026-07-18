"use client";

import { useRef } from "react";
import { gsap, useGSAP, prefersReducedMotion } from "@/lib/gsap";

/**
 * Radar "sonar sweep" that plays when the owl logo hard-resets the map.
 *
 * Concentric violet/cyan rings burst from the viewport centre over a faint scan
 * grid while the camera flies out to the India overview. Purely decorative:
 * pointer-events-none, sits above the map (z-45) and below the top nav (z-50),
 * so it never intercepts clicks. One-shot per `signal` bump; `signal === 0` is
 * the initial mount and plays nothing.
 */
export default function RecenterFX({ signal }: { signal: number }) {
  const scope = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      if (!signal || prefersReducedMotion()) return;
      const root = scope.current;
      if (!root) return;

      const rings = gsap.utils.toArray<HTMLElement>(".recenter-ring", root);
      const grid = root.querySelector(".recenter-grid");
      const owl = root.querySelector(".recenter-owl");

      // GSAP owns the transform (self-centering + scale) so it never fights a
      // CSS translate on the same element.
      gsap.set(rings, { xPercent: -50, yPercent: -50, scale: 0, opacity: 0.9 });
      if (owl) gsap.set(owl, { xPercent: -50, yPercent: -50, scale: 0.5, opacity: 0.85 });

      const tl = gsap.timeline();
      tl.to(
        rings,
        {
          scale: 2.6,
          opacity: 0,
          duration: 1.5,
          ease: "power2.out",
          stagger: 0.16,
        },
        0,
      );
      // The owl blooms out of the centre and fades with the rings.
      if (owl) {
        tl.to(owl, { scale: 2.4, opacity: 0, duration: 1.3, ease: "power2.out" }, 0);
      }
      if (grid) {
        tl.fromTo(
          grid,
          { opacity: 0 },
          { opacity: 0.28, duration: 0.22, ease: "power1.out" },
          0,
        ).to(grid, { opacity: 0, duration: 1.0, ease: "power2.in" }, 0.4);
      }
    },
    { scope, dependencies: [signal] },
  );

  const ringBase =
    "recenter-ring absolute left-1/2 top-1/2 h-[42vmin] w-[42vmin] rounded-full opacity-0";

  return (
    <div
      ref={scope}
      aria-hidden
      className="pointer-events-none absolute inset-0 z-[45] overflow-hidden"
    >
      {/* faint scan grid, radially masked so it fades toward the edges */}
      <div
        className="recenter-grid absolute inset-0 opacity-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(167,139,250,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(167,139,250,0.5) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(circle at center, black 0%, transparent 68%)",
          WebkitMaskImage: "radial-gradient(circle at center, black 0%, transparent 68%)",
        }}
      />
      {/* concentric sonar rings, all centred and scaled outward by GSAP */}
      <span
        className={`${ringBase} border-2`}
        style={{
          borderColor: "#a78bfa",
          boxShadow:
            "0 0 60px 6px rgba(167,139,250,0.55), inset 0 0 40px rgba(167,139,250,0.35)",
        }}
      />
      <span
        className={`${ringBase} border`}
        style={{ borderColor: "#22d3ee", boxShadow: "0 0 40px 4px rgba(34,211,238,0.4)" }}
      />
      <span className={`${ringBase} border`} style={{ borderColor: "rgba(167,139,250,0.6)" }} />
      {/* the owl blooms out of the radar centre and fades */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo-mark.png"
        alt=""
        className="recenter-owl absolute left-1/2 top-1/2 h-[22vmin] w-[22vmin] object-contain opacity-0"
        style={{ filter: "drop-shadow(0 0 26px rgba(167,139,250,0.75))" }}
      />
    </div>
  );
}
