import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

// Finds real employees of a real company via LinkedIn's people search, using the same logged-in
// browser session as scripts/linkedin_bot.js (rep's own account, li_at cookie). This scrapes
// LinkedIn, which is against its terms of use - see docs/report/report.md section 6 for the
// tradeoff already accepted for the sending side; this extends the same accepted risk to search.

const sleep = ms => new Promise(r => setTimeout(r, ms));

const args = process.argv.slice(2);
function getArg(name, def = null) {
  const idx = args.indexOf(name);
  if (idx !== -1 && idx + 1 < args.length) return args[idx + 1];
  return def;
}
const isHeaded = args.includes('--headed') || args.includes('--head');

const company = getArg('--company');
const domain = getArg('--domain', '');
const titlesArg = getArg('--titles', '');
const titles = titlesArg ? titlesArg.split(',').map(t => t.trim()).filter(Boolean) : [];
const limit = Math.max(1, Math.min(parseInt(getArg('--limit', '5'), 10) || 5, 10));
let liAtCookie = getArg('--cookie');

// Optional: push results straight into a live (or local) Cadence deployment instead of just printing them.
const pushTo = getArg('--push-to', '');       // e.g. https://buildathon-2026-production.up.railway.app
const campaignId = getArg('--campaign', '');
let secret = getArg('--secret');

if (!liAtCookie) {
  for (const envPath of ['.env', '../.env', '../../.env']) {
    try {
      if (fs.existsSync(envPath)) {
        const envContent = fs.readFileSync(envPath, 'utf8');
        const match = envContent.match(/LINKEDIN_LI_AT=([^\r\n]+)/);
        if (match && match[1].trim()) {
          liAtCookie = match[1].trim();
          break;
        }
      }
    } catch (e) {}
  }
}

if (!secret && pushTo) {
  for (const envPath of ['.env', '../.env', '../../.env']) {
    try {
      if (fs.existsSync(envPath)) {
        const m = fs.readFileSync(envPath, 'utf8').match(/WEBHOOK_SHARED_SECRET=([^\r\n]+)/);
        if (m && m[1].trim()) { secret = m[1].trim(); break; }
      }
    } catch (e) {}
  }
}

if (!company) {
  console.error('Usage: node scripts/linkedin_find_employees.js --company <name> [--domain example.com] [--titles "CTO,VP Engineering"]');
  console.error('       [--limit 5] [--cookie <li_at>] [--headed] [--push-to <api base url> --campaign <id> [--secret <WEBHOOK_SHARED_SECRET>]]');
  console.error('No valid LinkedIn session yet? Just run it - a real Chrome window opens for you to sign in, then the search continues automatically.');
  process.exit(1);
}
if (pushTo && !campaignId) {
  console.error('--push-to requires --campaign <id>');
  process.exit(1);
}

console.log(`[LinkedIn Find] Company: ${company}${domain ? ` (${domain})` : ''}`);
console.log(`[LinkedIn Find] Titles: ${titles.join(', ') || '(any)'}`);
console.log(`[LinkedIn Find] Limit: ${limit}`);
console.log(`[LinkedIn Find] Cookie configured: ${Boolean(liAtCookie)}`);
console.log(`[LinkedIn Find] Push target: ${pushTo ? `${pushTo} (campaign ${campaignId})` : '(none - printing only)'}`);

function searchUrl() {
  const keywords = encodeURIComponent([company, ...titles].join(' '));
  return `https://www.linkedin.com/search/results/people/?keywords=${keywords}&origin=GLOBAL_SEARCH_HEADER`;
}

function isAuthWall(url) {
  return url.includes('/login') || url.includes('/authwall') || url.includes('/checkpoint');
}

function launch(headed, userDataDir) {
  const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  if (!fs.existsSync(chromePath)) {
    throw new Error(`Chrome executable not found at: ${chromePath}`);
  }
  return puppeteer.launch({
    executablePath: chromePath,
    headless: !headed,
    userDataDir,
    defaultViewport: headed ? null : { width: 1280, height: 800 },
    args: headed
      ? ['--start-maximized', '--disable-notifications']
      : ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled', '--disable-notifications'],
  });
}

function saveCookieToEnv(value) {
  for (const envPath of ['.env', '../.env', '../../.env']) {
    try {
      if (!fs.existsSync(envPath)) continue;
      let content = fs.readFileSync(envPath, 'utf8');
      content = content.includes('LINKEDIN_LI_AT=')
        ? content.replace(/LINKEDIN_LI_AT=[^\r\n]*/, `LINKEDIN_LI_AT=${value}`)
        : content + `\nLINKEDIN_LI_AT=${value}\n`;
      fs.writeFileSync(envPath, content, 'utf8');
      console.log(`[LinkedIn Find] Saved LINKEDIN_LI_AT to ${envPath} for next time.`);
      return;
    } catch (e) {}
  }
}

// No valid session: open a real, visible Chrome window so the user can sign in once, save the
// session, and resume automatically - no separate script, no manual restart.
async function loginInteractively(userDataDir) {
  console.log('====================================================');
  console.log(' No LinkedIn session found (or it expired).');
  console.log(' Opening a real Chrome window - please sign in to LinkedIn there.');
  console.log(' This script waits, then continues the search automatically once you are in.');
  console.log('====================================================');

  const browser = await launch(true, userDataDir);
  const page = (await browser.pages())[0] || (await browser.newPage());
  await page.goto('https://www.linkedin.com/login', { waitUntil: 'domcontentloaded' });

  let loggedIn = false;
  for (let attempts = 0; attempts < 120 && !loggedIn; attempts++) { // up to 4 minutes
    await sleep(2000);
    const url = page.url();
    if (url.includes('/feed') || url.includes('/mynetwork') || url.includes('/in/')) loggedIn = true;
  }
  if (!loggedIn) {
    await browser.close();
    throw new Error('LOGIN_TIMEOUT: sign-in was not completed within 4 minutes');
  }

  const cookies = await page.cookies('https://www.linkedin.com');
  const liAt = cookies.find(c => c.name === 'li_at');
  if (liAt) saveCookieToEnv(liAt.value);
  console.log('[LinkedIn Find] Signed in. Continuing the search in this window...');
  return { browser, page, headed: true };
}

async function run() {
  const userDataDir = path.resolve('./.chrome_linkedin_profile');
  if (!fs.existsSync(userDataDir)) {
    fs.mkdirSync(userDataDir, { recursive: true });
  }

  let browser = await launch(isHeaded, userDataDir);
  let headed = isHeaded;

  try {
    let page = (await browser.pages())[0] || (await browser.newPage());

    await page.evaluateOnNewDocument(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    });

    if (liAtCookie) {
      console.log('[LinkedIn Find] Setting li_at session cookie...');
      await page.setCookie({
        name: 'li_at',
        value: liAtCookie,
        domain: '.www.linkedin.com',
        path: '/',
        httpOnly: true,
        secure: true,
        sameSite: 'None',
      });
    }

    const url = searchUrl();
    console.log(`[LinkedIn Find] Navigating to ${url}...`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await sleep(3500);

    if (isAuthWall(page.url())) {
      console.log('[LinkedIn Find] Hit an auth wall / expired session - falling back to interactive sign-in.');
      await browser.close();
      const signedIn = await loginInteractively(userDataDir);
      browser = signedIn.browser;
      page = signedIn.page;
      headed = true;
      console.log(`[LinkedIn Find] Re-navigating to ${url}...`);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await sleep(3500);
      if (isAuthWall(page.url())) {
        await page.screenshot({ path: 'linkedin_find_auth_required.png' });
        throw new Error('AUTH_REQUIRED: still on an auth wall after interactive sign-in');
      }
    }

    // Scroll a little so lazy-loaded result cards render.
    await page.evaluate(() => window.scrollBy(0, 800));
    await sleep(1500);

    const results = await page.evaluate((wantCompany, wantLimit) => {
      const cards = Array.from(document.querySelectorAll('li.reusable-search__result-container, div[data-chameleon-result-urn]'));
      const out = [];
      for (const card of cards) {
        const link = card.querySelector('a.app-aware-link[href*="/in/"]');
        if (!link) continue;
        const href = (link.getAttribute('href') || '').split('?')[0];
        const nameEl = card.querySelector('span[aria-hidden="true"]');
        const name = (nameEl ? nameEl.innerText : link.innerText || '').trim();
        const subtitleEl = card.querySelector('.entity-result__primary-subtitle, div.t-14.t-black.t-normal');
        const subtitle = (subtitleEl ? subtitleEl.innerText : '').trim();
        if (!name || !href) continue;
        out.push({ name, title: subtitle, profile_url: href, company: wantCompany });
        if (out.length >= wantLimit) break;
      }
      return out;
    }, company, limit);

    console.log(`[LinkedIn Find] Parsed ${results.length} result card(s).`);

    if (pushTo && results.length) {
      console.log(`[LinkedIn Find] Pushing ${results.length} result(s) to ${pushTo}/tools/linkedin-import...`);
      const resp = await fetch(`${pushTo.replace(/\/$/, '')}/tools/linkedin-import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(secret ? { 'X-Cadence-Secret': secret } : {}) },
        body: JSON.stringify({ campaign_id: campaignId, company, domain, people: results }),
      });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        console.error(`[LinkedIn Find] Push failed: HTTP ${resp.status}`, JSON.stringify(body));
        console.log(JSON.stringify({ status: 'scraped_but_not_pushed', company, results }));
        process.exitCode = 1;
      } else {
        console.log('[LinkedIn Find] Pushed. Server response:', JSON.stringify(body));
        console.log(JSON.stringify({ status: 'success', company, pushed: true, server: body }));
      }
    } else {
      console.log(JSON.stringify({ status: 'success', company, pushed: false, results }));
    }
  } finally {
    if (!headed) {
      await browser.close();
    }
  }
}

run().catch(err => {
  console.error('[LinkedIn Find] FAILED:', err.message);
  process.exit(1);
});
