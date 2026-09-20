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

    console.log('[LinkedIn Bot] Inspecting profile header actions...');

    // Detect relationship and action buttons strictly within the hero profile section
    const profileState = await page.evaluate(() => {
      // Find elements with Connect or Message in the top section
      const buttons = Array.from(document.querySelectorAll('main div.ph5 button, main div.pvs-profile-actions button, main section:first-of-type button'));
      const links = Array.from(document.querySelectorAll('main div.ph5 a, main div.pvs-profile-actions a, main section:first-of-type a'));

      const isFirstDegree = document.body.innerText.includes('· 1st') || document.body.innerText.includes('1st degree');
      const isPending = buttons.some(b => (b.innerText || '').trim() === 'Pending');
      const hasConnect = buttons.some(b => (b.innerText || '').trim() === 'Connect');
      const hasMessage = links.some(a => (a.innerText || '').trim() === 'Message' && (a.getAttribute('href') || '').includes('messaging'));

      return { isFirstDegree, isPending, hasConnect, hasMessage };
    });

    console.log(`[LinkedIn Bot] Profile state: 1st Degree=${profileState.isFirstDegree}, Pending=${profileState.isPending}, Has Connect=${profileState.hasConnect}, Has Message=${profileState.hasMessage}`);

    // CASE 1: Already pending
    if (profileState.isPending) {
      console.log('[LinkedIn Bot] An invitation to this profile is already pending. No action needed.');
      return;
    }

    // CASE 2: Already 1st-degree connection -> Send direct message!
    if (profileState.isFirstDegree && profileState.hasMessage) {
      console.log('[LinkedIn Bot] Target is already a 1st-degree connection. Opening message thread...');

      // Find the Message button link
      const messageLink = await page.$('a[href*="/messaging/compose/"]');
      if (!messageLink) {
        throw new Error('MESSAGE_LINK_NOT_FOUND: Could not find direct Message link');
      }

      await messageLink.click();
      console.log('[LinkedIn Bot] Clicked Message button. Waiting for chat dock...');
      await sleep(3000);

      // Find chat text area
      const chatInput = await page.$('.msg-form__contenteditable, div[role="textbox"][contenteditable="true"]');
      if (!chatInput) {
        await page.screenshot({ path: 'linkedin_chat_dock_missing.png' });
        throw new Error('CHAT_INPUT_NOT_FOUND: Could not find chat input area in messaging dock');
      }

      console.log('[LinkedIn Bot] Typing direct message into chat dock...');
      await chatInput.click();
      await sleep(500);
      await page.keyboard.type(cleanNote, { delay: 30 });
      await sleep(1000);

      // Click Send button in chat form
      console.log('[LinkedIn Bot] Finding Send button in chat form...');
      const sendChatBtn = await page.$('button.msg-form__send-button, form.msg-form button[type="submit"]');
      if (!sendChatBtn) {
        await page.screenshot({ path: 'linkedin_chat_send_missing.png' });
        throw new Error('CHAT_SEND_NOT_FOUND: Could not find Send button in chat dock');
      }

      await sendChatBtn.click();
      await sleep(2500);

      console.log('[LinkedIn Bot] SUCCESS! Direct LinkedIn message sent to 1st-degree connection.');
      await page.screenshot({ path: 'linkedin_success.png' });
      console.log(JSON.stringify({
        status: 'success',
        type: 'direct_message',
        profile: profileUrl,
        note: cleanNote,
        timestamp: new Date().toISOString()
      }));
      return;
    }

    // CASE 3: 2nd or 3rd-degree connection -> Send connection invite with note!
    console.log('[LinkedIn Bot] Searching for Connect button on profile header...');
    let connectBtn = null;

    // Direct connect button inside profile header
    const headerButtons = await page.$$('main div.ph5 button, main div.pvs-profile-actions button, main section:first-of-type button');
    for (const btn of headerButtons) {
      const text = await page.evaluate(el => el.innerText.trim(), btn);
      if (text === 'Connect') {
        connectBtn = btn;
        break;
      }
    }

    // Check inside "More actions" in the hero card
    if (!connectBtn) {
      console.log('[LinkedIn Bot] Direct Connect button not in hero; checking hero "More" dropdown...');
      let moreBtn = null;
      for (const btn of headerButtons) {
        const text = await page.evaluate(el => (el.getAttribute('aria-label') || el.innerText || '').trim(), btn);
        if (text === 'More' || text.includes('More actions')) {
          moreBtn = btn;
          break;
        }
      }

      if (moreBtn) {
        await moreBtn.click();
        await sleep(1200);

        // Find Connect inside the opened dropdown menu
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
      console.warn('[LinkedIn Bot] Connect button not found on profile. Profile may be Follow-only or already connected.');
      await page.screenshot({ path: 'linkedin_no_connect_btn.png' });
      throw new Error('CONNECT_NOT_FOUND: Could not find Connect button on profile header');
    }

    console.log('[LinkedIn Bot] Found Connect button. Clicking...');
    await connectBtn.click();
    await sleep(2000);

    // Look for "Add a note" button in invitation modal
    console.log('[LinkedIn Bot] Looking for "Add a note" button in modal...');
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

    // Click "Send" in invitation modal
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
      type: 'connection_invitation',
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
