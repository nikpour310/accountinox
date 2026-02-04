import { describe, it, expect } from 'vitest';
import { encryptText, decryptText } from '../../src/lib/crypto';

describe('crypto encrypt/decrypt', () => {
  it('should encrypt and decrypt text correctly', () => {
    process.env.AES_SECRET = 'base64:' + Buffer.from('01234567890123456789012345678901').toString('base64');
    const plain = 'secret-credential-123';
    const enc = encryptText(plain);
    const dec = decryptText(enc);
    expect(dec).toBe(plain);
  });
});