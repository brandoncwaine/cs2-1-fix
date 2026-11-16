// Print, as JSON, each player's name, steamid64, downloaded demo files and fetch problems.
// For scripts/sync.sh (parsing and the website). No secrets and no share codes.
import { existsSync } from 'node:fs';

import { loadConfig, loadState } from './lib/config.js';
import { buildManifest } from './lib/core.js';

const config = loadConfig();
const state = loadState(config.players[0]?.steamid);
console.log(JSON.stringify(buildManifest(config, state, existsSync), null, 2));
