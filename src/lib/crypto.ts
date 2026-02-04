import crypto from 'crypto';

const AES_SECRET = process.env.AES_SECRET || '';
if (!AES_SECRET) {
  console.warn('AES_SECRET is not set. Encryption will fail.');
}

export function encryptText(plain: string) {
  const key = Buffer.from(AES_SECRET.replace(/^base64:/, ''), 'base64');
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const enc = Buffer.concat([cipher.update(plain, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, enc]).toString('base64');
}

export function decryptText(payload: string) {
  const key = Buffer.from(AES_SECRET.replace(/^base64:/, ''), 'base64');
  const data = Buffer.from(payload, 'base64');
  const iv = data.slice(0, 12);
  const tag = data.slice(12, 28);
  const enc = data.slice(28);
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
  decipher.setAuthTag(tag);
  const dec = Buffer.concat([decipher.update(enc), decipher.final()]);
  return dec.toString('utf8');
}
