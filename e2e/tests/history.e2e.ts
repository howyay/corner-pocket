import assert from 'node:assert/strict';
import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('History opens a broadcast and its review stage paints a frame with no warning', async ({ app, browser }) => {
  await app.open('/#/records');
  await expect(browser.locator('#main')).toContainText('History');
  await expect(browser.locator('#main [data-action="tl-review"]').first()).toBeVisible();

  await browser.evaluate(() => (document.querySelector('#main [data-action="tl-review"]') as HTMLElement).click());
  await expect(browser.locator('.vision-surface')).toBeVisible();
  // Before the first frame lands, the workbench keeps the page width: a flex column once shrank it to
  // its empty content (887 px of 1219 at 1280 wide).
  const layout = await browser.evaluate(() => {
    const surface = (document.querySelector('.vision-surface') as HTMLElement).getBoundingClientRect();
    const main = (document.querySelector('#ops-shell main') as HTMLElement).getBoundingClientRect();
    return { surface: Math.round(surface.width), main: Math.round(main.width) };
  });
  assert.ok(layout.surface >= layout.main - 80, `the workbench fills the page (${layout.surface} of ${layout.main} px)`);
  // The server decodes the first frame on demand; on a loaded host that took 25 s, so allow 60 s.
  let width = 0;
  for (let i = 0; i < 240 && width === 0; i += 1) {
    width = await browser.evaluate(() =>
      (document.querySelector('#t-img') as HTMLImageElement | null)?.naturalWidth ?? 0);
    if (width === 0) await new Promise((resolve) => setTimeout(resolve, 250));
  }
  assert.ok(width > 0, 'the review stage painted a decoded frame');
  const warning = await browser.evaluate(() =>
    ((document.querySelector('#message') as HTMLElement | null)?.textContent ?? '').trim());
  assert.doesNotMatch(warning, /decoded|解码帧/, 'the stage warns only while it has no frame');
});
