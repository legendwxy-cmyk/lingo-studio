import React, { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  Edit3,
  FileUp,
  Mic,
  PlusCircle,
  RefreshCw,
  Save,
  Sparkles,
  Square,
  Trash2,
  Volume2,
} from 'lucide-react';
import { api } from '../api';
import { formatTime, pickRecorderMimeType, stopSpeechSynthesis } from '../utils/speech';

function pauseAllMediaInDom() {
  stopSpeechSynthesis();
  if (typeof document === 'undefined') return;
  document.querySelectorAll('audio, video').forEach((el) => {
    if (!el.paused) {
      try {
        el.pause();
      } catch {
        // ignore
      }
    }
  });
}

/* ===================== 1. AI SENTENCE COACH & RETELLING PANEL ===================== */
export function AiCoachPanel({
  episode,
  activeSubtitle,
  isRecording = false,
  onRecordingChange,
  onStopAllAudio,
  onSubtitleAnalyzed,
  onEpisodeReload,
  onPlayCurrent,
  onToast,
}) {
  const [analyzing, setAnalyzing] = useState(false);
  const [retellMode, setRetellMode] = useState('keywords'); // keywords | questions | blind
  const [retellInput, setRetellInput] = useState('');
  const [evaluating, setEvaluating] = useState(false);
  const [evaluation, setEvaluation] = useState(null);

  const [recordingRetell, setRecordingRetell] = useState(false);
  const [recElapsed, setRecElapsed] = useState(0);
  const recRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const acquiringRef = useRef(false);
  const discardRef = useRef(false);
  const frozenRetellRef = useRef({ episodeId: null, mode: 'keywords' });

  useEffect(() => {
    const latest = episode?.retelling_history?.[0]?.evaluation || null;
    setEvaluation(latest);
    setRetellInput('');
  }, [episode?.id]);

  // Keep evaluation in sync when episode history reloads after submission
  useEffect(() => {
    const latest = episode?.retelling_history?.[0]?.evaluation || null;
    if (latest) setEvaluation(latest);
  }, [episode?.retelling_history?.[0]?.id]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (recRef.current && recRef.current.state === 'recording') {
        discardRef.current = true;
        try {
          recRef.current.stop();
        } catch {
          // ignore
        }
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      onRecordingChange?.(false);
    };
  }, []);

  const handleAnalyze = async (force = false) => {
    if (!activeSubtitle || recordingRetell || isRecording) return;
    setAnalyzing(true);
    try {
      const res = await api.analyzeSubtitle(activeSubtitle.id, force);
      onSubtitleAnalyzed(activeSubtitle.id, res.ai_note);
      onToast('本句语音语法精讲已生成');
    } catch (err) {
      onToast(err.message || '精讲生成失败');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleEvaluateRetelling = async () => {
    if (recordingRetell || isRecording) return;
    if (!retellInput.trim()) {
      onToast('请先输入或口述录音你的英文复述内容');
      return;
    }
    setEvaluating(true);
    try {
      const res = await api.evaluateRetelling(episode.id, {
        mode: retellMode,
        transcript_text: retellInput,
      });
      setEvaluation(res.evaluation);
      onToast(`复述要点覆盖评分：${res.evaluation.coverage_score} 分`);
      onEpisodeReload?.();
    } catch (err) {
      onToast(err.message || '复述批改失败');
    } finally {
      setEvaluating(false);
    }
  };

  const startVoiceRetell = async () => {
    if (acquiringRef.current || recordingRetell || evaluating || isRecording) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      onToast('当前环境不支持麦克风口述录音，请直接输入英文复述文本');
      return;
    }

    acquiringRef.current = true;
    onStopAllAudio?.();
    pauseAllMediaInDom();
    onRecordingChange?.(true);
    frozenRetellRef.current = { episodeId: episode.id, mode: retellMode };
    discardRef.current = false;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      onStopAllAudio?.();
      pauseAllMediaInDom();

      streamRef.current = stream;
      const preferredMime = pickRecorderMimeType();
      const rec = preferredMime
        ? new MediaRecorder(stream, { mimeType: preferredMime })
        : new MediaRecorder(stream);

      chunksRef.current = [];
      rec.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      rec.onstop = async () => {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        stream.getTracks().forEach((t) => t.stop());
        if (streamRef.current === stream) streamRef.current = null;
        recRef.current = null;
        setRecordingRetell(false);
        onRecordingChange?.(false);

        if (discardRef.current) {
          discardRef.current = false;
          return;
        }

        const mime = rec.mimeType || preferredMime || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type: mime });
        if (blob.size < 300) {
          onToast('口述录音过短未提交，请清晰复述后重试');
          return;
        }
        const { episodeId: targetEpId, mode: targetMode } = frozenRetellRef.current;
        setEvaluating(true);
        try {
          const res = await api.evaluateRetellingAudio(targetEpId, targetMode, blob);
          if (res.transcript_text) setRetellInput(res.transcript_text);
          setEvaluation(res.evaluation);
          onToast(`口述转写与批改完成：${res.evaluation.coverage_score} 分`);
          onEpisodeReload?.();
        } catch (err) {
          onToast(err.message || '口述转写评测失败');
        } finally {
          setEvaluating(false);
        }
      };
      recRef.current = rec;
      rec.start();
      setRecordingRetell(true);
      setRecElapsed(0);
      timerRef.current = setInterval(() => setRecElapsed((t) => +(t + 0.1).toFixed(1)), 100);
    } catch {
      onRecordingChange?.(false);
      onToast('未获取到麦克风权限，请检查浏览器音频输入设置');
    } finally {
      acquiringRef.current = false;
    }
  };

  const stopVoiceRetell = () => {
    if (recRef.current && recRef.current.state === 'recording') {
      recRef.current.stop();
    } else {
      setRecordingRetell(false);
      onRecordingChange?.(false);
    }
  };

  const aiNote = activeSubtitle?.ai_note;
  const guide = episode?.retelling_guide || {};

  return (
    <div className="cards-scroll">
      {/* Sentence Grammar & Linking Breakdown */}
      <div className="practice-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="pill-3d dark">当前句 AI 精讲</span>
            {activeSubtitle && (
              <span className="pill-3d tnum">
                #{activeSubtitle.seq_index} {formatTime(activeSubtitle.start_sec)}
              </span>
            )}
          </div>
          <div className="toolbar-group">
            <button
              type="button"
              className="chunk chunk-white chunk-sm"
              disabled={recordingRetell || isRecording || !activeSubtitle}
              onClick={onPlayCurrent}
            >
              <Volume2 size={14} />
              <span>听本句</span>
            </button>
            <button
              type="button"
              className="chunk chunk-yellow chunk-sm"
              disabled={analyzing || !activeSubtitle || recordingRetell || isRecording}
              onClick={() => handleAnalyze(Boolean(aiNote))}
            >
              {aiNote ? <RefreshCw size={14} /> : <Sparkles size={14} />}
              <span>{analyzing ? '解析中...' : aiNote ? '重新生成精讲' : '生成语音语法精讲'}</span>
            </button>
          </div>
        </div>

        {activeSubtitle && (
          <p style={{ fontSize: 16, fontWeight: 800 }}>{activeSubtitle.source_text}</p>
        )}

        {aiNote ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <span className="pill-3d mint">{aiNote.engine || '语音语法分析'}</span>
            </div>
            <div style={{ background: 'var(--panel-bg)', borderRadius: 14, padding: '10px 13px' }}>
              <strong style={{ fontSize: 13.5 }}>句型结构拆解</strong>
              <p style={{ fontSize: 14, marginTop: 3 }}>{aiNote.grammar_summary}</p>
            </div>
            {(aiNote.linking_tips || []).length > 0 && (
              <div style={{ background: 'var(--panel-bg)', borderRadius: 14, padding: '10px 13px' }}>
                <strong style={{ fontSize: 13.5 }}>连读、弱读与节奏提示</strong>
                <ul style={{ paddingLeft: 18, marginTop: 4, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {aiNote.linking_tips.map((t, i) => (
                    <li key={i} style={{ fontSize: 13.5 }}>
                      {t}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {(aiNote.key_expressions || []).length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {aiNote.key_expressions.map((item, i) => (
                  <span key={i} className="pill-3d">
                    <strong>{item.expr}</strong> {item.note}
                  </span>
                ))}
              </div>
            )}
            {aiNote.practice_tip && (
              <p style={{ fontSize: 13.5, color: 'var(--ink-sub)', fontWeight: 700 }}>
                训练建议：{aiNote.practice_tip}
              </p>
            )}
          </div>
        ) : (
          <p style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>
            点击右上角「生成语音语法精讲」，自动剖析本句的连读失去爆破、实词重读与主从句意群（未配置 LLM API 时同样支持本地语音学拆解）。
          </p>
        )}
      </div>

      {/* 3-Level Guided Retelling Studio */}
      <div className="practice-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span className="pill-3d dark">整篇三阶复述检验</span>
          <div className="toolbar-group">
            <button
              type="button"
              className={`seg-pill ${retellMode === 'keywords' ? 'active' : ''}`}
              disabled={recordingRetell || isRecording}
              onClick={() => setRetellMode('keywords')}
            >
              关键词提示
            </button>
            <button
              type="button"
              className={`seg-pill ${retellMode === 'questions' ? 'active' : ''}`}
              disabled={recordingRetell || isRecording}
              onClick={() => setRetellMode('questions')}
            >
              问题引导
            </button>
            <button
              type="button"
              className={`seg-pill ${retellMode === 'blind' ? 'active' : ''}`}
              disabled={recordingRetell || isRecording}
              onClick={() => setRetellMode('blind')}
            >
              无提示脱稿
            </button>
          </div>
        </div>

        {retellMode === 'keywords' && (guide.keywords || []).length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {guide.keywords.map((kw) => (
              <span key={kw} className="keycap-word" style={{ cursor: 'default' }}>
                {kw}
              </span>
            ))}
          </div>
        )}

        {retellMode === 'questions' && (guide.questions || []).length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {guide.questions.map((q, idx) => (
              <div key={idx} style={{ background: 'var(--panel-bg)', borderRadius: 12, padding: '8px 12px' }}>
                <div style={{ fontSize: 14, fontWeight: 800 }}>
                  Q{idx + 1}. {q.en}
                </div>
                <div style={{ fontSize: 13, color: 'var(--ink-sub)' }}>{q.zh}</div>
              </div>
            ))}
          </div>
        )}

        {retellMode === 'blind' && (
          <p style={{ fontSize: 13.5, color: 'var(--ink-sub)', fontWeight: 700 }}>
            脱稿挑战模式：不看字幕和关键词，直接口述或输入你的英文复述，系统自动核对要点覆盖率。
          </p>
        )}

        {recordingRetell && (
          <div
            role="status"
            style={{
              background: '#FFE4E9',
              color: '#850E29',
              borderRadius: 12,
              padding: '8px 12px',
              fontSize: 13.5,
              fontWeight: 800,
            }}
          >
            语音口述中：原声视频与切换控制已自动静音并锁定，说完请点「停止口述并批改」。
          </div>
        )}

        <textarea
          className="textarea-3d"
          placeholder="输入英文复述，或点击下方「语音口述复述」直接说英文由 Whisper 自动转写并批改..."
          disabled={recordingRetell}
          value={retellInput}
          onChange={(e) => setRetellInput(e.target.value)}
        />

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {!recordingRetell ? (
            <button
              type="button"
              className="chunk chunk-coral chunk-sm"
              disabled={evaluating || isRecording}
              onClick={startVoiceRetell}
            >
              <Mic size={15} />
              <span>语音口述复述</span>
            </button>
          ) : (
            <button type="button" className="chunk chunk-dark chunk-sm" onClick={stopVoiceRetell}>
              <Square size={14} />
              <span className="tnum">停止口述并批改 ({recElapsed.toFixed(1)}s)</span>
            </button>
          )}

          <button
            type="button"
            className="chunk chunk-dark chunk-sm"
            disabled={evaluating || recordingRetell || isRecording}
            onClick={handleEvaluateRetelling}
          >
            <CheckCircle2 size={15} />
            <span>{evaluating ? '转写与批改中...' : '提交文字批改'}</span>
          </button>
        </div>

        {evaluation && (
          <div
            style={{
              background: 'var(--panel-bg)',
              borderRadius: 16,
              padding: 14,
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div className="score-ring tnum">
                <span>{evaluation.coverage_score ?? 0}</span>
                <span style={{ fontSize: 10, color: '#EAE4F8' }}>覆盖</span>
              </div>
              <div>
                <span className="pill-3d mint">{evaluation.engine || '要点评测'}</span>
                <p style={{ fontSize: 14, fontWeight: 700, marginTop: 4 }}>{evaluation.fluency_comment}</p>
              </div>
            </div>

            {(evaluation.point_checks || []).map((pt, i) => (
              <div
                key={i}
                style={{
                  background: 'var(--card-bg)',
                  borderRadius: 12,
                  padding: '8px 11px',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 8,
                }}
              >
                <span
                  className={`pill-3d ${
                    pt.status === 'covered' ? 'mint' : pt.status === 'partial' ? '' : 'coral'
                  }`}
                >
                  {pt.status === 'covered' ? '已覆盖' : pt.status === 'partial' ? '部分覆盖' : '待补充'}
                </span>
                <div style={{ fontSize: 13.5 }}>
                  <div style={{ fontWeight: 800 }}>{pt.point_zh}</div>
                  <div style={{ color: 'var(--ink-sub)', marginTop: 2 }}>{pt.note}</div>
                </div>
              </div>
            ))}

            {evaluation.polished_version && (
              <div style={{ fontSize: 13.5, background: 'var(--card-bg)', padding: '9px 12px', borderRadius: 12 }}>
                <strong>参考地道串联版：</strong>
                {evaluation.polished_version}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ===================== 2. PROOFREAD SUBTITLE & CUSTOM LEXICON EDITOR ===================== */
const EMPTY_SUB_FORM = {
  source_text: '',
  target_text: '',
  start_sec: 0,
  end_sec: 0,
  ipa: '',
};

export function ProofreadEditorPanel({
  episodeId,
  hasRecordings = false,
  activeSubtitle,
  onStopAllAudio,
  onEpisodeReload,
  onDeckChanged,
  onToast,
}) {
  const [subForm, setSubForm] = useState(EMPTY_SUB_FORM);
  const [ipaDirty, setIpaDirty] = useState(false);
  const [savingSub, setSavingSub] = useState(false);
  const [addingSub, setAddingSub] = useState(false);
  const [replacingSrt, setReplacingSrt] = useState(false);

  const [newEntry, setNewEntry] = useState({
    headword: '',
    category: '短语动词',
    definition_target: '',
    definition_source: '',
    usage_pattern: '',
  });
  const [savingEntry, setSavingEntry] = useState(false);
  const srtInputRef = useRef(null);
  const pollCancelRef = useRef(false);

  useEffect(() => {
    return () => {
      pollCancelRef.current = true;
    };
  }, []);

  useEffect(() => {
    if (activeSubtitle) {
      setSubForm({
        source_text: activeSubtitle.source_text || '',
        target_text: activeSubtitle.target_text || '',
        start_sec: activeSubtitle.start_sec ?? 0,
        end_sec: activeSubtitle.end_sec ?? 0,
        ipa: activeSubtitle.ipa || '',
      });
      setIpaDirty(false);
    } else {
      setSubForm(EMPTY_SUB_FORM);
      setIpaDirty(false);
    }
  }, [
    activeSubtitle?.id,
    activeSubtitle?.source_text,
    activeSubtitle?.target_text,
    activeSubtitle?.start_sec,
    activeSubtitle?.end_sec,
    activeSubtitle?.ipa,
  ]);

  const handleSaveSub = async (e) => {
    e.preventDefault();
    if (!activeSubtitle) return;
    const cleanSource = subForm.source_text.trim();
    const startVal = Number(subForm.start_sec);
    const endVal = Number(subForm.end_sec);
    if (!cleanSource) {
      onToast('英文原句不能为空');
      return;
    }
    if (!Number.isFinite(startVal) || !Number.isFinite(endVal) || startVal < 0 || endVal <= startVal) {
      onToast('时间轴无效：开始时间不能小于 0，且结束时间必须大于开始时间');
      return;
    }

    const payload = {
      source_text: cleanSource,
      target_text: subForm.target_text.trim(),
      start_sec: startVal,
      end_sec: endVal,
    };
    const sourceChanged = cleanSource !== (activeSubtitle.source_text || '').trim();
    if (ipaDirty || !sourceChanged) {
      payload.ipa = subForm.ipa.trim();
    }

    setSavingSub(true);
    try {
      await api.patchSubtitle(activeSubtitle.id, payload);
      onToast(
        sourceChanged && !ipaDirty
          ? '字幕已保存，IPA 音标与词块键帽已自动更新'
          : '字幕已保存'
      );
      onEpisodeReload();
    } catch (err) {
      onToast(err.message || '保存字幕失败');
    } finally {
      setSavingSub(false);
    }
  };

  const handleInsertAfter = async () => {
    setAddingSub(true);
    try {
      const start = activeSubtitle ? +(activeSubtitle.end_sec + 0.1).toFixed(2) : 0;
      const end = +(start + 3.0).toFixed(2);
      await api.createSubtitle(episodeId, {
        start_sec: start,
        end_sec: end,
        source_text: 'New subtitle line ready for proofreading.',
        target_text: '新增字幕句（请编辑修改）',
      });
      onToast('已插入新字幕句并重排时间序');
      onEpisodeReload();
    } catch (err) {
      onToast(err.message || '新增字幕句失败');
    } finally {
      setAddingSub(false);
    }
  };

  const handleDeleteCurrent = async () => {
    if (!activeSubtitle) return;
    if (!window.confirm(`确定删除第 #${activeSubtitle.seq_index} 句字幕吗？`)) return;
    try {
      await api.deleteSubtitle(activeSubtitle.id);
      onToast('已删除该句字幕并重排索引');
      onEpisodeReload();
      onDeckChanged?.();
    } catch (err) {
      onToast(err.message || '删除字幕失败');
    }
  };

  const handleReplaceSrt = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (
      hasRecordings &&
      !window.confirm('替换字幕会重新拆解全部句子并清空本篇已有跟读录音与金句收藏，确定继续吗？')
    ) {
      return;
    }
    onStopAllAudio?.();
    setReplacingSrt(true);
    pollCancelRef.current = false;
    try {
      await api.reprocessEpisode(episodeId, file);
      onToast('已上传新字幕并触发重新拆解，正在等待处理完成...');
      for (let attempt = 0; attempt < 45; attempt += 1) {
        if (pollCancelRef.current) break;
        await new Promise((r) => setTimeout(r, 900));
        if (pollCancelRef.current) break;
        const st = await api.getEpisodeStatus(episodeId);
        if (st.status === 'ready') {
          onToast(`新字幕拆解完成：共 ${st.subtitle_count} 句与 ${st.entry_count} 组词块`);
          onEpisodeReload();
          onDeckChanged?.();
          break;
        }
        if (st.status === 'error') {
          onToast(`字幕替换失败：${st.error_message}`);
          break;
        }
      }
    } catch (err) {
      onToast(err.message || '替换字幕失败');
    } finally {
      setReplacingSrt(false);
    }
  };

  const handleCreateEntry = async (e) => {
    e.preventDefault();
    const hw = newEntry.headword.trim();
    if (!hw) {
      onToast('请填写要新增的英文词块或短语');
      return;
    }
    setSavingEntry(true);
    try {
      const payload = { ...newEntry, headword: hw, episode_id: episodeId };
      try {
        await api.createEntry(payload);
      } catch (err) {
        if (err.status === 409) {
          if (!window.confirm(`词条「${hw}」已存在于词典中，是否用当前填写的内容覆盖原释义？`)) {
            return;
          }
          await api.createEntry({ ...payload, overwrite: true });
        } else {
          throw err;
        }
      }
      setNewEntry({
        headword: '',
        category: '短语动词',
        definition_target: '',
        definition_source: '',
        usage_pattern: '',
      });
      onToast(`已将「${hw}」加入词典并同步高亮到全篇字幕`);
      onEpisodeReload();
      onDeckChanged?.();
    } catch (err) {
      onToast(err.message || '新增词块失败');
    } finally {
      setSavingEntry(false);
    }
  };

  return (
    <div className="cards-scroll">
      <form className="practice-card" noValidate onSubmit={handleSaveSub}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="pill-3d dark">
            <Edit3 size={13} />
            <span>{activeSubtitle ? `校对当前字幕 #${activeSubtitle.seq_index}` : '当前篇目暂无字幕'}</span>
          </span>
          <div className="toolbar-group">
            <input
              ref={srtInputRef}
              type="file"
              accept=".srt,.vtt"
              style={{ display: 'none' }}
              onChange={handleReplaceSrt}
            />
            <button
              type="button"
              className="chunk chunk-white chunk-sm"
              disabled={replacingSrt}
              onClick={() => srtInputRef.current?.click()}
              title="上传新的 SRT/VTT 字幕文件覆盖并重新绑定词块"
            >
              <FileUp size={14} />
              <span>{replacingSrt ? '拆解中...' : '替换 SRT'}</span>
            </button>
            <button
              type="button"
              className="chunk chunk-mint chunk-sm"
              disabled={addingSub || replacingSrt}
              onClick={handleInsertAfter}
            >
              <PlusCircle size={14} />
              <span>插新句</span>
            </button>
            <button
              type="button"
              className="chunk chunk-coral chunk-sm"
              disabled={!activeSubtitle || replacingSrt}
              onClick={handleDeleteCurrent}
              title="删除当前字幕句"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {!activeSubtitle ? (
          <p style={{ fontSize: 14, color: 'var(--ink-sub)', fontWeight: 700, padding: '8px 0' }}>
            当前篇目已无字幕，可点击上方「插新句」手工添加或点击「替换 SRT」导入字幕文件。
          </p>
        ) : (
          <>
            <div>
              <label className="field-label">英文原句</label>
              <textarea
                className="textarea-3d"
                style={{ minHeight: 68 }}
                value={subForm.source_text}
                onChange={(e) => setSubForm({ ...subForm, source_text: e.target.value })}
              />
            </div>

            <div>
              <label className="field-label">中文译文</label>
              <input
                className="input-3d"
                value={subForm.target_text}
                onChange={(e) => setSubForm({ ...subForm, target_text: e.target.value })}
              />
            </div>

            <div className="form-row-2">
              <div>
                <label className="field-label">开始时间（秒）</label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  className="input-3d tnum"
                  value={subForm.start_sec}
                  onChange={(e) => setSubForm({ ...subForm, start_sec: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">结束时间（秒）</label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  className="input-3d tnum"
                  value={subForm.end_sec}
                  onChange={(e) => setSubForm({ ...subForm, end_sec: e.target.value })}
                />
              </div>
            </div>

            <div>
              <label className="field-label">IPA 音标（修改英文原句后不改此项会自动重算音标）</label>
              <input
                className="input-3d"
                style={{ fontFamily: 'var(--font-mono)' }}
                value={subForm.ipa}
                onChange={(e) => {
                  setIpaDirty(true);
                  setSubForm({ ...subForm, ipa: e.target.value });
                }}
              />
            </div>
          </>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            type="submit"
            className="chunk chunk-dark chunk-sm"
            disabled={!activeSubtitle || savingSub || replacingSrt}
          >
            <Save size={15} />
            <span>{savingSub ? '保存中...' : '保存字幕并重绑词块'}</span>
          </button>
        </div>
      </form>

      <form className="practice-card" onSubmit={handleCreateEntry}>
        <span className="pill-3d mint" style={{ alignSelf: 'flex-start' }}>
          <PlusCircle size={13} />
          <span>补充自定义重点词块</span>
        </span>

        <div className="form-row-2">
          <div>
            <label className="field-label">英文词条 / 短语</label>
            <input
              className="input-3d"
              placeholder="例如：slip past"
              value={newEntry.headword}
              onChange={(e) => setNewEntry({ ...newEntry, headword: e.target.value })}
            />
          </div>
          <div>
            <label className="field-label">词块类别</label>
            <select
              className="select-3d"
              value={newEntry.category}
              onChange={(e) => setNewEntry({ ...newEntry, category: e.target.value })}
            >
              <option value="短语动词">短语动词</option>
              <option value="惯用表达">惯用表达</option>
              <option value="搭配">搭配</option>
              <option value="短语">短语</option>
              <option value="单词">单词</option>
            </select>
          </div>
        </div>

        <div>
          <label className="field-label">中文释义</label>
          <input
            className="input-3d"
            placeholder="例如：从耳边溜走；未曾察觉地掠过"
            value={newEntry.definition_target}
            onChange={(e) => setNewEntry({ ...newEntry, definition_target: e.target.value })}
          />
        </div>

        <div className="form-row-2">
          <div>
            <label className="field-label">英文释义（选填）</label>
            <input
              className="input-3d"
              placeholder="to pass by without being noticed"
              value={newEntry.definition_source}
              onChange={(e) => setNewEntry({ ...newEntry, definition_source: e.target.value })}
            />
          </div>
          <div>
            <label className="field-label">常用搭配（选填）</label>
            <input
              className="input-3d"
              placeholder="slip past someone's ear"
              value={newEntry.usage_pattern}
              onChange={(e) => setNewEntry({ ...newEntry, usage_pattern: e.target.value })}
            />
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button type="submit" className="chunk chunk-yellow chunk-sm" disabled={savingEntry}>
            <PlusCircle size={15} />
            <span>{savingEntry ? '正在添加...' : '新增并嵌入字幕键帽'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
