export default function ThemisScalesLogo({ className = "h-6 w-6" }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        {/* Left Pan (Cyan - Market Probability) */}
        <linearGradient id="navThemisCyan" x1="1.5" y1="17" x2="8.5" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="60%" stopColor="#06b6d4" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>

        {/* Right Pan (Emerald - Oracle Resolution) */}
        <linearGradient id="navThemisEmerald" x1="23.5" y1="17" x2="30.5" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#6ee7b7" />
          <stop offset="60%" stopColor="#10b981" />
          <stop offset="100%" stopColor="#047857" />
        </linearGradient>

        {/* Pillar / Metal Gradients */}
        <linearGradient id="navPillarGold" x1="16" y1="1.5" x2="16" y2="29" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#f8fafc" />
          <stop offset="40%" stopColor="#cbd5e1" />
          <stop offset="100%" stopColor="#64748b" />
        </linearGradient>

        {/* Beam Gradient */}
        <linearGradient id="navBeamMetal" x1="4" y1="8" x2="28" y2="8" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="25%" stopColor="#e2e8f0" />
          <stop offset="75%" stopColor="#e2e8f0" />
          <stop offset="100%" stopColor="#34d399" />
        </linearGradient>
      </defs>

      {/* Central Spearhead / Greek Apex Pediment */}
      <polygon points="16,1.5 19,6.5 13,6.5" fill="url(#navPillarGold)" />

      {/* Central Pillar / Sword of Justice */}
      <line x1="16" y1="7" x2="16" y2="26.5" stroke="url(#navPillarGold)" strokeWidth="1.8" strokeLinecap="round" />

      {/* Classical Greek Pedestal Base */}
      <line x1="12.5" y1="26.5" x2="19.5" y2="26.5" stroke="#cbd5e1" strokeWidth="1.4" strokeLinecap="round" />
      <line x1="10" y1="29" x2="22" y2="29" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />

      {/* Balance Beam */}
      <line x1="4.5" y1="8" x2="27.5" y2="8" stroke="url(#navBeamMetal)" strokeWidth="1.6" strokeLinecap="round" />

      {/* Fulcrum Hub Ring */}
      <circle cx="16" cy="8" r="2.4" fill="#0b101c" stroke="#f8fafc" strokeWidth="1.2" />
      <circle cx="16" cy="8" r="0.9" fill="#38bdf8" />

      {/* Pivot Caps */}
      <circle cx="4.8" cy="8" r="1.3" fill="#38bdf8" />
      <circle cx="27.2" cy="8" r="1.3" fill="#34d399" />

      {/* ─── LEFT SCALE: CYAN (Market Odds) ─── */}
      {/* Suspension Cords */}
      <line x1="4.8" y1="9.3" x2="1.8" y2="17.2" stroke="#38bdf8" strokeWidth="0.9" strokeLinecap="round" opacity="0.9" />
      <line x1="4.8" y1="9.3" x2="8.8" y2="17.2" stroke="#38bdf8" strokeWidth="0.9" strokeLinecap="round" opacity="0.9" />
      {/* Cyan Vessel / Pan */}
      <polygon points="1.2,17.2 9.2,17.2 7.6,22 2.8,22" fill="url(#navThemisCyan)" stroke="#38bdf8" strokeWidth="0.7" />
      {/* Market Token Orb */}
      <circle cx="5.2" cy="15.2" r="1.7" fill="#22d3ee" />
      <circle cx="5.2" cy="15.2" r="0.7" fill="#ffffff" />

      {/* ─── RIGHT SCALE: EMERALD (Oracle Verdict) ─── */}
      {/* Suspension Cords */}
      <line x1="27.2" y1="9.3" x2="23.2" y2="17.2" stroke="#34d399" strokeWidth="0.9" strokeLinecap="round" opacity="0.9" />
      <line x1="27.2" y1="9.3" x2="30.2" y2="17.2" stroke="#34d399" strokeWidth="0.9" strokeLinecap="round" opacity="0.9" />
      {/* Emerald Vessel / Pan */}
      <polygon points="22.8,17.2 30.8,17.2 29.2,22 24.4,22" fill="url(#navThemisEmerald)" stroke="#34d399" strokeWidth="0.7" />
      {/* Verdict Token Orb */}
      <circle cx="26.8" cy="15.2" r="1.7" fill="#34d399" />
      <circle cx="26.8" cy="15.2" r="0.7" fill="#ffffff" />
    </svg>
  );
}
