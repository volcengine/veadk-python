// Static export build for GitHub Pages.
//
// `output: 'export'` cannot include the POST /api/chat route (it is dynamic and
// only used in local dev — the production Ask-AI endpoint is external, set via
// NEXT_PUBLIC_AI_CHAT_URL). So we temporarily move the route out, run the
// export build, restore it, and write a `.nojekyll` file so GitHub Pages serves
// the `_next/` directory.
//
// Usage: NEXT_PUBLIC_BASE_PATH=/veadk-python node scripts/build-static.mjs

import { execSync } from 'node:child_process';
import { existsSync, renameSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const chatDir = join(root, 'app/api/chat');
const backupDir = join(root, '.chat-route-bak');

function moveChatAway() {
  if (existsSync(chatDir)) {
    renameSync(chatDir, backupDir);
    console.log('[build:static] moved app/api/chat aside (incompatible with output: export)');
  }
}

function restoreChat() {
  if (existsSync(backupDir)) {
    renameSync(backupDir, chatDir);
    console.log('[build:static] restored app/api/chat');
  }
}

process.on('exit', restoreChat);
process.on('SIGINT', () => {
  restoreChat();
  process.exit(1);
});

try {
  moveChatAway();
  execSync('next build', {
    stdio: 'inherit',
    env: { ...process.env, NEXT_STATIC_EXPORT: '1' },
  });
} finally {
  restoreChat();
}

// GitHub Pages: disable Jekyll so the `_next/` folder is served.
const outDir = join(root, 'out');
if (existsSync(outDir)) {
  writeFileSync(join(outDir, '.nojekyll'), '');
  console.log('[build:static] wrote out/.nojekyll');
} else {
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, '.nojekyll'), '');
}
