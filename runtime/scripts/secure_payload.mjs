/**
 * Zero-dependency authenticated encryption for a GitHub Pages OBS feed.
 * AES-256-GCM with a random nonce, PBKDF2-SHA256 (210k), and a repo secret.
 * Public Pages bundle contains only encrypted headlines, never plaintext JSON.
 * Usage: node runtime/scripts/secure_payload.mjs restore|publish
 */
import { readFileSync, writeFileSync, mkdirSync, rmSync, existsSync, copyFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes, pbkdf2Sync, createCipheriv, createDecipheriv } from 'node:crypto';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const secret = process.env.VIEW_PASSPHRASE || '';
if (!process.env.VIEW_LABEL || process.env.VIEW_LABEL.trim().length < 2) {
  console.error('Missing VIEW_LABEL.'); process.exit(1);
}
if (secret.length < 32) {
  console.error('Missing VIEW_PASSPHRASE (minimum 32 characters). Deployment blocked.');
  process.exit(1);
}
const ENCRYPTED = join(root, 'data', 'payload.enc.json');
const PRIVATE = join(root, 'private', 'payload.json');
const DEPLOY = join(root, '_deploy');
const b64 = buf => Buffer.from(buf).toString('base64');
const un64 = str => Buffer.from(str, 'base64');
const derive = salt => pbkdf2Sync(secret, salt, 210_000, 32, 'sha256');

function encrypt(plaintext) {
  const salt = randomBytes(16), iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', derive(salt), iv);
  const bytes = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final(), cipher.getAuthTag()]);
  return JSON.stringify({v:1,salt:b64(salt),iv:b64(iv),ct:b64(bytes)}) + '\n';
}
function decrypt(text) {
  const e = JSON.parse(text);
  if (e.v !== 1 || !e.salt || !e.iv || !e.ct) throw new Error('Missing encrypted feed fields');
  const raw = un64(e.ct), iv = un64(e.iv);
  if (raw.length < 16 || iv.length !== 12) throw new Error('Invalid cipher');
  const decipher = createDecipheriv('aes-256-gcm', derive(un64(e.salt)), iv);
  decipher.setAuthTag(raw.subarray(raw.length - 16));
  return Buffer.concat([decipher.update(raw.subarray(0, raw.length - 16)), decipher.final()]).toString('utf8');
}

const command = process.argv[2];
if (command === 'restore') {
  mkdirSync(dirname(PRIVATE), {recursive:true});
  const plain = existsSync(ENCRYPTED) ? decrypt(readFileSync(ENCRYPTED, 'utf8')) : JSON.stringify({items:[]});
  const data = JSON.parse(plain);
  if (!Array.isArray(data.items)) throw new Error('Invalid prior feed');
  writeFileSync(PRIVATE, JSON.stringify({
    items:data.items,
    history:Array.isArray(data.history)?data.history:[],
    delivery_log:Array.isArray(data.delivery_log)?data.delivery_log:[]
  }) + '\n');
  console.log('Private state restored.');
} else if (command === 'publish') {
  if (!existsSync(PRIVATE)) throw new Error('Run restore/collect first');
  const current = JSON.parse(readFileSync(PRIVATE, 'utf8'));
  if (!Array.isArray(current.items)) throw new Error('Invalid current feed');
  const safe = JSON.stringify({
    label:process.env.VIEW_LABEL || '',
    items:current.items,
    history:Array.isArray(current.history)?current.history:[],
    delivery_log:Array.isArray(current.delivery_log)?current.delivery_log:[]
  });
  let unchanged = false;
  if (existsSync(ENCRYPTED)) {
    // Fails closed on wrong secret and prevents unnecessary commits.
    unchanged = decrypt(readFileSync(ENCRYPTED,'utf8')) === safe;
  }
  if (!unchanged) {
    mkdirSync(dirname(ENCRYPTED), {recursive:true});
    writeFileSync(ENCRYPTED, encrypt(safe));
  }
  rmSync(PRIVATE, {force:true});
  rmSync(DEPLOY, {recursive:true,force:true});
  mkdirSync(join(DEPLOY,'data'), {recursive:true});
  for (const file of ['view.html','view.js','style.css','index.html','history.html','history.js','history.css']) {
    copyFileSync(join(root,'web',file),join(DEPLOY,file));
  }
  copyFileSync(ENCRYPTED,join(DEPLOY,'data','payload.enc.json'));
  writeFileSync(join(DEPLOY,'robots.txt'),'User-agent: *\nDisallow: /\n');
  console.log(`Encrypted deployment ready. Feed updated: ${!unchanged}`);
} else {
  console.error('Usage: node private_feed.mjs restore|publish');
  process.exit(2);
}
