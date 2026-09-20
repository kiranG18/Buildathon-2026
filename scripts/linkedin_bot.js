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

// Ensure note is within LinkedIn's 200 char limit
const cleanNote = noteText.length > 200 ? noteText.slice(0, 197) + '...' : noteText;

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
      const topSection = document.querySelector('main section:first-of-type, main div.ph5') || document.body;
      const topText = topSection.innerText || '';

      const heroElements = Array.from(topSection.querySelectorAll('a, button')).map(el => ({
        tag: el.tagName,
        text: (el.innerText || '').trim(),
        aria: (el.getAttribute('aria-label') || '').trim(),
        href: el.getAttribute('href') || ''
      }));

      // Strictly check the hero card for 1st degree badge
      const isFirstDegree = topText.includes('· 1st') || topText.includes('1st degree');
      const isPending = heroElements.some(b => b.text === 'Pending' || b.aria.includes('Pending'));
      const hasConnect = heroElements.some(b => b.text === 'Connect' || (b.aria.includes('Invite') && b.aria.includes('to connect')));
      const hasMessage = heroElements.some(b => b.text === 'Message' && b.aria !== 'Message with Premium');

      return { isFirstDegree, isPending, hasConnect, hasMessage };
    });

    console.log(`[LinkedIn Bot] Profile state: 1st Degree=${profileState.isFirstDegree}, Pending=${profileState.isPending}, Has Connect=${profileState.hasConnect}, Has Message=${profileState.hasMessage}`);

    // Helper to get active root (light DOM or Shadow DOM)
    const getRoot = () => {
      const host = document.querySelector('div.theme--light');
      return (host && host.shadowRoot) ? host.shadowRoot : document;
    };

    // CASE 1: Already pending
    if (profileState.isPending) {
      console.log('[LinkedIn Bot] An invitation to this profile is already pending. No action needed.');
      console.log(JSON.stringify({
        status: 'skipped',
        reason: 'already_pending',
        profile: profileUrl,
        timestamp: new Date().toISOString()
      }));
      return;
    }

    // CASE 2: Already 1st-degree connection -> Send direct message!
    if (profileState.isFirstDegree && profileState.hasMessage && !profileState.hasConnect) {
      console.log('[LinkedIn Bot] Target is a 1st-degree connection. Opening message thread...');

      // Find Message button in hero section
      const messageClicked = await page.evaluate(() => {
        const topSection = document.querySelector('main section:first-of-type, main div.ph5') || document.body;
        const msgBtn = Array.from(topSection.querySelectorAll('a, button')).find(el => {
          const text = (el.innerText || '').trim();
          const aria = (el.getAttribute('aria-label') || '').trim();
          return text === 'Message' && aria !== 'Message with Premium';
        });
        if (msgBtn) {
          msgBtn.click();
          return true;
        }
        return false;
      });

      if (!messageClicked) {
        throw new Error('MESSAGE_BUTTON_NOT_FOUND: Could not click hero Message button');
      }

      console.log('[LinkedIn Bot] Clicked Message button. Waiting for chat dock / modal...');
      await sleep(3000);

      // Dismiss upsell modal if shown
      await page.evaluate(() => {
        const host = document.querySelector('div.theme--light');
        const root = (host && host.shadowRoot) ? host.shadowRoot : document;
        const closeBtn = root.querySelector('button[aria-label="Dismiss"], button[aria-label="Close"], button.artdeco-modal__dismiss');
        if (closeBtn) closeBtn.click();
      });

      // Find chat text area (checking both light DOM and shadow DOM)
      const chatInputFound = await page.evaluate((text) => {
        const host = document.querySelector('div.theme--light');
        const root = (host && host.shadowRoot) ? host.shadowRoot : document;
        const input = root.querySelector('div[role="textbox"][contenteditable="true"], .msg-form__contenteditable');
        if (input) {
          input.focus();
          document.execCommand('insertText', false, text);
          return true;
        }
        return false;
      }, cleanNote);

      if (!chatInputFound) {
        await page.screenshot({ path: 'linkedin_chat_dock_missing.png' });
        throw new Error('CHAT_INPUT_NOT_FOUND: Could not find chat input area in messaging dock');
      }

      await sleep(1000);

      // Click Send in chat dock
      const sent = await page.evaluate(() => {
        const host = document.querySelector('div.theme--light');
        const root = (host && host.shadowRoot) ? host.shadowRoot : document;
        const sendBtn = root.querySelector('button.msg-form__send-button, form.msg-form button[type="submit"]');
        if (sendBtn) {
          sendBtn.click();
          return true;
        }
        return false;
      });

      if (!sent) {
        await page.screenshot({ path: 'linkedin_chat_send_missing.png' });
        throw new Error('CHAT_SEND_NOT_FOUND: Could not click Send button in chat dock');
      }

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

    // CASE 3: 2nd or 3rd-degree connection (or Connect available) -> Send connection invite with note!
    console.log('[LinkedIn Bot] Searching for Connect button on profile header...');

    let connectClicked = await page.evaluate(() => {
      const topSection = document.querySelector('main section:first-of-type, main div.ph5') || document.body;
      const elements = Array.from(topSection.querySelectorAll('a, button'));
      const connectEl = elements.find(el => {
        const text = (el.innerText || '').trim();
        const aria = (el.getAttribute('aria-label') || '').trim();
        return text === 'Connect' || (aria.includes('Invite') && aria.includes('to connect'));
      });
      if (connectEl) {
        connectEl.click();
        return true;
      }
      return false;
    });

    // Check inside "More actions" in the hero card if not found directly
    if (!connectClicked) {
      console.log('[LinkedIn Bot] Direct Connect button not in hero; checking hero "More" dropdown...');
      const moreOpened = await page.evaluate(() => {
        const topSection = document.querySelector('main section:first-of-type, main div.ph5') || document.body;
        const buttons = Array.from(topSection.querySelectorAll('button'));
        const moreBtn = buttons.find(b => {
          const aria = (b.getAttribute('aria-label') || '').trim();
          const text = (b.innerText || '').trim();
          return aria.includes('More') || text === 'More';
        });
        if (moreBtn) {
          moreBtn.click();
          return true;
        }
        return false;
      });

      if (moreOpened) {
        await sleep(1200);
        connectClicked = await page.evaluate(() => {
          const dropdownItems = Array.from(document.querySelectorAll('div[role="menu"] div, div[role="menu"] span, .artdeco-dropdown__content span'));
          const item = dropdownItems.find(el => (el.innerText || '').trim() === 'Connect');
          if (item) {
            item.click();
            return true;
          }
          return false;
        });
      }
    }

    if (!connectClicked) {
      console.warn('[LinkedIn Bot] Connect button not found on profile. Profile may be Follow-only, pending, or already connected.');
      await page.screenshot({ path: 'linkedin_no_connect_btn.png' });
      throw new Error('CONNECT_NOT_FOUND: Could not find Connect button on profile header');
    }

    console.log('[LinkedIn Bot] Found and clicked Connect button. Waiting for modal...');
    await sleep(2500);

    // Look for "Add a note" button in invitation modal (checking Shadow DOM first, then light DOM)
    console.log('[LinkedIn Bot] Looking for "Add a note" button in modal (piercing Shadow DOM)...');
    const addNoteClicked = await page.evaluate(() => {
      const host = document.querySelector('div.theme--light');
      const root = (host && host.shadowRoot) ? host.shadowRoot : document;
      const buttons = Array.from(root.querySelectorAll('button'));
      const addNoteBtn = buttons.find(b => (b.innerText || '').trim() === 'Add a note');
      if (addNoteBtn) {
        addNoteBtn.click();
        return true;
      }
      return false;
    });

    if (addNoteClicked && cleanNote) {
      console.log('[LinkedIn Bot] Clicked "Add a note". Waiting for textarea...');
      await sleep(1500);

      console.log(`[LinkedIn Bot] Typing personalized note (${cleanNote.length} chars)...`);
      const noteTyped = await page.evaluate((text) => {
        const host = document.querySelector('div.theme--light');
        const root = (host && host.shadowRoot) ? host.shadowRoot : document;
        const ta = root.querySelector('textarea#custom-message, textarea[name="message"], textarea');
        if (ta) {
          ta.focus();
          ta.value = text;
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          ta.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }
        return false;
      }, cleanNote);

      if (!noteTyped) {
        console.warn('[LinkedIn Bot] Could not find note textarea in modal, proceeding to Send.');
      } else {
        await sleep(1000);
      }
    }

    // Click "Send" / "Send invitation" in invitation modal
    console.log('[LinkedIn Bot] Looking for Send button in modal (piercing Shadow DOM)...');
    const sendClicked = await page.evaluate(() => {
      const host = document.querySelector('div.theme--light');
      const root = (host && host.shadowRoot) ? host.shadowRoot : document;
      const buttons = Array.from(root.querySelectorAll('button'));
      const sendBtn = buttons.find(b => {
        const t = (b.innerText || '').trim();
        const a = (b.getAttribute('aria-label') || '').trim();
        return t === 'Send' || a === 'Send invitation' || t === 'Send invitation' || a.includes('Send invitation');
      });
      if (sendBtn && !sendBtn.disabled && !sendBtn.classList.contains('artdeco-button--disabled')) {
        sendBtn.click();
        return true;
      }
      return false;
    });

    if (!sendClicked) {
      await page.screenshot({ path: 'linkedin_no_send_btn.png' });
      throw new Error('SEND_NOT_FOUND: Send button not found or disabled in modal');
    }

    console.log('[LinkedIn Bot] Clicked Send invitation. Waiting for confirmation...');
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
