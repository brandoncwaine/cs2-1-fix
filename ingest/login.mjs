// One-time, interactive login for the bot Steam account. Run it yourself in a terminal:
//   cd ingest && npm run login
// You type the account name and password here; Steam Guard is prompted here too.
// Only the resulting refresh token is saved (~/.config/onefix/bot-refresh-token, mode 600).
// The password is never written anywhere.
import { createInterface } from 'node:readline/promises';
import { stdin, stdout } from 'node:process';

import SteamUser from 'steam-user';

import { existsSync } from 'node:fs';

import { loadToken, saveToken, TOKEN } from './lib/config.js';

async function ask(question, { hidden = false } = {}) {
  const rl = createInterface({ input: stdin, output: stdout, terminal: true });
  if (hidden) {
    // Mask typed characters.
    rl._writeToOutput = (s) => rl.output.write(s.startsWith(question) ? s : '*');
  }
  const answer = await rl.question(question);
  rl.close();
  if (hidden) stdout.write('\n');
  return answer.trim();
}

// Reuse a saved session unless --fresh is passed, so re-running never needs the password.
const useSaved = existsSync(TOKEN) && !process.argv.includes('--fresh');
let details;
if (useSaved) {
  console.log(`Using saved bot session (${TOKEN}). Pass --fresh to log in with a password.`);
  details = { refreshToken: loadToken() };
} else {
  const accountName = await ask('Bot account name: ');
  const password = await ask('Bot account password (hidden): ', { hidden: true });
  details = { accountName, password };
}

const user = new SteamUser();
user.on('refreshToken', (token) => {
  saveToken(token);
  console.log(`Saved bot session to ${TOKEN}`);
});
user.on('error', (err) => {
  console.error(`Steam login failed: ${err.message}`);
  process.exit(1);
});
user.on('loggedOn', () => {
  console.log(`Logged on as ${user.steamID.getSteamID64()}.`);
});
user.once('licenses', () => {
  // Request the free CS2 licence unconditionally: if the account already has it, Steam
  // grants nothing. (Checking ownership first needs steam-user's PICS cache.)
  user.requestFreeLicense([730], (err, packageIds, appIds) => {
    if (err) console.error(`Could not add CS2: ${err.message}. Add it in the Steam client instead.`);
    else if (appIds?.length) console.log('Added Counter-Strike 2 to the bot account. Done.');
    else console.log('Bot account already has Counter-Strike 2. Done.');
    user.logOff();
    setTimeout(() => process.exit(err ? 1 : 0), 1000);
  });
});

user.logOn({ ...details, machineName: 'onefix-ingest' });
