import krishIcon from "@/assets/krish-icon.svg";

/** The Krish AI app icon (a "K" on the brand gradient). The EmpireX gear logo stays in assets/empirex-logo.svg for the company. */
export default function BrandMark({ className = "" }) {
  return <img src={krishIcon} alt="" draggable="false" className={`select-none ${className}`} />;
}
