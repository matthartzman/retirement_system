// WP5.1 owner checkpoint: screenshots of the Plan Features tier picker.
//
// Starts tools/e2e_server.py (a throwaway workspace seeded from the frozen
// sample plan, which has no tier row, so it opens as "Expert (customized)"),
// opens Settings > Plan Features and captures, at desktop (1280x900) and
// phone (390x844) size:
//   1. the tier picker as the plan opens (no tier picked: Expert);
//   2. the confirm dialog previewing a pick of Standard;
//   3. the customized state: Standard applied, then one switch overridden.
// Each viewport gets its own server, so each starts from the same plan.
//
// Run from the repo root. Chromium: CHROMIUM_PATH when set, else
// /opt/pw-browsers/chromium when it exists, else Playwright's own browser
// (never `playwright install` in the sandbox):
//   node tools/capture_wp5_screens.mjs [outDir]
// outDir defaults to documentation/reference/wp5_screens (see its ABOUT.md).
import { chromium } from "@playwright/test";
import { spawn, spawnSync } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.resolve(ROOT, process.argv[2] || "documentation/reference/wp5_screens");
const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "mobile", width: 390, height: 844 },
];

function waitForServer(url, deadline) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve();
      });
      req.on("error", () => (Date.now() > deadline ? reject(new Error(`no server at ${url}`)) : setTimeout(attempt, 500)));
      req.setTimeout(2000, () => req.destroy());
    };
    attempt();
  });
}

async function startServer(port) {
  const child = spawn(process.platform === "win32" ? "python" : "python3", ["tools/e2e_server.py"], {
    cwd: ROOT,
    env: { ...process.env, RETIREMENT_SYSTEM_E2E_PORT: String(port) },
    stdio: ["ignore", "ignore", "inherit"],
  });
  const url = `http://127.0.0.1:${port}`;
  await waitForServer(url, Date.now() + 30_000);
  return { child, url };
}

async function openPlanFeatures(page, url) {
  await page.goto(url);
  await page.locator("#appStatus", { hasText: "Ready" }).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: "Open Current Plan" }).click();
  const keepEditing = page.getByRole("button", { name: "Keep Editing" });
  if (await keepEditing.isVisible({ timeout: 1000 }).catch(() => false)) await keepEditing.click();
  await page.waitForFunction(() => window.planLoaded === true, null, { timeout: 30_000 });
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => window.setStep("optional_functions"));
  await page.locator(".pf-tier").waitFor({ timeout: 15_000 });
}

async function shot(page, file, locator) {
  // Scroll the subject to just below the sticky header (tall on a phone).
  if (locator)
    await locator.evaluate((el) => {
      el.scrollIntoView({ block: "start" });
      const head = document.querySelector("header");
      window.scrollBy(0, -((head ? head.getBoundingClientRect().bottom : 0) + 8));
    });
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(OUT, file) });
  console.log("wrote", path.relative(ROOT, path.join(OUT, file)));
}

async function capture(browser, vp, port) {
  const { child, url } = await startServer(port);
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  try {
    await openPlanFeatures(page, url);
    const picker = page.locator(".pf-tier");
    await shot(page, `wp5_${vp.name}_1_tier_picker_default_expert.png`, picker);

    await page.locator(".pf-tier-card", { hasText: "Standard" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.waitFor({ timeout: 15_000 });
    await shot(page, `wp5_${vp.name}_2_standard_preview_confirm.png`);

    await dialog.getByRole("button", { name: "Apply Standard" }).click();
    await page.locator(".pf-tier-card.selected", { hasText: "Standard" }).waitFor({ timeout: 30_000 });
    // One override on top of the preset: the plan now reads "Standard (customized)".
    await page.evaluate(() => window.setPlanFeatureSwitch("planning_workbench", true));
    await page.locator(".pf-tier-status", { hasText: "Standard (customized)" }).waitFor({ timeout: 30_000 });
    await page.evaluate(() => window.setStep("optional_functions"));
    // A phone shows only part of the picker below its tall header: aim at the
    // second row of cards, so the status line and the reset action are in view.
    const status = vp.width < 600 ? page.locator(".pf-tier-cards .pf-tier-card").nth(2) : picker;
    await shot(page, `wp5_${vp.name}_3_customized_with_reset.png`, status);
    const badge = page.locator(".pf-tier-diff").first();
    await shot(page, `wp5_${vp.name}_4_customized_row_badge.png`, badge);
  } finally {
    await context.close();
    // SIGINT, so e2e_server.py's own cleanup removes its throwaway workspace.
    await new Promise((resolve) => {
      child.once("exit", resolve);
      child.kill("SIGINT");
    });
  }
}

fs.mkdirSync(OUT, { recursive: true });
const exe = process.env.CHROMIUM_PATH || (fs.existsSync("/opt/pw-browsers/chromium") ? "/opt/pw-browsers/chromium" : undefined);
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
try {
  let port = Number(process.env.WP5_SCREENS_PORT || 5990);
  for (const vp of VIEWPORTS) await capture(browser, vp, port++);
} finally {
  await browser.close();
}

// Keep the committed PNGs small: a 256-colour palette when Pillow is available
// (the screenshots are flat UI colours, so nothing visible is lost).
const shrink = spawnSync(process.platform === "win32" ? "python" : "python3", ["-c", [
  "import sys, pathlib",
  "from PIL import Image",
  "for p in pathlib.Path(sys.argv[1]).glob('wp5_*.png'):",
  "    Image.open(p).convert('RGB').quantize(256).save(p, optimize=True)",
].join("\n"), OUT], { stdio: "inherit" });
if (shrink.status !== 0) console.log("Pillow not available: PNGs left at full colour");
