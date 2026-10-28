// Browser end-to-end check: sign in, edit the lists as a phone user would, and confirm the preview changes.
// Run by tests/test_e2e.py with E2E_BASE, E2E_USER and E2E_PASS set. Exit code 77 means Playwright is not installed.
let chromium;
try {
  ({chromium} = require('playwright'));
} catch (e) {
  console.log('playwright is not installed');
  process.exit(77);
}

const base = process.env.E2E_BASE;
const user = process.env.E2E_USER;
const pass = process.env.E2E_PASS;

function check(condition, message) {
  if (!condition) throw new Error(message);
}

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));

    await page.goto(base + '/');
    await page.fill('#username', user);
    await page.fill('#password', pass);
    await page.click('#loginForm button');
    await page.waitForSelector('#app:not([hidden])');

    // The preview bytes are fetched with the page's own session cookie.
    const frame = async () => (await page.context().request.get(base + '/frame.png')).body();
    const before = await frame();

    await page.fill('#item', 'Cheese');
    await page.click('#shopping button');
    await page.waitForSelector('#items li:has-text("Cheese")');
    const afterShopping = await frame();
    check(!before.equals(afterShopping), 'adding a shopping item did not change the preview');

    await page.fill('#eventTitle', 'Dentist');
    await page.fill('#eventTime', '11:15');
    await page.check('#eventPrivate');
    await page.click('#event button');
    await page.waitForSelector('#events li:has-text("Dentist")');
    const afterEvent = await frame();
    check(!afterShopping.equals(afterEvent), 'adding a private event did not change the preview');

    await page.locator('#items li', {hasText: 'Cheese'}).getByRole('button', {name: 'Remove'}).click();
    await page.waitForSelector('#items li:has-text("Cheese")', {state: 'detached'});
    check(!afterEvent.equals(await frame()), 'removing a shopping item did not change the preview');

    const size = await page.$eval('#screen', img => [img.naturalWidth, img.naturalHeight]);
    check(size[0] === 600 && size[1] === 800, `preview is ${size[0]}x${size[1]}, expected 600x800`);
    check(errors.length === 0, `page errors: ${errors.join('; ')}`);
    console.log('phone edit path OK: shopping, private event and removal each updated the preview');
  } finally {
    await browser.close();
  }
})().catch(e => {
  console.error('FAILED:', e.message);
  process.exitCode = 1;
});
