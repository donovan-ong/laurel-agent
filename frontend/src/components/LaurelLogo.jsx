export default function LaurelLogo({ size = 28, className }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="Laurel"
      className={className}
      // Inline SVGs default to vertical-align: baseline, which reserves a few px of descender space below
      // them — that's what was throwing off vertical centring next to text in flex rows (the nav bar, the
      // login title). display: block removes that gap so align-items: center actually centres it.
      style={{ display: "block" }}
    >
      {/* A plain speech bubble, white on a red disc — the same mark the floating chat widget uses
          (widget/src/icons.jsx's ChatIcon), so the brand mark matches between the two surfaces. */}
      <circle cx="16" cy="16" r="16" fill="var(--accent, #e4002b)" />
      <g transform="translate(7,7) scale(0.75)">
        <path
          fill="#fff"
          d="M6 3h12a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-7.2L5.6 21.2A.6.6 0 0 1 4.6 20.7V17.9A3 3 0 0 1 3 15.2V6a3 3 0 0 1 3-3z"
        />
      </g>
    </svg>
  );
}
