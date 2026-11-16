/**
 * Krish's "working on it" mark, used everywhere Krish is thinking, answering or making something:
 * a square outline that turns and softens into a circle and back, with a saffron centre.
 * `onColor` draws it in white for coloured buttons.
 */
export default function ThinkingShape({ size = 13, className = "", onColor = false }) {
  const border = size >= 28 ? 2.5 : size >= 18 ? 2 : 1.6;
  return (
    <span aria-hidden="true" className={`krish-shape ${onColor ? "is-on-color" : ""} ${className}`}
      style={{ width: size, height: size, borderWidth: border }} data-testid="thinking-shape" />
  );
}
