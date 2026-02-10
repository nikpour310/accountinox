const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  if (!fs.existsSync('screenshots')) fs.mkdirSync('screenshots');
  const base = 'http://127.0.0.1:8005';
  const pages = [
    '/',
    '/shop/',
    '/shop/cart/',
    '/shop/checkout/',
    '/blog/',
    '/accounts/login/',
    '/accounts/profile/',
    '/accounts/dashboard/',
    '/support/',
    '/support/chat/',
    '/support/operator/'
  ];

  const viewports = [
    { name: 'mobile', width: 375, height: 667 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'desktop', width: 1366, height: 768 }
  ];

  const browser = await chromium.launch();
  const context = await browser.newContext();

  const report = [];
  for (const p of pages) {
    for (const vp of viewports) {
      const page = await context.newPage();
      await page.setViewportSize({ width: vp.width, height: vp.height });
      const url = base + p;
      try {
        const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
        const status = resp ? resp.status() : 'no-response';
        const safeName = p === '/' ? 'home' : p.replace(/\W+/g, '_').replace(/^_+|_+$/g, '');
        const out = `screenshots/${safeName}_${vp.name}_${vp.width}x${vp.height}.png`;
        await page.screenshot({ path: out, fullPage: true });

        // run visual checks
        const checks = await page.evaluate((vw) => {
          const issues = [];
          // check if CSS applied by looking for a known class
          const hasSection = !!document.querySelector('.section-title');
          if (!hasSection) issues.push('missing .section-title on page');

          // detect horizontal overflow
          const doc = document.documentElement || document.body;
          const overflowX = doc.scrollWidth > vw;
          if (overflowX) issues.push('horizontal-overflow');

          // detect missing hero image by searching for common src
          const missingHero = !!document.querySelector("img[src*='hero-mockup']") === false && !!document.querySelector(".hero") === false;
          if (missingHero) issues.push('possible-missing-hero-image');

          // detect if body has default font-family applied (quick heuristic)
          const bodyStyle = window.getComputedStyle(document.body);
          const font = bodyStyle.getPropertyValue('font-family') || '';
          if (!font.toLowerCase().includes('vazirmatn') && !font.toLowerCase().includes('vazir') ) issues.push('font-not-vazirmatn');

          return { issues, fontFamily: font, width: doc.scrollWidth, height: doc.scrollHeight };
        }, vp.width);

        report.push({ url, status, viewport: vp, screenshot: out, checks });
        console.log(url, status, '->', out, checks.issues.length ? checks.issues : 'OK');
      } catch (err) {
        console.log('ERROR', url, err.toString());
        report.push({ url, error: err.toString() });
      } finally {
        await page.close();
      }
    }
  }

  fs.writeFileSync('screenshots/report.json', JSON.stringify(report, null, 2));

  await browser.close();
})();
