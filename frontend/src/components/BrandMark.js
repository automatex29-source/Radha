import { useId } from "react";

const TEETH = Array.from({ length: 12 }, (_, i) => i * 30);

/**
 * Krish AI's mark: a Sudarshan chakra drawn from the EmpireX blade. Used as the app icon and the
 * agent's avatar. Every few seconds it gives a quick turn on its own, it turns on hover, and it
 * spins while Krish is writing (`thinking`).
 */
export default function BrandMark({ className = "", thinking = false }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className={`krish-chakra select-none ${thinking ? "is-thinking" : ""} ${className}`}
      data-testid="brand-mark"
    >
      <defs>
        <linearGradient id={`${id}-blade`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.72" />
          <stop offset="0.5" stopColor="currentColor" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0.86" />
        </linearGradient>
        <radialGradient id={`${id}-hub`} cx="38%" cy="35%" r="70%">
          <stop offset="0" stopColor="#FFD29A" />
          <stop offset="0.45" stopColor="#FF8A1E" />
          <stop offset="1" stopColor="#E85A0C" />
        </radialGradient>
      </defs>
      <circle className="krish-chakra-glow" cx="50" cy="50" r="17" fill="#FF8A1E" />
      <g className="krish-chakra-blade">
        <g className="krish-chakra-idle" fill={`url(#${id}-blade)`}>
          {TEETH.map((a) => (
            <path key={a} d="M45 20C47 11 53 6 61 5C58 9 56.5 14 56 20Z" transform={`rotate(${a} 50 50)`} />
          ))}
          <circle cx="50" cy="50" r="31" fill="none" stroke={`url(#${id}-blade)`} strokeWidth="6" />
          <circle cx="50" cy="50" r="22" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="3 5.2" opacity="0.5" />
        </g>
      </g>
      <g className="krish-chakra-hub">
        <circle cx="50" cy="50" r="11" fill={`url(#${id}-hub)`} />
        <circle cx="46.5" cy="46.5" r="3" fill="#fff" opacity="0.55" />
      </g>
    </svg>
  );
}
