// One-time, interactive login for the bot Steam account. Run it yourself in a terminal:
//   cd ingest && npm run login
// You type the account name and password here; Steam Guard is prompted here too.
// Only the resulting refresh token is saved (~/.config/onefix/bot-refresh-token, mode 600).
// The password is never written anywhere.
import { createInterface } from 'node:readline/promises';
import { stdin, stdout } from 'node:process';

import SteamUser from 'steam-user';

import { saveToken, TOKEN } from './lib/config.js';

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

const accountName = await ask('Bot account name: ');
const password = await ask('Bot account password (hidden): ', { hidden: true });

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
user.on('licenses', () => {
  if (user.ownsApp(730)) {
    console.log('Bot account has Counter-Strike 2. Done.');
    user.logOff();
    setTimeout(() => process.exit(0), 1000);
    return;
  }
  console.log('Adding the free Counter-Strike 2 licence to the bot account...');
  user.requestFreeLicense([730], (err) => {
    if (err) console.error(`Could not add CS2: ${err.message}. Add it in the Steam client instead.`);
    else console.log('Added Counter-Strike 2. Done.');
    user.logOff();
    setTimeout(() => process.exit(err ? 1 : 0), 1000);
  });
});

user.logOn({ accountName, password, machineName: 'onefix-ingest' });
