const TEETH = Array.from({ length: 12 }, (_, i) => i * 30);

/**
 * Krish AI's mark: a Sudarshan chakra drawn from the EmpireX blade. Used as the app icon and the
 * agent's avatar. It turns a little on hover and spins while Krish is writing (`thinking`).
 */
export default function BrandMark({ className = "", thinking = false }) {
  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className={`krish-chakra select-none ${thinking ? "is-thinking" : ""} ${className}`}
      data-testid="brand-mark"
    >
      <g className="krish-chakra-blade" fill="currentColor">
        {TEETH.map((a) => (
          <path key={a} d="M45 20C47 11 53 6 61 5C58 9 56.5 14 56 20Z" transform={`rotate(${a} 50 50)`} />
        ))}
        <circle cx="50" cy="50" r="31" fill="none" stroke="currentColor" strokeWidth="6" />
        <circle cx="50" cy="50" r="22" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="3 5.2" opacity="0.55" />
      </g>
      <circle className="krish-chakra-hub" cx="50" cy="50" r="10" fill="#FF8A1E" />
    </svg>
  );
}
