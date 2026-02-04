import { describe, it, expect } from 'vitest';
import { extractKeywords } from '../../src/lib/keywords';

describe('keywords extraction', () => {
  it('should extract top words from text', () => {
    const text = 'این تست تست تست یک مقاله نمونه است؛ تست برای استخراج کلیدواژه';
    const kws = extractKeywords(text, 3);
    expect(kws.length).toBeGreaterThanOrEqual(1);
  });
});