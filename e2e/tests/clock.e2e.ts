import assert from 'node:assert/strict';
import { test } from '@e2e-dev/web';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const read = (browser: any) =>
  browser.evaluate(() => (document.querySelector('.clock[data-clock]') as HTMLElement | null)?.textContent?.trim() ?? '');

test('the shot timer counts down and resets', async ({ app, browser }) => {
  await app.open('/#/clock');
  let before = '';
  for (let i = 0; i < 80 && !/^\d+:\d{2}$/.test(before); i += 1) {
    before = await read(browser);
    if (!/^\d+:\d{2}$/.test(before)) await wait(250);
  }
  assert.match(before, /^\d+:\d{2}$/, 'the clock reads minutes:seconds');
  await browser.evaluate(() => (document.querySelector('[data-action="clock-toggle"]') as HTMLElement).click());
  await wait(1800);
  const during = await read(browser);
  assert.notEqual(during, before, 'Start moves the clock');
  await browser.evaluate(() => (document.querySelector('[data-action="clock-reset"]') as HTMLElement).click());
  let after = '';
  for (let i = 0; i < 40 && after !== before; i += 1) {
    await wait(150);
    after = await read(browser);
  }
  assert.equal(after, before, 'Reset returns the clock to its preset');
});
