import React, { useEffect, useState } from 'react';
import { BookMarked, Download, Play, RotateCw, Star, Volume2, X } from 'lucide-react';
import { api } from '../api';
import { formatTime, speakWord, stopSpeechSynthesis } from '../utils/speech';

export default function VocabDeckModal({
  open,
  onClose,
  onJumpToOccurrence,
  onDeckChanged,
  onToast,
}) {
  const [tab, setTab] = useState('words'); // words | flashcard | sentences
  const [deck, setDeck] = useState({ entries: [], favorite_subtitles: [] });
  const [loading, setLoading] = useState(false);
  const [cardIdx, setCardIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);

  const loadDeck = async () => {
    setLoading(true);
    try {
      const data = await api.getVocabDeck();
      setDeck(data);
      setCardIdx(0);
      setFlipped(false);
    } catch (err) {
      onToast(err.message || '加载生词本失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) loadDeck();
    else stopSpeechSynthesis();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        stopSpeechSynthesis();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      stopSpeechSynthesis();
    };
  }, [open, onClose]);

  if (!open) return null;

  const handleRemoveEntry = async (entryId) => {
    try {
      await api.toggleEntryBookmark(entryId);
      await loadDeck();
      onDeckChanged();
    } catch (err) {
      onToast(err.message || '操作失败');
    }
  };

  const handleRemoveSub = async (subId) => {
    try {
      await api.toggleSubtitleFavorite(subId);
      await loadDeck();
      onDeckChanged();
    } catch (err) {
      onToast(err.message || '操作失败');
    }
  };

  const currentCard = deck.entries[cardIdx] || null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-3d" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>
            <BookMarked size={22} />
            <span>个人生词本与闪卡复习</span>
          </h2>
          <div className="toolbar-group">
            <a
              href="/api/vocab-deck/export?format=csv"
              className="chunk chunk-white chunk-sm"
              style={{ textDecoration: 'none' }}
            >
              <Download size={14} />
              <span>导出 CSV</span>
            </a>
            <a
              href="/api/vocab-deck/export?format=anki"
              className="chunk chunk-yellow chunk-sm"
              style={{ textDecoration: 'none' }}
            >
              <Download size={14} />
              <span>导出 Anki</span>
            </a>
            <button type="button" className="chunk chunk-dark chunk-sm" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="toolbar-group">
            <button
              type="button"
              className={`chunk chunk-sm ${tab === 'words' ? 'chunk-dark' : 'chunk-white'}`}
              onClick={() => setTab('words')}
            >
              收藏词块 ({deck.entries.length})
            </button>
            <button
              type="button"
              className={`chunk chunk-sm ${tab === 'flashcard' ? 'chunk-dark' : 'chunk-white'}`}
              onClick={() => {
                setTab('flashcard');
                setFlipped(false);
              }}
            >
              闪卡翻面抽查
            </button>
            <button
              type="button"
              className={`chunk chunk-sm ${tab === 'sentences' ? 'chunk-dark' : 'chunk-white'}`}
              onClick={() => setTab('sentences')}
            >
              收藏金句 ({deck.favorite_subtitles.length})
            </button>
          </div>

          {loading ? (
            <p style={{ padding: 20, textAlign: 'center', fontWeight: 700 }}>正在加载生词本...</p>
          ) : tab === 'words' ? (
            deck.entries.length === 0 ? (
              <div className="practice-card" style={{ alignItems: 'center', padding: 28 }}>
                <strong>生词本还是空的</strong>
                <p style={{ color: 'var(--ink-sub)', fontSize: 14 }}>
                  在学习机里点击任意 3D 词块键帽并点亮收藏星标，即可收录到这里。
                </p>
              </div>
            ) : (
              deck.entries.map((entry) => {
                const ipa = entry.pronunciations?.[0]?.ipa || '';
                const d0 = entry.definitions?.[0] || {};
                return (
                  <div key={entry.id} className="dict-entry-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <strong style={{ fontSize: 18 }}>{entry.headword}</strong>
                        <span className="pill-3d dark">{entry.category}</span>
                        {ipa && (
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13.5, color: 'var(--ink-sub)' }}>
                            {ipa}
                          </span>
                        )}
                      </div>
                      <div className="toolbar-group">
                        <button
                          type="button"
                          className="chunk chunk-white chunk-sm"
                          onClick={() => speakWord(entry.headword, 'US')}
                        >
                          <Volume2 size={14} />
                          <span>美音</span>
                        </button>
                        <button
                          type="button"
                          className="chunk chunk-white chunk-sm"
                          onClick={() => speakWord(entry.headword, 'UK')}
                        >
                          <Volume2 size={14} />
                          <span>英音</span>
                        </button>
                        <button
                          type="button"
                          className="chunk chunk-coral chunk-sm"
                          onClick={() => handleRemoveEntry(entry.id)}
                          title="移出生词本"
                        >
                          <Star size={14} fill="currentColor" />
                        </button>
                      </div>
                    </div>
                    <p style={{ fontSize: 14.5, fontWeight: 700 }}>{d0.definition_target}</p>
                    {d0.definition_source && (
                      <p style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>{d0.definition_source}</p>
                    )}
                    {entry.occurrences?.length > 0 && (
                      <div className="toolbar-group" style={{ marginTop: 4 }}>
                        {entry.occurrences.map((occ, i) => (
                          <button
                            key={`${occ.episode_id}-${occ.subtitle_id}-${i}`}
                            type="button"
                            className="occ-chip"
                            onClick={() => {
                              onJumpToOccurrence(occ.episode_id, occ.subtitle_id);
                              onClose();
                            }}
                          >
                            <Play size={12} />
                            <span>
                              {occ.episode_title} #{occ.seq_index} ({formatTime(occ.start_sec)})
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )
          ) : tab === 'flashcard' ? (
            !currentCard ? (
              <div className="practice-card" style={{ alignItems: 'center', padding: 28 }}>
                <strong>请先收藏至少 1 个词块再开始闪卡复习</strong>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div
                  className={`flashcard-3d ${flipped ? 'flipped' : ''}`}
                  onClick={() => setFlipped((f) => !f)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setFlipped((f) => !f);
                    }
                  }}
                >
                  <span className="pill-3d dark tnum">
                    卡片 {cardIdx + 1} / {deck.entries.length} [{currentCard.category}]
                  </span>
                  <h3 style={{ fontSize: 30, fontWeight: 900 }}>{currentCard.headword}</h3>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 15, color: 'var(--ink-sub)' }}>
                    {currentCard.pronunciations?.[0]?.ipa}
                  </div>
                  {flipped ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 540 }}>
                      <strong style={{ fontSize: 18 }}>
                        {currentCard.definitions?.[0]?.definition_target}
                      </strong>
                      <p style={{ fontSize: 14, color: 'var(--ink-sub)' }}>
                        {currentCard.definitions?.[0]?.definition_source}
                      </p>
                      {currentCard.definitions?.[0]?.examples?.[0]?.example_source && (
                        <p style={{ fontSize: 14, fontWeight: 700, marginTop: 4 }}>
                          例句：{currentCard.definitions[0].examples[0].example_source}
                        </p>
                      )}
                    </div>
                  ) : (
                    <p style={{ color: 'var(--ink-sub)', fontSize: 14, fontWeight: 700 }}>
                      点击卡片翻转查看释义与原句
                    </p>
                  )}
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                  <button
                    type="button"
                    className="chunk chunk-white"
                    onClick={() => {
                      setCardIdx((i) => (i - 1 + deck.entries.length) % deck.entries.length);
                      setFlipped(false);
                    }}
                  >
                    上一张
                  </button>
                  <div className="toolbar-group">
                    <button
                      type="button"
                      className="chunk chunk-cream"
                      onClick={() => speakWord(currentCard.headword, 'US')}
                    >
                      <Volume2 size={15} />
                      <span>朗读发音</span>
                    </button>
                    <button
                      type="button"
                      className="chunk chunk-yellow"
                      onClick={() => setFlipped((f) => !f)}
                    >
                      <RotateCw size={15} />
                      <span>翻转卡片</span>
                    </button>
                  </div>
                  <button
                    type="button"
                    className="chunk chunk-dark"
                    onClick={() => {
                      setCardIdx((i) => (i + 1) % deck.entries.length);
                      setFlipped(false);
                    }}
                  >
                    下一张
                  </button>
                </div>
              </div>
            )
          ) : deck.favorite_subtitles.length === 0 ? (
            <div className="practice-card" style={{ alignItems: 'center', padding: 28 }}>
              <strong>暂无收藏金句</strong>
              <p style={{ color: 'var(--ink-sub)', fontSize: 14 }}>
                在字幕卡片右上角点击星标按钮，即可收藏地道例句方便回跳复习。
              </p>
            </div>
          ) : (
            deck.favorite_subtitles.map((sub) => (
              <div key={sub.id} className="dict-entry-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="pill-3d dark tnum">
                    {sub.episode_title} #{sub.seq_index} ({formatTime(sub.start_sec)})
                  </span>
                  <div className="toolbar-group">
                    <button
                      type="button"
                      className="chunk chunk-yellow chunk-sm"
                      onClick={() => {
                        onJumpToOccurrence(sub.episode_id, sub.id);
                        onClose();
                      }}
                    >
                      <Play size={13} />
                      <span>跳转播放</span>
                    </button>
                    <button
                      type="button"
                      className="chunk chunk-coral chunk-sm"
                      onClick={() => handleRemoveSub(sub.id)}
                    >
                      移除
                    </button>
                  </div>
                </div>
                <p style={{ fontSize: 16, fontWeight: 800 }}>{sub.source_text}</p>
                {sub.ipa && (
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: 13.5, color: 'var(--ink-sub)' }}>
                    {sub.ipa}
                  </p>
                )}
                <p style={{ fontSize: 14, color: 'var(--ink-sub)' }}>{sub.target_text}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
