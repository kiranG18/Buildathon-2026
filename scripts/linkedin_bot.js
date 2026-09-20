import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

const sleep = ms => new Promise(r => setTimeout(r, ms));

// Parse CLI arguments: --url <profileUrl> --note <noteText> --cookie <li_at> --headed
const args = process.argv.slice(2);
function getArg(name, def = null) {
  const idx = args.indexOf(name);
  if (idx !== -1 && idx + 1 < args.length) return args[idx + 1];
  return def;
}
const isHeaded = args.includes('--headed') || args.includes('--head');

const profileUrl = getArg('--url');
const noteText = getArg('--note', '');
let liAtCookie = getArg('--cookie');

// If cookie not passed via CLI, try reading from .env in parent or current dir
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

if (!profileUrl) {
  console.error('Usage: node scripts/linkedin_bot.js --url <profile_url> [--note <text>] [--cookie <li_at>] [--headed]');
  process.exit(1);
}

// Ensure note is within LinkedIn's 300 char limit
const cleanNote = noteText.length > 290 ? noteText.slice(0, 287) + '...' : noteText;

console.log(`[LinkedIn Bot] Target profile: ${profileUrl}`);
console.log(`[LinkedIn Bot] Note length: ${cleanNote.length} chars`);
console.log(`[LinkedIn Bot] Headed mode: ${isHeaded}`);
console.log(`[LinkedIn Bot] Cookie configured: ${Boolean(liAtCookie)}`);

async function run() {
  const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  if (!fs.existsSync(chromePath)) {
    throw new Error(`Chrome executable not found at: ${chromePath}`);
  }

  // Dedicated user data directory for the bot
  const userDataDir = path.resolve('./.chrome_linkedin_profile');
  if (!fs.existsSync(userDataDir)) {
    fs.mkdirSync(userDataDir, { recursive: true });
  }

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: !isHeaded,
    userDataDir,
    defaultViewport: { width: 1280, height: 800 },
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-blink-features=AutomationControlled',
      '--disable-notifications'
    ]
  });

  try {
    const page = (await browser.pages())[0] || (await browser.newPage());

    // Stealth: overwrite navigator.webdriver
    await page.evaluateOnNewDocument(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    });

    // Set li_at cookie if provided
    if (liAtCookie) {
      console.log('[LinkedIn Bot] Setting li_at session cookie...');
      await page.setCookie({
        name: 'li_at',
        value: liAtCookie,
        domain: '.www.linkedin.com',
        path: '/',
        httpOnly: true,
        secure: true,
        sameSite: 'None'
      });
    }

    console.log(`[LinkedIn Bot] Navigating to ${profileUrl}...`);
    await page.goto(profileUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await sleep(4000);

    const currentUrl = page.url();
    console.log(`[LinkedIn Bot] Landed at: ${currentUrl}`);

    // Check if auth wall or login screen hit
    if (currentUrl.includes('/login') || currentUrl.includes('/authwall') || currentUrl.includes('/checkpoint')) {
      console.error('[LinkedIn Bot] Encountered LinkedIn login or authwall.');
      console.error('[LinkedIn Bot] To authenticate: Provide a valid LINKEDIN_LI_AT cookie or run with --headed to log in once.');
      await page.screenshot({ path: 'linkedin_auth_required.png' });
      throw new Error('AUTH_REQUIRED: LinkedIn requires login or li_at cookie is missing/expired');
    }

    // Look for Connect button
    console.log('[LinkedIn Bot] Scanning for Connect button on profile...');

    // Method 1: Look for direct Connect button
    let connectBtn = await page.$('button[aria-label*="Invite"][aria-label*="to connect"]');
    
    // Method 2: Check buttons by text content
    if (!connectBtn) {
      const buttons = await page.$$('main button');
      for (const btn of buttons) {
        const text = await page.evaluate(el => el.innerText.trim(), btn);
        if (text === 'Connect') {
          connectBtn = btn;
          break;
        }
      }
    }

    // Method 3: Check inside "More" / "..." button
    if (!connectBtn) {
      console.log('[LinkedIn Bot] Checking More actions dropdown...');
      let moreBtn = await page.$('button[aria-label="More actions"]');
      if (!moreBtn) {
        const buttons = await page.$$('main button');
        for (const btn of buttons) {
          const text = await page.evaluate(el => el.innerText.trim(), btn);
          if (text === 'More') {
            moreBtn = btn;
            break;
          }
        }
      }

      if (moreBtn) {
        await moreBtn.click();
        await sleep(1000);

        // Find Connect inside the opened dropdown
        const dropdownItems = await page.$$('div[role="dialog"] div[role="button"], div[role="menu"] div[role="button"], div[role="dialog"] span, div[role="menu"] span');
        for (const item of dropdownItems) {
          const text = await page.evaluate(el => el.innerText.trim(), item);
          if (text === 'Connect') {
            connectBtn = item;
            break;
          }
        }
      }
    }

    if (!connectBtn) {
      console.warn('[LinkedIn Bot] Connect button not found on profile. Profile might already be connected, pending, or Follow-only.');
      await page.screenshot({ path: 'linkedin_no_connect_btn.png' });
      throw new Error('CONNECT_NOT_FOUND: Could not find Connect button on profile');
    }

    console.log('[LinkedIn Bot] Found Connect button. Clicking...');
    await connectBtn.click();
    await sleep(2000);

    // Look for "Add a note" modal button
    console.log('[LinkedIn Bot] Looking for "Add a note" button in invitation modal...');
    let addNoteBtn = null;
    const modalButtons = await page.$$('div[role="dialog"] button');
    for (const btn of modalButtons) {
      const text = await page.evaluate(el => el.innerText.trim(), btn);
      if (text.includes('Add a note')) {
        addNoteBtn = btn;
        break;
      }
    }

    if (addNoteBtn && cleanNote) {
      console.log('[LinkedIn Bot] Clicking "Add a note"...');
      await addNoteBtn.click();
      await sleep(1000);

      console.log('[LinkedIn Bot] Typing personalized note...');
      const textarea = await page.$('textarea[name="message"], textarea#custom-message');
      if (textarea) {
        await textarea.type(cleanNote, { delay: 35 });
        await sleep(800);
      }
    }

    // Now find and click "Send"
    console.log('[LinkedIn Bot] Looking for Send button in modal...');
    let sendBtn = null;
    const sendButtons = await page.$$('div[role="dialog"] button');
    for (const btn of sendButtons) {
      const label = await page.evaluate(el => (el.getAttribute('aria-label') || el.innerText || '').trim(), btn);
      if (label.includes('Send') || label.includes('Send invitation')) {
        sendBtn = btn;
        break;
      }
    }

    if (!sendBtn) {
      await page.screenshot({ path: 'linkedin_no_send_btn.png' });
      throw new Error('SEND_NOT_FOUND: Send button not found in modal');
    }

    console.log('[LinkedIn Bot] Clicking Send invitation...');
    await sendBtn.click();
    await sleep(2500);

    console.log('[LinkedIn Bot] SUCCESS! Connection invitation sent.');
    await page.screenshot({ path: 'linkedin_success.png' });

    console.log(JSON.stringify({
      status: 'success',
      profile: profileUrl,
      note: cleanNote,
      timestamp: new Date().toISOString()
    }));
  } finally {
    if (!isHeaded) {
      await browser.close();
    }
  }
}

run().catch(err => {
  console.error('[LinkedIn Bot] FAILED:', err.message);
  process.exit(1);
});
