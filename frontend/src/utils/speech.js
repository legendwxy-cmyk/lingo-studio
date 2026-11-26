export function stopSpeechSynthesis() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try {
      window.speechSynthesis.cancel();
    } catch {
      // ignore
    }
  }
}

export function speakWord(text, accent = 'US') {
  if (!text || typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return;
  }
  try {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    const targetLang = accent === 'UK' ? 'en-GB' : 'en-US';
    utter.lang = targetLang;
    utter.rate = 0.92;
    const voices = window.speechSynthesis.getVoices() || [];
    const matched =
      voices.find((v) => v.lang.toLowerCase() === targetLang.toLowerCase()) ||
      voices.find((v) => v.lang.toLowerCase().startsWith('en'));
    if (matched) utter.voice = matched;
    window.speechSynthesis.speak(utter);
  } catch {
    // Graceful no-op in environments without speech synthesis
  }
}

export function formatTime(sec) {
  const s = Math.max(0, Number(sec) || 0);
  const m = Math.floor(s / 60);
  const rem = Math.floor(s % 60);
  return `${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
}

export function decodeHtmlEntities(str) {
  if (!str) return '';
  return String(str)
    .replace(/&#x27;|&#39;|&apos;/gi, "'")
    .replace(/&quot;/gi, '"')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&');
}

export function normalizeWord(word) {
  return decodeHtmlEntities(word)
    .replace(/[‘’`´]/g, "'")
    .replace(/[“”]/g, '"')
    .toLowerCase()
    .replace(/[^a-z0-9'\s]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^'+|'+$/g, '');
}

/**
 * LCS word alignment for full-sentence dictation so omitting or inserting 1 word
 * does not cascade mismatches across all subsequent words.
 */
export function alignDictationWords(expectedWords, userWords) {
  const cleanExpected = expectedWords.filter((w) => normalizeWord(w).length > 0);
  const cleanUser = userWords.filter((w) => normalizeWord(w).length > 0);
  const m = cleanExpected.length;
  const n = cleanUser.length;
  const expNorm = cleanExpected.map((w) => normalizeWord(w));
  const usrNorm = cleanUser.map((w) => normalizeWord(w));

  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i -= 1) {
    for (let j = n - 1; j >= 0; j -= 1) {
      if (expNorm[i] && expNorm[i] === usrNorm[j]) {
        dp[i][j] = 1 + dp[i + 1][j + 1];
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const items = [];
  let extraCount = 0;
  let i = 0;
  let j = 0;
  while (i < m) {
    if (j < n && expNorm[i] && expNorm[i] === usrNorm[j]) {
      items.push({ expected: cleanExpected[i], got: cleanUser[j], ok: true });
      i += 1;
      j += 1;
    } else if (j < n && dp[i][j + 1] > dp[i + 1][j]) {
      // User inserted an extra word: mark it without cascading mismatches to subsequent words
      items.push({ expected: '', got: cleanUser[j], ok: false, extra: true });
      extraCount += 1;
      j += 1;
    } else if (j < n && dp[i + 1][j + 1] >= dp[i + 1][j] && dp[i + 1][j + 1] >= dp[i][j + 1]) {
      // Substitution at this position
      items.push({ expected: cleanExpected[i], got: cleanUser[j], ok: false });
      i += 1;
      j += 1;
    } else {
      // Expected word was omitted
      items.push({ expected: cleanExpected[i], got: '', ok: false });
      i += 1;
    }
  }
  while (j < n) {
    items.push({ expected: '', got: cleanUser[j], ok: false, extra: true });
    extraCount += 1;
    j += 1;
  }

  const hits = items.filter((it) => it.ok).length;
  return {
    items,
    accuracy: Math.round((hits / Math.max(1, m + extraCount)) * 100),
  };
}

export function pickRecorderMimeType() {
  if (typeof window === 'undefined' || typeof MediaRecorder === 'undefined') return '';
  if (typeof MediaRecorder.isTypeSupported !== 'function') return '';
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ];
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return '';
}

export function audioExtFromMime(mimeType) {
  const mt = String(mimeType || '').toLowerCase();
  if (mt.includes('mp4') || mt.includes('aac') || mt.includes('m4a')) return '.m4a';
  if (mt.includes('ogg')) return '.ogg';
  if (mt.includes('wav')) return '.wav';
  if (mt.includes('mpeg') || mt.includes('mp3')) return '.mp3';
  return '.webm';
}
