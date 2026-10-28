// Automatic preview checks must preserve form drafts and the last decoded image.
let chromium;
try { ({chromium} = require('playwright')); } catch (e) { process.exit(77); }
const base = process.env.E2E_BASE;
const check = (ok, message) => { if (!ok) throw new Error(message); };

(async () => {
  const browser = await chromium.launch({executablePath: process.env.E2E_CHROMIUM_EXECUTABLE_PATH || undefined});
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    await page.clock.install();
    await page.goto(base + '/');
    await page.fill('#username', process.env.E2E_USER);
    await page.fill('#password', process.env.E2E_PASS);
    await page.click('#loginForm button');
    await page.waitForFunction(() => document.getElementById('screen').naturalWidth === 600);
    const src = () => page.getAttribute('#screen', 'src');
    const before = await src();
    await page.fill('#item', 'Unfinished shopping draft');
    await page.fill('#lat', '12.345');

    // A second phone (same session here) makes an edit, without invoking this page's refresh().
    const csrf = await page.evaluate(async () => (await (await fetch('/api/state')).json()).csrf);
    await page.context().request.post(base + '/api/shopping', {
      headers: {'X-CSRF-Token': csrf, Origin: base}, data: {title: 'Automatic preview test'}
    });
    await page.clock.fastForward(60_000);
    await page.waitForFunction(previous => document.getElementById('screen').src !== previous, before);
    await page.waitForFunction(() => document.getElementById('screen').naturalWidth === 600);
    const updated = await src();
    check(await page.inputValue('#item') === 'Unfinished shopping draft', 'polling erased shopping draft');
    check(await page.inputValue('#lat') === '12.345', 'polling reset location draft');

    // An unchanged conditional response must not cause a new image URL or redraw.
    const unchanged = page.waitForResponse(r => r.url().endsWith('/frame.png') && r.status() === 304);
    await page.clock.fastForward(60_000);
    await unchanged;
    check(await src() === updated, 'unchanged frame was redrawn');

    await page.route('**/frame.png', route => route.fulfill({status: 503, body: '{}'}));
    await page.clock.fastForward(60_000);
    await page.waitForFunction(() => document.getElementById('previewStatus').textContent.includes('Keeping'));
    check(await src() === updated, 'failed refresh discarded the last image');
    check(await page.$eval('#screen', img => img.naturalWidth) === 600, 'failed refresh broke the preview');

    await page.unroute('**/frame.png');
    await page.clock.fastForward(60_000);
    await page.waitForFunction(() => document.getElementById('previewStatus').textContent.includes('checks every minute'));
    await page.click('#logout');
    await page.waitForSelector('#login:not([hidden])');
    check(await src() === null, 'sign-out retained the private preview');
    console.log('preview polling OK: automatic update, drafts, unchanged hash, failure, recovery and sign-out');
  } finally { await browser.close(); }
})().catch(e => { console.error('FAILED:', e.message); process.exitCode = 1; });
