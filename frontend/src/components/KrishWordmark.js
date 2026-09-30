/** The "Krish AI" name in the brand font, with "AI" in the blue-purple-pink glow. */
export default function KrishWordmark({ className = "" }) {
  return (
    <span className={`krish-wordmark ${className}`}>
      Krish <span className="krish-wordmark-ai">AI</span>
    </span>
  );
}
