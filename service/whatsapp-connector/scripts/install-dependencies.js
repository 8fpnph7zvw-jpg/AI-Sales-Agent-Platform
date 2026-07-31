const { chmodSync } = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const binDirectory = path.join(__dirname, 'install-bin');
if (process.platform !== 'win32') {
  chmodSync(path.join(binDirectory, 'is-ci'), 0o755);
}

const npmExecutable = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const npmArguments = ['ci'];
if (process.argv.includes('--production')) npmArguments.push('--omit=dev');

const result = spawnSync(npmExecutable, npmArguments, {
  cwd: path.resolve(__dirname, '..'),
  env: {
    ...process.env,
    CI: 'true',
    HUSKY: '0',
    PUPPETEER_SKIP_DOWNLOAD: process.env.PUPPETEER_SKIP_DOWNLOAD || 'true',
    PATH: `${binDirectory}${path.delimiter}${process.env.PATH || ''}`,
  },
  shell: process.platform === 'win32',
  stdio: 'inherit',
});

if (result.error) throw result.error;
process.exit(result.status ?? 1);
