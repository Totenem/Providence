import { test, expect } from '@playwright/test';

test('showcase, download CTAs, examples, FAQ, and responsive layout', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page).toHaveTitle(/Providence.*Offline AI File Search/);
  await expect(page.locator('h1')).toContainText('find the file');
  for (const link of await page.getByRole('link', { name: /Download/ }).all()) {
    await expect(link).toHaveAttribute('href', 'https://github.com/Totenem/Providence/releases/latest');
  }
  await page.getByRole('button', { name: 'Text inside a scan' }).click();
  await expect(page.getByRole('heading', { name: 'desk-upgrade.jpg' })).toBeVisible();
  await page.getByRole('button', { name: 'Dark preview' }).click();
  await expect(page.locator('.product-window img')).toHaveAttribute('src', '/images/library-dark.png');
  await page.locator('summary').first().click();
  await expect(page.locator('details').first()).toHaveAttribute('open', '');
  if (testInfo.project.name === 'mobile') {
    await page.getByRole('button', { name: 'Menu', exact: true }).click();
    await expect(page.getByRole('navigation')).toBeVisible();
    await page.getByRole('navigation').getByRole('link', { name: 'FAQ', exact: true }).click();
    await expect(page.getByRole('navigation')).not.toBeVisible();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator('img').evaluateAll(images => images.every(image => (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
  await page.screenshot({ path: `test-results/${testInfo.project.name}.png`, fullPage: true });
  await page.getByRole('link', { name: 'Privacy', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your files stay local.' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('local SEO is honest and pages include structured metadata', async ({ request }) => {
  const home = await request.get('/');
  const html = await home.text();
  expect(html).toContain('application/ld+json');
  expect(html).toContain('SoftwareApplication');
  expect(html).toContain('noindex');
  expect(html).not.toContain('rel="canonical"');
  expect(await (await request.get('/robots.txt')).text()).toContain('Disallow: /');
  expect((await request.get('/privacy')).status()).toBe(200);
  expect((await request.get('/not-a-page')).status()).toBe(404);
});
