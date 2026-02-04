export function extractKeywords(text: string, topN = 10) {
  // simple TF algorithm (not full TF-IDF for standalone simplicity)
  const words = text
    .toLowerCase()
    .replace(/[^آ-یa-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .filter((w) => w.length > 2);

  const freq: Record<string, number> = {};
  for (const w of words) freq[w] = (freq[w] || 0) + 1;

  return Object.entries(freq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map((v) => v[0]);
}
