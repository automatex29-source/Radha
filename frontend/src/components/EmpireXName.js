/** "by EmpireX" under the Krish AI wordmark: EmpireX in the logo's gold. */
export default function EmpireXName({ by = true, className = "" }) {
  return (
    <span className={`inline-flex items-baseline gap-1.5 leading-none ${className}`}>
      {by && <span className="text-[10px] font-medium italic text-muted-foreground">by</span>}
      <span className="empirex-name">EmpireX</span>
    </span>
  );
}
