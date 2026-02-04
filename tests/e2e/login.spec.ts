import { test, expect } from '@playwright/test';

test('landing and navigation', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await expect(page).toHaveTitle(/Accountinox/);
  await page.click('text=فروشگاه');
  await expect(page).toHaveURL(/\/shop/);
});