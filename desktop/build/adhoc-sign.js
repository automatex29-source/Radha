// Gives the Mac app a free "ad-hoc" signature after it's packed. Apple silicon Macs won't open an app with no
// signature at all ("the app is damaged"). This isn't a paid Apple Developer certificate, so the Mac still asks
// once before opening it (System Settings > Privacy & Security > Open Anyway).
const { execFileSync } = require("child_process");
const path = require("path");

exports.default = async function adhocSign(context) {
  if (context.electronPlatformName !== "darwin") return;
  // A universal build packs an Intel and an Apple silicon copy first ("-temp") and then joins them; sign the result.
  if (/-temp$/.test(context.appOutDir)) return;
  const app = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  execFileSync("codesign", ["--force", "--deep", "--sign", "-", app], { stdio: "inherit" });
  execFileSync("codesign", ["--verify", "--deep", "--strict", app], { stdio: "inherit" });
  console.log(`  • ad-hoc signed ${app}`);
};
