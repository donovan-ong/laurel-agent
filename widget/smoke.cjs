// Smoke test: drives the real widget in headless Chrome and saves screenshots to widget/.smoke/.
//
//   python scripts/widget_stub.py --port 8111 --delay 4     (canned agent, no Orchestrate needed)
//   cd widget && npm run build && npm run smoke -- http://127.0.0.1:8111/demo/index.html
//
// Covers: launcher holds position while scrolling, in-widget login (bad and good password), chips, loading
// indicator, replies with a table, trace toggle, history restored after reload, sign out, phone layout.
// Part A checks the login form with the keyboard, because in this automation typing into a password field
// leaves Chrome's mouse input dead for that browser session; the rest runs in fresh sessions with a seeded
// token, where real mouse clicks are used.
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const path = require("path");

const TARGET = process.argv[2] || "http://127.0.0.1:8111/demo/index.html";
const OUT = path.join(__dirname, ".smoke");
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (sel) => `pierce/${sel}`;
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

async function open(viewport = { width: 1365, height: 900 }) {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new" });
  const page = await browser.newPage();
  await page.setViewport(viewport);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  return { browser, page, errors };
}
const shot = (page, name) => page.screenshot({ path: path.join(OUT, `${name}.png`) });
const box = (page, sel) => page.$eval($(sel), (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; });

async function partA() {
  const { browser, page, errors } = await open();
  await page.goto(TARGET, { waitUntil: "networkidle0" });
  await page.evaluate(() => sessionStorage.clear());
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector($(".lw-launcher"));
  await shot(page, "01-launcher");
  const before = await box(page, ".lw-launcher");
  await page.evaluate(() => window.scrollTo(0, 1500));
  await sleep(200);
  const after = await box(page, ".lw-launcher");
  console.log("launcher before/after scroll:", JSON.stringify(before), JSON.stringify(after), before.y === after.y ? "HOLDS" : "MOVED");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.click($(".lw-launcher"));
  await sleep(300);
  await shot(page, "02-login");
  console.log("panel:", JSON.stringify(await box(page, ".lw-panel")));
  // wrong password first
  await page.type($(".lw-login input[type=text]"), "demo4");
  await page.type($(".lw-login input[type=password]"), "nope");
  await page.keyboard.press("Enter");
  await page.waitForSelector($(".lw-form-error"));
  console.log("bad password message:", await page.$eval($(".lw-form-error"), (e) => e.textContent));
  await shot(page, "02b-login-error");
  await page.reload({ waitUntil: "networkidle0" }); // the open panel is remembered for the session
  await page.waitForSelector($(".lw-login input[type=text]"));
  await page.type($(".lw-login input[type=text]"), "demo4");
  await page.type($(".lw-login input[type=password]"), "demo4");
  await page.keyboard.press("Enter");
  await page.waitForSelector($(".lw-chip"));
  console.log("form login ok, chips:", await page.$$eval($(".lw-chip"), (e) => e.map((x) => x.textContent)));
  console.log("greeting:", await page.$eval($(".lw-empty h2"), (e) => e.textContent));
  await sleep(300);
  await shot(page, "03-empty-chips");
  console.log("A errors:", errors.length ? errors : "none");
  await browser.close();
}

async function partB() {
  const { browser, page, errors } = await open();
  await page.goto(TARGET, { waitUntil: "networkidle0" });
  await page.evaluate(async () => {
    const r = await fetch("/api/widget/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "demo4", password: "demo4" }) });
    sessionStorage.clear();
    sessionStorage.setItem("laurel.token", (await r.json()).token);
    sessionStorage.setItem("laurel.open", "1");
  });
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector($(".lw-chip"));
  await sleep(400);

  await page.click($(".lw-chip"));
  await sleep(1300);
  await shot(page, "04-loading");
  console.log("loading text:", await page.$eval($(".lw-loading"), (e) => e.textContent));
  await page.waitForSelector($(".lw-actions"), { timeout: 15000 });
  await sleep(300);
  await shot(page, "05-reply");

  await page.click($("button[aria-label='Show the tool-call trace']"));
  await sleep(300);
  const summary = await page.$($(".lw-trace summary"));
  console.log("trace shown:", !!summary);
  if (summary) { await summary.click(); await sleep(200); }
  await shot(page, "06-trace");

  await page.click($(".lw-input input"));
  await page.keyboard.type("What do I have on loan?");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.getElementById("laurel-widget-host").shadowRoot.querySelectorAll(".lw-assistant").length >= 2, { timeout: 15000 });
  await sleep(300);
  await shot(page, "07-table-reply");

  // copy / thumbs / retry
  const thumbs = await page.$$($("button[aria-label='Good response']"));
  await thumbs[1].click();
  await page.click($("button[aria-label='Retry']:last-of-type"), { }).catch(() => {});
  await sleep(300);

  // phone: the general-enquiries number is offered as a tel: link, and closes again
  await page.click($("button[aria-label='Call RMIT']"));
  await page.waitForSelector($(".lw-phone"));
  console.log("phone panel:", await page.$eval($(".lw-phone-number"), (e) => `${e.textContent} ${e.getAttribute("href")}`));
  await shot(page, "07a-phone");
  await page.click($("button[aria-label='Call RMIT']"));
  await sleep(100);
  console.log("phone panel closes:", (await page.$$($(".lw-phone"))).length === 0);

  // expand: a larger window, still on the page; kept after reload; collapse returns to the default size
  const small = await box(page, ".lw-panel");
  await page.click($("button[aria-label='Make the chat window larger']"));
  await sleep(300);
  const large = await box(page, ".lw-panel");
  await shot(page, "07b-expanded");
  console.log("expand:", JSON.stringify({ small: [small.w, small.h], large: [large.w, large.h] }), large.w > small.w && large.h > small.h ? "LARGER" : "NOT LARGER");
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector($(".lw-assistant"), { timeout: 8000 });
  const kept = await box(page, ".lw-panel");
  console.log("expanded size kept after reload:", kept.w === large.w);
  await page.click($("button[aria-label='Make the chat window smaller']"));
  await sleep(300);
  console.log("collapse returns to default width:", (await box(page, ".lw-panel")).w === small.w);
  await page.click($("button[aria-label='Make the chat window larger']"));
  await sleep(200);
  console.log("assistant messages restored after reload:", await page.$$eval($(".lw-assistant"), (els) => els.length));
  console.log("trace preference kept after reload:", await page.$$eval($(".lw-trace"), (els) => els.length > 0));

  // sign out returns to the login form
  await page.click($("button[aria-label='Sign out']"));
  await page.waitForSelector($(".lw-login"));
  console.log("signed out -> login form shown");

  console.log("B errors:", errors.length ? errors : "none");
  await browser.close();
}

async function partC() {
  const { browser, page } = await open({ width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 });
  await page.goto(TARGET, { waitUntil: "networkidle0" });
  await page.evaluate(async () => {
    const r = await fetch("/api/widget/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "demo4", password: "demo4" }) });
    sessionStorage.clear();
    sessionStorage.setItem("laurel.token", (await r.json()).token);
    sessionStorage.setItem("laurel.open", "1");
  });
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector($(".lw-chip"));
  await sleep(400);
  await shot(page, "08-mobile");
  console.log("mobile panel:", JSON.stringify(await box(page, ".lw-panel")));
  await browser.close();
}

async function partD() {
  // Another chat button is already fixed in the bottom-right corner: the launcher must sit above it.
  const { browser, page } = await open();
  await page.goto(new URL("/demo/crowded.html", TARGET).href, { waitUntil: "networkidle0" });
  await page.waitForSelector($(".lw-launcher"));
  await sleep(300);
  const other = await page.$eval("#other-chat", (el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; });
  const launcher = await box(page, ".lw-launcher");
  const clear = launcher.y + launcher.h <= other.top;
  console.log("launcher clear of another fixed chat button:", clear ? "yes" : "NO (overlaps)", JSON.stringify({ other, launcher }));
  await shot(page, "09-crowded-corner");
  await browser.close();
}

(async () => {
  await partA();
  await partB();
  await partC();
  await partD();
})().catch((e) => { console.error(e); process.exit(1); });
