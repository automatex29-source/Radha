import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";

// Sun/moon switch. The choice is remembered per browser; until the user picks,
// Krish AI follows the device's light/dark setting.
export default function ThemeToggle({ className = "" }) {
  const { resolvedTheme, setTheme } = useTheme();
  const dark = resolvedTheme !== "light";
  const label = dark ? "Switch to light theme" : "Switch to dark theme";

  return (
    <button type="button" onClick={() => setTheme(dark ? "light" : "dark")} title={label} aria-label={label}
      data-testid="theme-toggle"
      className={`flex h-10 w-10 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-surface hover:text-foreground ${className}`}>
      {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </button>
  );
}
