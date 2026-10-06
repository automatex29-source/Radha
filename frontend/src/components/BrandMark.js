import empirexLogo from "@/assets/empirex-logo.svg";

/** The EmpireX saw-blade logo, used as Krish AI's app icon and avatar. */
export default function BrandMark({ className = "" }) {
  return <img src={empirexLogo} alt="" draggable="false" className={`select-none ${className}`} />;
}
