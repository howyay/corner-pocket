import assert from 'node:assert/strict';
import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('the competition card keeps the pencil by the name and its buttons on one row', async ({ app, browser }) => {
  await app.open('/#/tonight');
  await expect(browser.locator('#main .card--event .event-title')).toBeVisible();
  const card = await browser.evaluate(() => {
    const c = document.querySelector('#main .card--event') as HTMLElement;
    const title = c.querySelector('.event-title') as HTMLElement | null;
    const pencil = c.querySelector('.event-head .event-rename') as HTMLElement | null;
    const row = c.querySelector('.row') as HTMLElement | null;
    const buttons = [...(row?.querySelectorAll('button') ?? [])] as HTMLElement[];
    const top = (e: HTMLElement | null) => (e ? Math.round(e.getBoundingClientRect().top) : -1);
    return {
      title: (title?.textContent ?? '').trim(),
      hasPencil: !!pencil,
      pencilLabel: pencil?.getAttribute('aria-label') ?? '',
      headTop: top(title),
      pencilTop: top(pencil),
      rowActions: buttons.map((b) => b.dataset.action ?? ''),
      rowTops: buttons.map((b) => top(b)),
    };
  });
  assert.ok(card.title.length > 0, 'the event has a name');
  assert.ok(card.hasPencil, 'the pencil sits beside the name');
  assert.match(card.pencilLabel, /rename/i);
  assert.ok(Math.abs(card.headTop - card.pencilTop) <= 6, 'the pencil is on the title line');
  assert.ok(card.rowActions.length >= 2, 'the card carries its buttons in one row');
  assert.equal(new Set(card.rowTops).size, 1, 'every button shares one row');

  const before = card.title;
  await browser.evaluate(() => (document.querySelector('#main .event-rename') as HTMLElement).click());
  await expect(browser.locator('#event-name')).toBeVisible();
  const label = await browser.evaluate(() =>
    (document.querySelector('#event-name') as HTMLInputElement | null)?.getAttribute('aria-label') ?? '');
  assert.match(label, /rename/i, 'the field is named for the rename');
  await browser.evaluate(() => (document.querySelector('[data-action="event-rename-cancel"]') as HTMLElement).click());
  const after = await browser.evaluate(() =>
    (document.querySelector('#main .event-title') as HTMLElement | null)?.textContent?.trim() ?? '');
  assert.equal(after, before, 'cancel leaves the name alone');
});
