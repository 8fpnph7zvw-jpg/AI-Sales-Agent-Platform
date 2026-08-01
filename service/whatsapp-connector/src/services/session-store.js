const fs = require('node:fs');
const path = require('node:path');

const SESSION_DIRECTORY_PATTERN = /^session-([A-Za-z0-9_-]{1,64})$/;
const CHROMIUM_PROFILE_LOCKS = ['SingletonLock', 'SingletonCookie', 'SingletonSocket'];

function sessionProfilePath(sessionsPath, sessionId) {
  return path.join(sessionsPath, `session-${sessionId}`);
}

function profileLockDetails(profilePath) {
  const locks = [];
  for (const name of CHROMIUM_PROFILE_LOCKS) {
    const lockPath = path.join(profilePath, name);
    try {
      const stat = fs.lstatSync(lockPath);
      locks.push({
        name,
        type: stat.isSymbolicLink() ? 'symlink' : stat.isDirectory() ? 'directory' : 'file',
        target: stat.isSymbolicLink() ? fs.readlinkSync(lockPath) : null,
      });
    } catch (error) {
      if (error.code !== 'ENOENT') {
        locks.push({ name, type: 'unreadable', target: null, error: error.message });
      }
    }
  }
  return locks;
}

function inspectStoredSessions(sessionsPath, defaultSessionId) {
  fs.mkdirSync(sessionsPath, { recursive: true });
  const sessions = [];
  for (const directory of fs.readdirSync(sessionsPath, { withFileTypes: true })) {
    if (!directory.isDirectory()) continue;
    const match = SESSION_DIRECTORY_PATTERN.exec(directory.name);
    if (!match) continue;
    const sessionId = match[1];
    const profilePath = path.join(sessionsPath, directory.name);
    const locks = profileLockDetails(profilePath);
    const stat = fs.statSync(profilePath);
    sessions.push({
      sessionId,
      profilePath,
      status: locks.length ? 'profile_locked' : 'stored',
      isDefaultSession: sessionId === defaultSessionId,
      lastModifiedAt: stat.mtime.toISOString(),
      locks,
    });
  }
  sessions.sort((left, right) => left.sessionId.localeCompare(right.sessionId));
  return sessions;
}

async function waitForProfileUnlock(profilePath, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let locks = profileLockDetails(profilePath);
  while (locks.length && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 100));
    locks = profileLockDetails(profilePath);
  }
  return locks;
}

module.exports = {
  inspectStoredSessions,
  profileLockDetails,
  sessionProfilePath,
  waitForProfileUnlock,
};
