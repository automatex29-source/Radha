const PETALS = Array.from({ length: 8 }, (_, i) => i);
const COLORS = ["var(--rangoli-saffron)", "var(--rangoli-blue)", "var(--rangoli-green)"];

/**
 * Krish's "answering" mark: a small 8-petal rangoli that turns slowly while its petals light up
 * one after another in saffron, blue and green.
 */
export default function RangoliBloom({ className = "" }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={`krish-rangoli ${className}`}>
      {PETALS.map((i) => (
        <ellipse
          key={i}
          cx="12" cy="5.2" rx="2.3" ry="4.2"
          fill={COLORS[i % 3]}
          transform={`rotate(${i * 45} 12 12)`}
          style={{ animationDelay: `${(i * 0.2).toFixed(1)}s` }}
        />
      ))}
      <circle cx="12" cy="12" r="2.2" fill="var(--rangoli-saffron)" />
    </svg>
  );
}
