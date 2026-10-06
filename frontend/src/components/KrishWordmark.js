/** The "Krish AI" name in the brand font, with "AI" in the orange of the saw-blade logo. */
export default function KrishWordmark({ className = "" }) {
  return (
    <span className={`krish-wordmark ${className}`}>
      Krish <span className="krish-wordmark-ai">AI</span>
    </span>
  );
}
