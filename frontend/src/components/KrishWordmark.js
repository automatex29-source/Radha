/**
 * The "Krish AI" wordmark: clean geometric letters in the text colour, with the dot of the "i"
 * and "AI" in the chakra's orange so the name and the logo read as one brand.
 */
export default function KrishWordmark({ className = "" }) {
  return (
    <span className={`krish-wordmark ${className}`} aria-label="Krish AI">
      <span aria-hidden="true">
        Kr<span className="krish-wordmark-i">ı</span>sh <span className="krish-wordmark-ai">AI</span>
      </span>
    </span>
  );
}
