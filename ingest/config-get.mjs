// Print one validated config field (for shell scripts): node config-get.mjs steamid
import { loadConfig } from './lib/config.js';

const field = process.argv[2];
const value = loadConfig()[field];
if (value === undefined || field === 'webApiKey' || field === 'matchAuthCode') {
  console.error(`not a printable config field: ${field}`);
  process.exit(1);
}
console.log(value.replace(/^~(?=\/)/, process.env.HOME));
