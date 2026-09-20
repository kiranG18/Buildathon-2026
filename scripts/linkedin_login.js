import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function loginHelper() {
  const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  if (!fs.existsSync(chromePath)) {
    console.error(`Chrome executable not found at: ${chromePath}`);
    process.exit(1);
  }

  const userDataDir = path.resolve('./.chrome_linkedin_profile');
  if (!fs.existsSync(userDataDir)) {
    fs.mkdirSync(userDataDir, { recursive: true });
  }

  console.log('====================================================');
  console.log(' Opening Chrome for one-time LinkedIn sign-in...');
  console.log(' Please sign in to your LinkedIn account in the browser window.');
  console.log(' Once you reach your LinkedIn feed, this script will automatically');
  console.log(' save your session and extract your li_at cookie.');
  console.log('====================================================');

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: false,
    userDataDir,
    defaultViewport: null,
    args: ['--start-maximized', '--disable-notifications']
  });

  const page = (await browser.pages())[0] || (await browser.newPage());
  await page.goto('https://www.linkedin.com/login', { waitUntil: 'domcontentloaded' });

  // Poll until user logs in and lands on LinkedIn feed or profile
  let loggedIn = false;
  let attempts = 0;
  while (!loggedIn && attempts < 120) { // 4 minutes max
    await sleep(2000);
    attempts++;
    const url = page.url();
    if (url.includes('/feed') || url.includes('/mynetwork') || url.includes('/in/')) {
      loggedIn = true;
      break;
    }
  }

  if (!loggedIn) {
    console.log('\n[Timeout] Sign-in was not completed within 4 minutes.');
    await browser.close();
    process.exit(1);
  }

  console.log('\n====================================================');
  console.log(' SUCCESS! Successfully logged in to LinkedIn!');
  
  // Extract li_at cookie
  const cookies = await page.cookies('https://www.linkedin.com');
  const liAt = cookies.find(c => c.name === 'li_at');
  if (liAt) {
    console.log(` Extracted li_at cookie: ${liAt.value.slice(0, 15)}...`);
    console.log(' Saving LINKEDIN_LI_AT to .env...');
    
    let envContent = '';
    if (fs.existsSync('.env')) {
      envContent = fs.readFileSync('.env', 'utf8');
      if (envContent.includes('LINKEDIN_LI_AT=')) {
        envContent = envContent.replace(/LINKEDIN_LI_AT=[^\r\n]*/, `LINKEDIN_LI_AT=${liAt.value}`);
      } else {
        envContent += `\nLINKEDIN_LI_AT=${liAt.value}\n`;
      }
    } else {
      envContent = `LINKEDIN_LI_AT=${liAt.value}\n`;
    }
    fs.writeFileSync('.env', envContent, 'utf8');
    console.log(' Session profile saved to ./.chrome_linkedin_profile');
    console.log(' Automated LinkedIn sends are now ready to execute!');
  } else {
    console.log(' Browser profile session saved to ./.chrome_linkedin_profile');
  }
  console.log('====================================================\n');

  await sleep(3000);
  await browser.close();
}

loginHelper().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
