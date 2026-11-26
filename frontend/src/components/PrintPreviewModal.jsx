import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Printer, X } from 'lucide-react';
import { decodeHtmlEntities, formatTime } from '../utils/speech';

export default function PrintPreviewModal({ open, onClose, episode, subtitles, entries }) {
  const [clozeMode, setClozeMode] = useState(false);
  const [includeIpa, setIncludeIpa] = useState(true);
  const [includeGlossary, setIncludeGlossary] = useState(true);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!episode) return null;

  const maskText = (sub) => {
    if (!clozeMode) return sub.source_text;
    const htmlStr = sub.source_html || sub.source_text;
    if (/<span class="lex-term"/.test(htmlStr)) {
      return decodeHtmlEntities(
        htmlStr
          .replace(/<span class="lex-term"[^>]*>.*?<\/span>/g, ' ____________ ')
          .replace(/<[^>]+>/g, '')
      );
    }
    let blanks = 0;
    return decodeHtmlEntities(sub.source_text)
      .split(/(\s+)/)
      .map((tok) => {
        if (/^[A-Za-z]{6,}$/.test(tok) && blanks < 3) {
          blanks += 1;
          return '____________';
        }
        return tok;
      })
      .join('');
  };

  const printSheet = (
    <div className="print-sheet">
      <div className="print-header">
        <h1>
          Lingo 讲义：{episode.title}（{clozeMode ? '挖空测验版' : '双语精听版'}）
        </h1>
        <div className="print-meta">
          合集：{episode.series_name} | 难度：{episode.difficulty} | 时长：{formatTime(episode.duration_sec)} |
          共 {subtitles.length} 句 / {entries.length} 组重点词块
        </div>
      </div>

      {subtitles.map((sub) => (
        <div key={sub.id} className="print-cue">
          <div className="print-cue-en">
            #{sub.seq_index} [{formatTime(sub.start_sec)}] {maskText(sub)}
          </div>
          {includeIpa && sub.ipa && <div className="print-cue-ipa">{sub.ipa}</div>}
          {sub.target_text && <div className="print-cue-cn">{sub.target_text}</div>}
        </div>
      ))}

      {includeGlossary && entries.length > 0 && (
        <div className="print-glossary">
          <h2>重点词汇与短语索引</h2>
          {entries.map((e) => (
            <div key={e.id} className="print-word-item">
              <strong>{e.headword}</strong> [{e.category}] {e.pronunciations?.[0]?.ipa || ''} —{' '}
              {e.definitions?.[0]?.definition_target || ''}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Portal printable A4 sheet directly onto document.body so @media print hiding .app-frame keeps it visible */}
      {typeof document !== 'undefined' && createPortal(printSheet, document.body)}

      {open && (
        <div className="modal-backdrop" onClick={onClose}>
          <div className="modal-3d" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>
                <Printer size={22} />
                <span>打印 / 导出 PDF 精听讲义</span>
              </h2>
              <div className="toolbar-group">
                <button
                  type="button"
                  className="chunk chunk-yellow chunk-sm"
                  onClick={() => window.print()}
                >
                  <Printer size={15} />
                  <span>打印或另存为 PDF</span>
                </button>
                <button type="button" className="chunk chunk-dark chunk-sm" onClick={onClose}>
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="toolbar-group">
                <button
                  type="button"
                  className={`chunk chunk-sm ${!clozeMode ? 'chunk-dark' : 'chunk-white'}`}
                  onClick={() => setClozeMode(false)}
                >
                  双语对照讲义
                </button>
                <button
                  type="button"
                  className={`chunk chunk-sm ${clozeMode ? 'chunk-dark' : 'chunk-white'}`}
                  onClick={() => setClozeMode(true)}
                >
                  词块挖空测验卷
                </button>
                <button
                  type="button"
                  className={`chunk chunk-sm ${includeIpa ? 'chunk-mint' : 'chunk-white'}`}
                  onClick={() => setIncludeIpa((v) => !v)}
                >
                  {includeIpa ? '包含 IPA 音标' : '不含音标'}
                </button>
                <button
                  type="button"
                  className={`chunk chunk-sm ${includeGlossary ? 'chunk-mint' : 'chunk-white'}`}
                  onClick={() => setIncludeGlossary((v) => !v)}
                >
                  {includeGlossary ? '附带词块表' : '仅打印正文'}
                </button>
              </div>

              <div
                style={{
                  background: '#FFFFFF',
                  borderRadius: 18,
                  padding: '20px 24px',
                  boxShadow: 'inset 0 0 0 2px var(--card-deep)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                }}
              >
                <h3 style={{ fontSize: 18, fontWeight: 900, borderBottom: '2px solid var(--ink)', paddingBottom: 8 }}>
                  {episode.title}（{clozeMode ? '挖空测验版' : '双语精听版'}）
                </h3>
                {subtitles.map((sub) => (
                  <div key={sub.id} style={{ paddingBottom: 6 }}>
                    <div style={{ fontSize: 15, fontWeight: 800 }}>
                      #{sub.seq_index} {maskText(sub)}
                    </div>
                    {includeIpa && sub.ipa && (
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-sub)' }}>
                        {sub.ipa}
                      </div>
                    )}
                    <div style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>{sub.target_text}</div>
                  </div>
                ))}
                {includeGlossary && entries.length > 0 && (
                  <div style={{ borderTop: '2px solid var(--ink)', paddingTop: 10, marginTop: 6 }}>
                    <strong style={{ fontSize: 15 }}>重点词块表（共 {entries.length} 组）</strong>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 8 }}>
                      {entries.slice(0, 14).map((e) => (
                        <div key={e.id} style={{ fontSize: 13 }}>
                          <strong>{e.headword}</strong> [{e.category}] {e.definitions?.[0]?.definition_target}
                        </div>
                      ))}
                    </div>
                    {entries.length > 14 && (
                      <p style={{ fontSize: 12.5, color: 'var(--ink-sub)', marginTop: 6, fontWeight: 700 }}>
                        预览展示前 14 组，点击「打印或另存为 PDF」将输出全部 {entries.length} 组词块。
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
