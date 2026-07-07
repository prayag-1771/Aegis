/** Tiny inline icon set (lucide-style paths) — zero dependencies, tree-shaken by usage. */

function I({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ?? "h-4 w-4"}
      aria-hidden
    >
      {children}
    </svg>
  );
}

export const Shield = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M12 22s8-3 8-10V5l-8-3-8 3v7c0 7 8 10 8 10z" />
  </I>
);

export const Phone = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.08 4.18 2 2 0 0 1 4.06 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />
  </I>
);

export const Banknote = ({ className }: { className?: string }) => (
  <I className={className}>
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <circle cx="12" cy="12" r="2" />
    <path d="M6 12h.01M18 12h.01" />
  </I>
);

export const Network = ({ className }: { className?: string }) => (
  <I className={className}>
    <circle cx="18" cy="5" r="3" />
    <circle cx="6" cy="12" r="3" />
    <circle cx="18" cy="19" r="3" />
    <path d="m8.59 13.51 6.83 3.98M15.41 6.51l-6.82 3.98" />
  </I>
);

export const MapPin = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
    <circle cx="12" cy="10" r="3" />
  </I>
);

export const AlertTriangle = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
    <path d="M12 9v4M12 17h.01" />
  </I>
);

export const CheckCircle = ({ className }: { className?: string }) => (
  <I className={className}>
    <circle cx="12" cy="12" r="10" />
    <path d="m9 12 2 2 4-4" />
  </I>
);

export const Bell = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
    <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </I>
);

export const Search = ({ className }: { className?: string }) => (
  <I className={className}>
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </I>
);

export const Zap = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
  </I>
);

export const Activity = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
  </I>
);

export const ArrowUpRight = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M7 7h10v10M7 17 17 7" />
  </I>
);

export const Layers = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.84Z" />
    <path d="m22 12.18-9.17 4.16a2 2 0 0 1-1.66 0L2 12.18" />
    <path d="m22 17.18-9.17 4.16a2 2 0 0 1-1.66 0L2 17.18" />
  </I>
);

export const Wifi = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M12 20h.01" />
    <path d="M2 8.82a15 15 0 0 1 20 0" />
    <path d="M5 12.86a10 10 0 0 1 14 0" />
    <path d="M8.5 16.43a5 5 0 0 1 7 0" />
  </I>
);
