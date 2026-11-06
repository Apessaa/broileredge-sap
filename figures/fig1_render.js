// Render fig1_walkthrough.html to fig1_walkthrough.png at 2x (2000 px wide).
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const W = 1000, H = 1470;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.goto('file://' + path.join(__dirname, 'fig1_walkthrough.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(__dirname, 'fig1_walkthrough.png'), clip: { x: 0, y: 0, width: W, height: H } });
  await browser.close();
  console.log('rendered');
})();
