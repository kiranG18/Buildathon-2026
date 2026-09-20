import puppeteer from 'puppeteer-core';

async function test() {
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  console.log('Browser launched successfully!');
  const page = await browser.newPage();
  await page.goto('https://httpbin.org/get');
  console.log('Page URL reached:', page.url());
  await browser.close();
}

test().catch(console.error);
