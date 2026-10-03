// Smoke test for the Chrome extension: loads it unpacked in headless Chrome, points it at a stub backend and
// checks the widget works through the extension's service worker.
//
//   python scripts/widget_stub.py --port 8111 --delay 4
//   cd widget && npm run build:extension && npm run smoke:extension -- http://127.0.0.1:8111
//
// For the long-reply check (Chrome ends an extension worker whose fetch takes more than 30 s; the worker pings an
// extension API to stay alive), run a second stub with --delay 45 and pass its address instead.
//
// Recent branded Chrome builds ignore --load-extension, so the extension is installed through Puppeteer's
// browser.installExtension. The shipped manifest matches only https://www.rmit.edu.au/*, so the test loads a
// temporary copy that also matches the local plain page (demo/plain.html, which has no widget script of its own).
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8111";
const SRC = path.join(__dirname, "..", "extension");
const OUT = path.join(__dirname, ".smoke");
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const $ = (sel) => `pierce/${sel}`;
fs.mkdirSync(OUT, { recursive: true });

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "laurel-ext-"));
fs.cpSync(SRC, tmp, { recursive: true });
const manifest = JSON.parse(fs.readFileSync(path.join(tmp, "manifest.json"), "utf8"));
manifest.content_scripts[0].matches.push("http://127.0.0.1/demo/plain.html");
fs.writeFileSync(path.join(tmp, "manifest.json"), JSON.stringify(manifest, null, 2));

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", pipe: true, enableExtensions: true, args: ["--enable-unsafe-extension-debugging"] });
  await browser.installExtension(tmp);
  const worker = await (await browser.waitForTarget((t) => t.type() === "service_worker", { timeout: 15000 })).worker();
  await worker.evaluate((b) => chrome.storage.local.set({ apiBase: b }), BASE);

  const page = await browser.newPage();
  await page.setViewport({ width: 1365, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${BASE}/demo/plain.html`, { waitUntil: "networkidle0" });
  await page.waitForSelector($(".lw-launcher"), { timeout: 8000 });
  console.log("extension added the widget to a page with no script of its own: yes");

  // Sign in through the worker, as the form would, so the page's mouse stays usable for the rest of the test.
  const who = await worker.evaluate(async (b) => {
    const r = await fetch(b + "/api/widget/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "demo4", password: "demo4" }) });
    const d = await r.json();
    await chrome.storage.session.set({ token: d.token });
    return d.username;
  }, BASE);
  console.log("session held by the worker for:", who);
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector($(".lw-launcher"));
  await page.click($(".lw-launcher"));
  await page.waitForSelector($(".lw-chip"), { timeout: 8000 });
  console.log("signed in through the extension transport; greeting:", await page.$eval($(".lw-empty h2"), (e) => e.textContent));

  const started = Date.now();
  await page.click($(".lw-chip:nth-of-type(3)"));
  await page.waitForSelector($(".lw-actions"), { timeout: 100000 });
  console.log(`reply came back through the service worker after ${Math.round((Date.now() - started) / 1000)}s:`, (await page.$eval($(".lw-assistant"), (e) => e.textContent)).slice(0, 50));
  await page.screenshot({ path: path.join(OUT, "ext-reply.png") });

  const seenByPage = await page.evaluate(() => JSON.stringify({ s: { ...sessionStorage }, l: { ...localStorage }, c: document.cookie }));
  const token = await worker.evaluate(async () => (await chrome.storage.session.get("token")).token);
  console.log("session token visible to the page:", seenByPage.includes(token) ? "YES (BAD)" : "no");

  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector($(".lw-assistant"), { timeout: 10000 });
  console.log("conversation restored on the next page load:", (await page.$$eval($(".lw-assistant"), (e) => e.length)) > 0);

  await page.click($("button[aria-label='Sign out']"));
  await page.waitForSelector($(".lw-login"));
  console.log("token after sign out:", await worker.evaluate(async () => (await chrome.storage.session.get("token")).token || "cleared"));
  console.log("page errors:", errors.length ? errors : "none");
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
