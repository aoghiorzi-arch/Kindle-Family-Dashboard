// Browser checks for the phone editor. Needs a running local Worker (see docs/PHASE4_EDITOR.md).
// Uses two separate browser contexts so Alex (admin) and Sam (member) have separate sessions.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
// Loaded with require so the pre-installed global Playwright resolves; see docs/PHASE4_EDITOR.md.
const { chromium, devices } = require("playwright");
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const BASE = process.env.KFD_BASE ?? "http://localhost:8787";
const MEMBER_ADMIN = "e2e-admin";
const MEMBER_SAM = "e2e-member";

const failures = [];
const passes = [];
function check(name, ok, detail = "") {
  (ok ? passes : failures).push(name + (detail ? ` (${detail})` : ""));
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail && !ok ? ` — ${detail}` : ""}`);
}

async function signIn(page, memberId) {
  await page.goto(`${BASE}/`);
  await page.fill("#dev-member", memberId);
  await page.click('button[type="submit"]:has-text("Sign in")');
  await page.waitForSelector("#tabs:not([hidden])");
}

async function listedItems(page) {
  await page.waitForLoadState("networkidle");
  return page.$$eval("ul.list > li .item-title", (nodes) => nodes.map((n) => n.textContent));
}

async function axeViolations(page) {
  await page.evaluate(AXE);
  return page.evaluate(async () => {
    const result = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } });
    return result.violations.map((v) => `${v.id}(${v.impact}:${v.nodes.length})`);
  });
}

const browser = await chromium.launch();
try {
  // ---- Two family accounts, two sessions
  const alexCtx = await browser.newContext();
  const samCtx = await browser.newContext();
  const alex = await alexCtx.newPage();
  const sam = await samCtx.newPage();
  await signIn(alex, MEMBER_ADMIN);
  await signIn(sam, MEMBER_SAM);
  // Start from an empty test list so earlier runs cannot change the order checks.
  await alex.evaluate(async () => {
    const me = await (await fetch("/api/me")).json();
    const list = (await (await fetch("/api/shopping")).json()).items;
    for (const item of list) {
      await fetch(`/api/shopping/${item.id}?version=${item.version}`, { method: "DELETE", headers: { "X-CSRF-Token": me.csrfToken } });
    }
  });
  check("both family members can sign in", (await alex.textContent("#who")).includes("Alex") && (await sam.textContent("#who")).includes("Sam"));

  // ---- Shopping: add, and the other member sees it
  await alex.goto(`${BASE}/#/shopping`);
  await alex.fill("#new-item", "E2E Milk");
  await alex.click('form button[type="submit"]:has-text("Add")');
  await alex.waitForSelector('text="E2E Milk"');
  await sam.goto(`${BASE}/#/shopping`);
  check("another family member sees the new item", (await listedItems(sam)).includes("E2E Milk"));

  // ---- Completing an item is shared and persists
  await sam.check('input[aria-label="Got: E2E Milk"]');
  await alex.reload();
  await alex.waitForSelector('input[aria-label="Got: E2E Milk"]');
  check("completion made by one member persists for the other", await alex.isChecked('input[aria-label="Got: E2E Milk"]'));

  // ---- Stale edit is refused, not silently overwritten
  await sam.reload();
  await sam.waitForSelector('input[aria-label="Got: E2E Milk"]');
  await alex.reload();
  await alex.waitForSelector('button:has-text("Rename")');
  await alex.click('li:has-text("E2E Milk") button:has-text("Rename")');
  await alex.fill('li:has-text("E2E Milk") input[aria-label="New name"]', "E2E Oat milk");
  await alex.click('li:has-text("E2E Milk") button:has-text("Save")');
  await alex.waitForSelector('text="E2E Oat milk"');
  // Sam's page still shows the old name and version, so this change must be refused.
  await sam.click('input[aria-label="Got: E2E Milk"]');
  await sam.waitForSelector('[role="status"]:has-text("Someone else changed")', { timeout: 5000 }).then(
    () => check("stale edit from another member is refused with a clear message", true),
    () => check("stale edit from another member is refused with a clear message", false, "no conflict message shown"),
  );
  check("after a conflict the list shows the other member's change", (await listedItems(sam)).includes("E2E Oat milk"));

  // ---- Reordering and deleting
  await alex.fill("#new-item", "E2E Bread");
  await alex.click('form button[type="submit"]:has-text("Add")');
  await alex.waitForSelector('text="E2E Bread"');
  await alex.click('button[aria-label="Move E2E Bread up"]');
  // Wait for the rendered order, not for network idle: idle can be reported before the click has sent anything.
  await alex.waitForFunction(() => document.querySelector("ul.list > li .item-title")?.textContent === "E2E Bread", null, { timeout: 10000 })
    .then(() => check("moving an item up changes the order", true), () => check("moving an item up changes the order", false, "order unchanged"));
  alex.once("dialog", (dialog) => dialog.accept());
  await alex.click('button[aria-label="Delete E2E Bread"]');
  await alex.waitForFunction(() => ![...document.querySelectorAll(".item-title")].some((n) => n.textContent === "E2E Bread"), null, { timeout: 10000 });
  await sam.reload();
  check("delete removes the item for everyone", !(await listedItems(sam)).includes("E2E Bread"));

  // ---- Account separation: member cannot manage devices
  await sam.goto(`${BASE}/#/settings`);
  await sam.waitForSelector("h2:has-text('Settings')");
  check("a member does not see device management", (await sam.locator("h2:has-text('Devices')").count()) === 0);

  // ---- Admin creates a display credential; token is shown once and not kept
  await alex.goto(`${BASE}/#/settings`);
  await alex.fill("#device-name", "E2E hall display");
  await alex.selectOption("#device-kind", "display");
  await alex.click('button:has-text("Create device")');
  await alex.waitForSelector("#token-value");
  const token = await alex.textContent("#token-value");
  check("new display token is shown once for copying", token.startsWith("kfd_"));
  const snapshot = await fetch(`${BASE}/api/device/snapshot`, { headers: { Authorization: `Bearer ${token}` } });
  check("the display token reads the snapshot", snapshot.status === 200);
  check("the display token cannot read the shopping list", (await fetch(`${BASE}/api/shopping`, { headers: { Authorization: `Bearer ${token}` } })).status === 401);
  await alex.reload();
  check("the token is not kept after reload", (await alex.locator("#token-value").count()) === 0);

  // ---- Source contains no credentials
  const html = await (await fetch(`${BASE}/`)).text();
  const js = await (await fetch(`${BASE}/app.js`)).text();
  check("served pages contain no tokens", !html.includes("kfd_") && !js.includes("kfd_"));

  // ---- Phone layout: no horizontal scroll at iPhone width
  const phoneCtx = await browser.newContext({ ...devices["iPhone 13"] });
  const phone = await phoneCtx.newPage();
  await signIn(phone, MEMBER_SAM);
  for (const route of ["home", "shopping", "calendar", "settings"]) {
    await phone.goto(`${BASE}/#/${route}`);
    await phone.waitForLoadState("networkidle");
    const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`no horizontal scroll on phone width: ${route}`, overflow <= 0, `${overflow}px`);
  }

  // ---- Accessibility smoke test (WCAG 2 A and AA rules via axe-core)
  const signedOut = await (await browser.newContext()).newPage();
  await signedOut.goto(`${BASE}/`);
  await signedOut.waitForSelector("h2");
  for (const [label, page, route] of [
    ["sign-in", signedOut, null],
    ["home", alex, "home"],
    ["shopping", alex, "shopping"],
    ["calendar", alex, "calendar"],
    ["settings (admin)", alex, "settings"],
    ["settings (member)", sam, "settings"],
  ]) {
    if (route) {
      await page.goto(`${BASE}/#/${route}`);
      await page.waitForLoadState("networkidle");
    }
    const violations = await axeViolations(page);
    check(`accessibility: ${label}`, violations.length === 0, violations.join(", "));
  }
} finally {
  await browser.close();
}

console.log(`\n${passes.length} passed, ${failures.length} failed`);
if (failures.length) process.exit(1);
