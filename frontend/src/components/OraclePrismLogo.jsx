export default function OraclePrismLogo({ className = "h-7 w-7" }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        {/* Left Wing (Polymarket / Cyan) Gradients */}
        <linearGradient id="navCyanTop" x1="3.5" y1="2.5" x2="14.5" y2="16" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
        <linearGradient id="navCyanMid" x1="3.5" y1="8.8" x2="14.5" y2="23.2" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#06b6d4" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>
        <linearGradient id="navCyanBot" x1="3.5" y1="16" x2="14.5" y2="29.5" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0284c7" />
          <stop offset="100%" stopColor="#0c4a6e" />
        </linearGradient>

        {/* Right Wing (UMA Oracle / Emerald) Gradients */}
        <linearGradient id="navEmeraldTop" x1="28.5" y1="2.5" x2="17.5" y2="16" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#6ee7b7" />
          <stop offset="100%" stopColor="#10b981" />
        </linearGradient>
        <linearGradient id="navEmeraldMid" x1="28.5" y1="8.8" x2="17.5" y2="23.2" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#10b981" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
        <linearGradient id="navEmeraldBot" x1="28.5" y1="16" x2="17.5" y2="29.5" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#059669" />
          <stop offset="100%" stopColor="#064e3b" />
        </linearGradient>

        {/* Core Divergence Ray Gradient */}
        <linearGradient id="navCoreRay" x1="16" y1="4" x2="16" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.8" />
          <stop offset="50%" stopColor="#ffffff" stopOpacity="1" />
          <stop offset="100%" stopColor="#34d399" stopOpacity="0.8" />
        </linearGradient>
      </defs>

      {/* Left Facet (Cyan - Market Odds) */}
      <g>
        <polygon points="14.5,2.5 3.5,8.8 14.5,16" fill="url(#navCyanTop)" />
        <polygon points="3.5,8.8 3.5,23.2 14.5,16" fill="url(#navCyanMid)" />
        <polygon points="3.5,23.2 14.5,29.5 14.5,16" fill="url(#navCyanBot)" />
      </g>

      {/* Right Facet (Emerald - Oracle Truth) */}
      <g>
        <polygon points="17.5,2.5 28.5,8.8 17.5,16" fill="url(#navEmeraldTop)" />
        <polygon points="28.5,8.8 28.5,23.2 17.5,16" fill="url(#navEmeraldMid)" />
        <polygon points="28.5,23.2 17.5,29.5 17.5,16" fill="url(#navEmeraldBot)" />
      </g>

      {/* Divergence Core Beam */}
      <line x1="16" y1="4" x2="16" y2="28" stroke="url(#navCoreRay)" strokeWidth="1.2" strokeLinecap="round" />

      {/* Central Oracle Core / Verdict Node */}
      <circle cx="16" cy="16" r="2.5" fill="#ffffff" fillOpacity="0.95" />
      <circle cx="16" cy="16" r="1.2" fill="#080c14" />
    </svg>
  );
}
