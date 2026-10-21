import assert from 'node:assert/strict';
import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('the console opens with its six tabs and an event card', async ({ app, browser }) => {
  await app.open('/');
  await expect(browser.locator('#tabbar button[data-tab]')).toHaveCount(6);
  await expect(browser.locator('#main .card--event')).toBeVisible();
  const tabs = await browser.evaluate(() =>
    [...document.querySelectorAll('#tabbar button[data-tab]')].map((b) => (b as HTMLElement).dataset.tab));
  assert.deepEqual(tabs, ['clock', 'tonight', 'records', 'vision', 'players', 'status']);
  const noise = await browser.evaluate(() =>
    ((document.querySelector('#message') as HTMLElement | null)?.textContent ?? '').trim());
  assert.equal(noise, '', 'the shell shows no error banner');
});
