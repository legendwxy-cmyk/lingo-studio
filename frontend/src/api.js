import { audioExtFromMime } from './utils/speech';

async function request(url, options = {}) {
  const res = await fetch(url, { credentials: 'same-origin', ...options });
  if (!res.ok) {
    let message = `请求失败 (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) message = data.detail;
    } catch {
      // ignore json parse failure
    }
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    return res.json();
  }
  return res.text();
}

export const api = {
  health: () => request('/api/health'),

  authStatus: () => request('/api/auth/status'),

  login: (password) =>
    request('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    }),

  logout: () => request('/api/auth/logout', { method: 'POST' }),

  shutdownDesktop: () => request('/api/system/shutdown', { method: 'POST' }),

  listEpisodes: (params = {}) => {
    const sp = new URLSearchParams();
    if (params.q) sp.set('q', params.q);
    if (params.difficulty) sp.set('difficulty', params.difficulty);
    if (params.status) sp.set('status', params.status);
    const qs = sp.toString();
    return request(`/api/episodes${qs ? `?${qs}` : ''}`);
  },

  getEpisode: (id) => request(`/api/episodes/${id}`),

  getEpisodeStatus: (id) => request(`/api/episodes/${id}/status`),

  uploadEpisode: (formData) =>
    request('/api/episodes/upload', {
      method: 'POST',
      body: formData,
    }),

  reprocessEpisode: (id, subtitleFile = null) => {
    const fd = new FormData();
    if (subtitleFile) fd.append('subtitle_file', subtitleFile);
    return request(`/api/episodes/${id}/reprocess`, {
      method: 'POST',
      body: fd,
    });
  },

  patchEpisode: (id, payload) =>
    request(`/api/episodes/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  deleteEpisode: (id) =>
    request(`/api/episodes/${id}`, { method: 'DELETE' }),

  createSubtitle: (episodeId, payload) =>
    request(`/api/episodes/${episodeId}/subtitles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  deleteSubtitle: (subtitleId) =>
    request(`/api/subtitles/${subtitleId}`, { method: 'DELETE' }),

  patchSubtitle: (id, payload) =>
    request(`/api/subtitles/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  toggleSubtitleFavorite: (id) =>
    request(`/api/subtitles/${id}/favorite`, { method: 'POST' }),

  analyzeSubtitle: (id, force = false) =>
    request(`/api/subtitles/${id}/ai-analyze${force ? '?force=true' : ''}`, {
      method: 'POST',
    }),

  createEntry: (payload) =>
    request('/api/entries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  patchEntry: (id, payload) =>
    request(`/api/entries/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  toggleEntryBookmark: (id) =>
    request(`/api/entries/${id}/bookmark`, { method: 'POST' }),

  getEntryOccurrences: (id) => request(`/api/entries/${id}/occurrences`),

  getVocabDeck: () => request('/api/vocab-deck'),

  uploadRecording: (episodeId, subtitleId, blob) => {
    const fd = new FormData();
    const ext = audioExtFromMime(blob?.type);
    fd.append('subtitle_id', String(subtitleId));
    fd.append('audio_file', blob, `shadow_${subtitleId}${ext}`);
    return request(`/api/episodes/${episodeId}/recordings`, {
      method: 'POST',
      body: fd,
    });
  },

  uploadContinuousRecordings: (episodeId, segments, blob) => {
    const fd = new FormData();
    const ext = audioExtFromMime(blob?.type);
    fd.append('segments_json', JSON.stringify(segments));
    fd.append('audio_file', blob, `shadow_continuous_${episodeId}${ext}`);
    return request(`/api/episodes/${episodeId}/recordings/batch`, {
      method: 'POST',
      body: fd,
    });
  },

  deleteRecording: (recordingId) =>
    request(`/api/recordings/${recordingId}`, { method: 'DELETE' }),

  evaluateRetelling: (episodeId, payload) =>
    request(`/api/episodes/${episodeId}/retelling/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  evaluateRetellingAudio: (episodeId, mode, blob) => {
    const fd = new FormData();
    const ext = audioExtFromMime(blob?.type);
    fd.append('mode', mode);
    fd.append('audio_file', blob, `retell${ext}`);
    return request(`/api/episodes/${episodeId}/retelling/audio`, {
      method: 'POST',
      body: fd,
    });
  },

  getSettings: () => request('/api/settings'),

  saveSettings: (payload) =>
    request('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  testLLM: (payload) =>
    request('/api/settings/test-llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
};
