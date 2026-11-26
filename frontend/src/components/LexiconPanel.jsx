import React, { useEffect, useState } from 'react';
import { Eye, EyeOff, Globe2, Play, Search, Star, Volume2 } from 'lucide-react';
import { api } from '../api';
import { formatTime, speakWord } from '../utils/speech';

const CATEGORIES = ['全部', '短语动词', '惯用表达', '搭配', '短语', '单词'];

export default function LexiconPanel({
  episodeId,
  entries,
  activeSubtitle,
  selectedEntryId,
  onSelectEntry,
  onToggleBookmark,
  onJumpToSubtitle,
  onJumpToOccurrence,
}) {
  const [scope, setScope] = useState('all'); // all | sentence
  const [category, setCategory] = useState('全部');
  const [query, setQuery] = useState('');
  const [hideMeaning, setHideMeaning] = useState(false);
  const [crossMap, setCrossMap] = useState({});
  const [loadingCrossId, setLoadingCrossId] = useState(null);

  const loadCrossOccurrences = async (entryId) => {
    if (!entryId || crossMap[entryId]) return;
    setLoadingCrossId(entryId);
    try {
      const res = await api.getEntryOccurrences(entryId);
      setCrossMap((prev) => ({ ...prev, [entryId]: res.occurrences || [] }));
    } catch {
      // ignore
    } finally {
      setLoadingCrossId(null);
    }
  };

  useEffect(() => {
    setCrossMap({});
  }, [episodeId, entries.length]);

  useEffect(() => {
    if (selectedEntryId) {
      loadCrossOccurrences(selectedEntryId);
    }
  }, [selectedEntryId, episodeId]);

  const sentenceEntrySet = new Set(activeSubtitle?.entry_ids || []);

  const filtered = entries.filter((e) => {
    if (scope === 'sentence' && activeSubtitle && !sentenceEntrySet.has(e.id)) {
      return false;
    }
    if (category !== '全部' && e.category !== category) return false;
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      const defs = (e.definitions || []).map((d) => `${d.definition_source} ${d.definition_target}`).join(' ');
      if (!`${e.headword} ${e.category} ${defs}`.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  // Ensure focused entry rises to top when selected from a subtitle keycap
  const sorted = [...filtered].sort((a, b) => {
    if (a.id === selectedEntryId) return -1;
    if (b.id === selectedEntryId) return 1;
    return 0;
  });

  return (
    <>
      <div className="sub-toolbar">
        <div className="toolbar-group">
          <button
            type="button"
            className={`seg-pill ${scope === 'all' ? 'active' : ''}`}
            onClick={() => setScope('all')}
          >
            全篇词块 ({entries.length})
          </button>
          <button
            type="button"
            className={`seg-pill ${scope === 'sentence' ? 'active' : ''}`}
            onClick={() => setScope('sentence')}
          >
            本句词块 ({sentenceEntrySet.size})
          </button>
        </div>

        <div className="toolbar-group">
          <button
            type="button"
            className={`chunk chunk-sm ${hideMeaning ? 'chunk-yellow' : 'chunk-white'}`}
            onClick={() => setHideMeaning((v) => !v)}
          >
            {hideMeaning ? <Eye size={14} /> : <EyeOff size={14} />}
            <span>{hideMeaning ? '显示释义' : '遮中文自测'}</span>
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flexShrink: 0 }}>
        <div style={{ position: 'relative' }}>
          <Search size={15} className="library-search-icon" />
          <input
            type="search"
            className="input-3d"
            style={{ paddingLeft: 36 }}
            placeholder="检索词条、短语或中文释义..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="toolbar-group">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`chunk chunk-sm ${category === cat ? 'chunk-dark' : 'chunk-white'}`}
              onClick={() => setCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      <div className="cards-scroll">
        {sorted.length === 0 ? (
          <div className="practice-card" style={{ alignItems: 'center', padding: 26 }}>
            <strong>没有匹配的词块</strong>
            <p style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>
              尝试切回「全篇词块」或在「校对编辑」中手动新增自定义词块。
            </p>
          </div>
        ) : (
          sorted.map((entry) => {
            const isFocused = entry.id === selectedEntryId;
            const ipaUs = entry.pronunciations?.find((p) => p.accent_type === 'US')?.ipa || entry.pronunciations?.[0]?.ipa || '';
            const ipaUk = entry.pronunciations?.find((p) => p.accent_type === 'UK')?.ipa || '';
            const crossList = crossMap[entry.id];

            return (
              <article
                key={entry.id}
                className={`dict-entry-card ${isFocused ? 'focused' : ''}`}
                onClick={() => onSelectEntry(entry.id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: 19 }}>{entry.headword}</strong>
                    <span className="pill-3d dark">{entry.category}</span>
                    {(entry.exam_tags || []).map((tag) => (
                      <span key={tag} className="pill-3d">
                        {tag}
                      </span>
                    ))}
                  </div>

                  <div className="toolbar-group" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="chunk chunk-white chunk-sm"
                      onClick={() => speakWord(entry.headword, 'US')}
                      title="美式发音"
                    >
                      <Volume2 size={14} />
                      <span>美</span>
                    </button>
                    <button
                      type="button"
                      className="chunk chunk-white chunk-sm"
                      onClick={() => speakWord(entry.headword, 'UK')}
                      title="英式发音"
                    >
                      <Volume2 size={14} />
                      <span>英</span>
                    </button>
                    <button
                      type="button"
                      className={`chunk chunk-sm ${entry.is_bookmarked ? 'chunk-coral' : 'chunk-white'}`}
                      onClick={() => onToggleBookmark(entry.id)}
                      title={entry.is_bookmarked ? '移出生词本' : '收藏到生词本'}
                    >
                      <Star size={14} fill={entry.is_bookmarked ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                </div>

                {(ipaUs || ipaUk) && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13.5, color: 'var(--ink-sub)' }}>
                    {ipaUs && <span>US {ipaUs}</span>}
                    {ipaUk && ipaUk !== ipaUs && <span style={{ marginLeft: 12 }}>UK {ipaUk}</span>}
                  </div>
                )}

                {(entry.definitions || []).map((def, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                      paddingTop: idx > 0 ? 6 : 0,
                      borderTop: idx > 0 ? '1px dashed var(--card-deep)' : 'none',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                      {def.pos && <span className="pill-3d">{def.pos}</span>}
                      <strong
                        style={{
                          fontSize: 15,
                          filter: hideMeaning ? 'blur(6px)' : 'none',
                          userSelect: hideMeaning ? 'none' : 'auto',
                        }}
                      >
                        {def.definition_target}
                      </strong>
                    </div>
                    {def.definition_source && (
                      <p style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>{def.definition_source}</p>
                    )}
                    {def.usage_pattern && (
                      <p style={{ fontSize: 13, color: 'var(--ink-muted)', fontWeight: 700 }}>
                        搭配：{def.usage_pattern}
                      </p>
                    )}
                    {(def.examples || []).slice(0, 1).map((ex, i) => (
                      <div
                        key={i}
                        style={{
                          background: 'var(--panel-bg)',
                          borderRadius: 12,
                          padding: '8px 11px',
                          marginTop: 2,
                        }}
                      >
                        <div style={{ fontSize: 13.5, fontWeight: 700 }}>{ex.example_source}</div>
                        {ex.example_target && !hideMeaning && (
                          <div style={{ fontSize: 13, color: 'var(--ink-sub)', marginTop: 2 }}>
                            {ex.example_target}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ))}

                {/* Within-episode & Cross-episode Occurrence Jump Links */}
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    gap: 6,
                    marginTop: 4,
                    paddingTop: 8,
                    borderTop: '1px dashed var(--card-deep)',
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {(entry.occurrences || []).map((occ, i) => (
                    <button
                      key={`${occ.subtitle_id}-${i}`}
                      type="button"
                      className="occ-chip tnum"
                      onClick={() => onJumpToSubtitle(occ.subtitle_id)}
                    >
                      <Play size={12} />
                      <span>
                        本篇 #{occ.seq_index} ({formatTime(occ.start_sec)})
                      </span>
                    </button>
                  ))}

                  {entry.cross_episode_count > 1 && !crossList && (
                    <button
                      type="button"
                      className="chunk chunk-mint chunk-sm"
                      onClick={() => loadCrossOccurrences(entry.id)}
                    >
                      <Globe2 size={13} />
                      <span>
                        {loadingCrossId === entry.id
                          ? '检索中...'
                          : `跨篇复现 (${entry.cross_episode_count} 篇)`}
                      </span>
                    </button>
                  )}

                  {crossList &&
                    crossList
                      .filter((c) => c.episode_id !== episodeId)
                      .map((c, idx) => (
                        <button
                          key={`cross-${c.episode_id}-${c.subtitle_id}-${idx}`}
                          type="button"
                          className="occ-chip"
                          style={{ background: 'var(--mint-soft)', color: 'var(--mint-ink)' }}
                          onClick={() => onJumpToOccurrence(c.episode_id, c.subtitle_id)}
                        >
                          <Globe2 size={12} />
                          <span>
                            跨篇「{c.episode_title}」#{c.seq_index}
                          </span>
                        </button>
                      ))}
                </div>
              </article>
            );
          })
        )}
      </div>
    </>
  );
}
