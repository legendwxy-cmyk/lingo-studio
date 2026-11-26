import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  EyeOff,
  Mic,
  Play,
  RotateCcw,
  Square,
  Trash2,
  Volume2,
} from 'lucide-react';
import { api } from '../api';
import {
  alignDictationWords,
  decodeHtmlEntities,
  formatTime,
  normalizeWord,
  pickRecorderMimeType,
  stopSpeechSynthesis,
} from '../utils/speech';

function pauseAllOtherMedia(exceptEl = null) {
  stopSpeechSynthesis();
  if (typeof document === 'undefined') return;
  document.querySelectorAll('audio, video').forEach((el) => {
    if (el !== exceptEl && !el.paused) {
      try {
        el.pause();
      } catch {
        // ignore
      }
    }
  });
}

/* ===================== 1. SHADOWING & COMPARISON PANEL ===================== */
export function ShadowingPanel({
  episodeId,
  activeSubtitle,
  isRecording = false,
  mediaEndedTick = 0,
  onRecordingChange,
  onStopAllAudio,
  onPrepareContinuousShadowing,
  onStartContinuousPlayback,
  onStopContinuousPlayback,
  onPlaySentenceOnce,
  onPlayOriginalSentence,
  onSelectSubtitle,
  onRecordingsChanged,
  onToast,
}) {
  const [shadowMode, setShadowMode] = useState('single'); // single | continuous
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [comparingId, setComparingId] = useState(null);
  const [comparePhase, setComparePhase] = useState('idle'); // idle | original | recording
  const [trackedSegments, setTrackedSegments] = useState([]);
  const [batchSummary, setBatchSummary] = useState(null);

  const mediaRecRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const autoStopTimerRef = useRef(null);
  const audioElRef = useRef(null);
  const acquiringRef = useRef(false);
  const discardRef = useRef(false);
  const frozenTargetRef = useRef({ episodeId: null, subtitleId: null });
  const episodeIdRef = useRef(episodeId);
  episodeIdRef.current = episodeId;
  const activeSubtitleRef = useRef(activeSubtitle);
  activeSubtitleRef.current = activeSubtitle;
  const recordingModeRef = useRef('single');
  const recStartPerfRef = useRef(0);
  const segmentsRef = useRef([]);
  const cancelOriginalRef = useRef(null);
  const compareGenRef = useRef(0);

  const stopCompare = () => {
    compareGenRef.current += 1;
    if (cancelOriginalRef.current) {
      cancelOriginalRef.current();
      cancelOriginalRef.current = null;
    }
    if (audioElRef.current) {
      audioElRef.current.onended = null;
      audioElRef.current.onerror = null;
      audioElRef.current.onpause = null;
      try {
        audioElRef.current.pause();
        audioElRef.current.currentTime = 0;
      } catch {
        // ignore
      }
    }
    setComparingId(null);
    setComparePhase('idle');
  };

  // Stop any ongoing comparison when switching sentence or episode
  useEffect(() => {
    stopCompare();
  }, [activeSubtitle?.id, episodeId]);

  // Clear continuous shadowing summary when switching episodes
  useEffect(() => {
    setBatchSummary(null);
    setTrackedSegments([]);
  }, [episodeId]);

  // Live sentence boundary tracking during Continuous Shadowing
  useEffect(() => {
    if (!recording || recordingModeRef.current !== 'continuous' || !activeSubtitle?.id) return;
    const nowSec = Math.max(0, (performance.now() - recStartPerfRef.current) / 1000);
    const segs = segmentsRef.current;
    if (!segs.length) {
      segs.push({
        subtitle_id: activeSubtitle.id,
        seq_index: activeSubtitle.seq_index,
        start_sec: nowSec,
        end_sec: null,
      });
      setTrackedSegments([...segs]);
      return;
    }
    const last = segs[segs.length - 1];
    if (last.subtitle_id !== activeSubtitle.id) {
      last.end_sec = Math.max(last.start_sec + 0.05, nowSec);
      segs.push({
        subtitle_id: activeSubtitle.id,
        seq_index: activeSubtitle.seq_index,
        start_sec: nowSec,
        end_sec: null,
      });
      setTrackedSegments([...segs]);
    }
  }, [recording, activeSubtitle?.id, activeSubtitle?.seq_index]);

  // Auto-stop smoothly with a short spoken tail when the episode ends during Continuous Shadowing
  useEffect(() => {
    if (!mediaEndedTick || !recording || recordingModeRef.current !== 'continuous') return;
    if (autoStopTimerRef.current) clearTimeout(autoStopTimerRef.current);
    autoStopTimerRef.current = setTimeout(() => {
      autoStopTimerRef.current = null;
      stopRecording();
    }, 750);
  }, [mediaEndedTick]);

  // Cleanup safely on unmount: discard aborted recording & release mic + unlock global state
  useEffect(() => {
    return () => {
      stopCompare();
      if (timerRef.current) clearInterval(timerRef.current);
      if (autoStopTimerRef.current) clearTimeout(autoStopTimerRef.current);
      if (mediaRecRef.current && mediaRecRef.current.state === 'recording') {
        discardRef.current = true;
        onStopContinuousPlayback?.(true);
        try {
          mediaRecRef.current.stop();
        } catch {
          // ignore
        }
      } else {
        onStopContinuousPlayback?.(false);
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      onRecordingChange?.(false);
    };
  }, []);

  if (!activeSubtitle) {
    return <div className="practice-card">请先在左侧选择一句字幕开始影子跟读。</div>;
  }

  const startRecording = async () => {
    if (acquiringRef.current || recording || uploading) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      onToast('当前浏览器不支持麦克风录音，请在 HTTPS 或本地桌面浏览器中打开');
      return;
    }

    const modeAtStart = shadowMode;
    acquiringRef.current = true;
    stopCompare();
    setBatchSummary(null);

    if (modeAtStart === 'single') {
      onStopAllAudio?.();
      pauseAllOtherMedia(null);
    } else {
      onPrepareContinuousShadowing?.();
    }
    recordingModeRef.current = modeAtStart;
    onRecordingChange?.(true);

    const targetEpId = episodeId;
    const targetSubId = activeSubtitle.id;
    const targetSeqIndex = activeSubtitle.seq_index;
    frozenTargetRef.current = { episodeId: targetEpId, subtitleId: targetSubId };
    discardRef.current = false;

    try {
      let stream;
      if (modeAtStart === 'continuous') {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          });
        } catch {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        }
      } else {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Double-check audio stayed muted while permission prompt resolved
        onStopAllAudio?.();
        pauseAllOtherMedia(null);
      }

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
        if (autoStopTimerRef.current) {
          clearTimeout(autoStopTimerRef.current);
          autoStopTimerRef.current = null;
        }
        if (recordingModeRef.current === 'continuous') {
          onStopContinuousPlayback?.();
        }
        stream.getTracks().forEach((t) => t.stop());
        if (streamRef.current === stream) streamRef.current = null;
        mediaRecRef.current = null;
        setRecording(false);
        onRecordingChange?.(false);

        if (discardRef.current) {
          discardRef.current = false;
          return;
        }

        const mime = rec.mimeType || preferredMime || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type: mime });
        if (blob.size < 200) {
          onToast('录音过短未保存，请重新点击录音并完整跟读');
          return;
        }

        const { episodeId: epId, subtitleId: subId } = frozenTargetRef.current;
        setUploading(true);
        try {
          if (recordingModeRef.current === 'continuous') {
            const endSec = Math.max(0.2, (performance.now() - recStartPerfRef.current) / 1000);
            const rawSegs = segmentsRef.current.map((s) => ({ ...s }));
            if (rawSegs.length > 0) {
              const tail = rawSegs[rawSegs.length - 1];
              if (tail.end_sec == null || tail.end_sec <= tail.start_sec) {
                tail.end_sec = Math.max(tail.start_sec + 0.1, endSec);
              }
            } else {
              rawSegs.push({ subtitle_id: subId, start_sec: 0, end_sec: endSec });
            }
            const payloadSegs = rawSegs.map((s) => ({
              subtitle_id: s.subtitle_id,
              start_sec: Number(s.start_sec.toFixed(3)),
              end_sec: Number(Math.max(s.start_sec + 0.1, s.end_sec).toFixed(3)),
            }));
            const res = await api.uploadContinuousRecordings(epId, payloadSegs, blob);
            if (episodeIdRef.current === epId) {
              setBatchSummary(res);
            }
            const preview = (res.results || [])
              .map((r) => {
                const sc = r.recording?.feedback?.overall_score;
                return `#${r.seq_index} ${typeof sc === 'number' ? `${sc}分` : '已保存'}`;
              })
              .join(' / ');
            onToast(`同步跟读完成：已按句切分保存 ${res.saved_count} 句（${preview}）`);
            onRecordingsChanged();
          } else {
            const res = await api.uploadRecording(epId, subId, blob);
            const fb = res?.recording?.feedback || {};
            if (fb.is_silent) {
              onToast('未检测到有效人声（0 分），请检查麦克风音量后重试');
            } else if (fb.asr_status === 'unavailable') {
              onToast('跟读录音已保存，但本地语音识别模型暂不可用');
            } else if (typeof fb.overall_score === 'number') {
              onToast(`跟读评测完成：综合得分 ${fb.overall_score} 分`);
            } else {
              onToast('跟读录音已保存并完成评测');
            }
            onRecordingsChanged();
          }
        } catch (err) {
          onToast(err.message || '保存跟读录音失败');
        } finally {
          setUploading(false);
        }
      };

      mediaRecRef.current = rec;
      recStartPerfRef.current = performance.now();
      if (modeAtStart === 'continuous') {
        const liveSub = activeSubtitleRef.current;
        segmentsRef.current = [
          {
            subtitle_id: liveSub?.id ?? targetSubId,
            seq_index: liveSub?.seq_index ?? targetSeqIndex,
            start_sec: 0,
            end_sec: null,
          },
        ];
        setTrackedSegments([...segmentsRef.current]);
      } else {
        segmentsRef.current = [];
        setTrackedSegments([]);
      }
      rec.start();
      if (modeAtStart === 'continuous') {
        onStartContinuousPlayback?.();
      }
      setRecording(true);
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((t) => +(t + 0.1).toFixed(1)), 100);
    } catch {
      onStopContinuousPlayback?.(false);
      onRecordingChange?.(false);
      onToast('未获取到麦克风权限，请检查浏览器音频输入授权');
    } finally {
      acquiringRef.current = false;
    }
  };

  const stopRecording = () => {
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
    if (recordingModeRef.current === 'continuous') {
      const endSec = Math.max(0.2, (performance.now() - recStartPerfRef.current) / 1000);
      if (segmentsRef.current.length > 0) {
        const tail = segmentsRef.current[segmentsRef.current.length - 1];
        tail.end_sec = Math.max(tail.start_sec + 0.1, endSec);
      }
      onStopContinuousPlayback?.();
    }
    if (mediaRecRef.current && mediaRecRef.current.state === 'recording') {
      mediaRecRef.current.stop();
    } else {
      setRecording(false);
      onRecordingChange?.(false);
    }
  };

  const handleComparePlay = (rec) => {
    if (recording || uploading) return;
    // Clicking again on the currently comparing item stops comparison immediately
    if (comparingId === rec.id) {
      stopCompare();
      onStopAllAudio?.();
      return;
    }

    stopCompare();
    onStopAllAudio?.();
    pauseAllOtherMedia(null);

    const myGen = compareGenRef.current;
    setComparingId(rec.id);
    setComparePhase('original');

    const cancel = onPlaySentenceOnce?.(
      activeSubtitle,
      () => {
        if (compareGenRef.current !== myGen) return;
        cancelOriginalRef.current = null;
        const el = audioElRef.current;
        if (!el) {
          setComparingId(null);
          setComparePhase('idle');
          return;
        }
        setComparePhase('recording');
        pauseAllOtherMedia(el);
        el.src = rec.audio_url;
        el.currentTime = 0;
        el.onended = () => {
          if (compareGenRef.current === myGen) {
            setComparingId(null);
            setComparePhase('idle');
          }
        };
        el.onpause = () => {
          if (compareGenRef.current === myGen && !el.ended) {
            setComparingId(null);
            setComparePhase('idle');
          }
        };
        el.onerror = () => {
          if (compareGenRef.current === myGen) {
            setComparingId(null);
            setComparePhase('idle');
            onToast('跟读音频播放失败，请重试');
          }
        };
        el.play().catch(() => {
          if (compareGenRef.current === myGen) {
            setComparingId(null);
            setComparePhase('idle');
          }
        });
      },
      () => {
        // Invoked if original playback was paused or interrupted externally before sentence end
        if (compareGenRef.current === myGen) {
          cancelOriginalRef.current = null;
          setComparingId(null);
          setComparePhase('idle');
        }
      }
    );

    cancelOriginalRef.current = cancel || null;
  };

  const handleDeleteRec = async (recId) => {
    if (recording) return;
    if (comparingId === recId) {
      stopCompare();
      onStopAllAudio?.();
    }
    try {
      await api.deleteRecording(recId);
      onRecordingsChanged();
      onToast('已删除跟读录音');
    } catch (err) {
      onToast(err.message || '删除失败');
    }
  };

  const recordings = activeSubtitle.recordings || [];

  return (
    <div className="cards-scroll">
      <audio ref={audioElRef} style={{ display: 'none' }} />

      <div className="practice-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className="pill-3d dark tnum">
              当前跟读句 #{activeSubtitle.seq_index} ({formatTime(activeSubtitle.start_sec)} -{' '}
              {formatTime(activeSubtitle.end_sec)})
            </span>
            <div className="toolbar-group" role="group" aria-label="跟读录制模式">
              <button
                type="button"
                className={`chunk chunk-sm ${shadowMode === 'single' ? 'chunk-dark' : 'chunk-cream'}`}
                disabled={recording || uploading || isRecording}
                aria-pressed={shadowMode === 'single'}
                onClick={() => setShadowMode('single')}
              >
                单句跟读（防串音）
              </button>
              <button
                type="button"
                className={`chunk chunk-sm ${shadowMode === 'continuous' ? 'chunk-dark' : 'chunk-cream'}`}
                disabled={recording || uploading || isRecording}
                aria-pressed={shadowMode === 'continuous'}
                onClick={() => setShadowMode('continuous')}
              >
                同步连续跟读（分句保存）
              </button>
            </div>
          </div>
          <button
            type="button"
            className="chunk chunk-yellow chunk-sm"
            disabled={recording || isRecording}
            onClick={() => {
              stopCompare();
              onPlayOriginalSentence();
            }}
          >
            <Volume2 size={15} />
            <span>听原声示范</span>
          </button>
        </div>

        <p style={{ fontSize: 18, fontWeight: 800, lineHeight: 1.5 }}>{activeSubtitle.source_text}</p>
        {activeSubtitle.ipa && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--ink-sub)' }}>
            {activeSubtitle.ipa}
          </p>
        )}
        <p style={{ fontSize: 14.5, color: 'var(--ink-sub)' }}>{activeSubtitle.target_text}</p>

        {recording && (
          <div
            role="status"
            style={{
              background: recordingModeRef.current === 'continuous' ? '#E9FBF0' : '#FFE4E9',
              color: recordingModeRef.current === 'continuous' ? '#134E2E' : '#850E29',
              borderRadius: 12,
              padding: '8px 12px',
              fontSize: 13.5,
              fontWeight: 800,
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
            }}
          >
            {recordingModeRef.current === 'continuous' ? (
              <>
                <span>
                  同步连续跟读中：原声继续前进，已自动记录 {trackedSegments.length} 句时间切片，停止后将按句切分并分别储存打分。
                </span>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {trackedSegments.map((seg, i) => (
                    <span key={`${seg.subtitle_id}-${i}`} className="pill-3d dark tnum">
                      #{seg.seq_index}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <span>录音中：原声视频与其他按键已自动静音并锁定，录完请点「停止录音」自动打分。</span>
            )}
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginTop: 4 }}>
          {!recording ? (
            <button
              type="button"
              className="chunk chunk-coral"
              disabled={uploading || isRecording}
              onClick={startRecording}
            >
              <Mic size={17} />
              <span>
                {uploading
                  ? recordingModeRef.current === 'continuous'
                    ? '正在按句切分评测...'
                    : '正在评测上传...'
                  : shadowMode === 'continuous'
                    ? '开始同步连续跟读'
                    : '开始跟读录音'}
              </span>
            </button>
          ) : (
            <button type="button" className="chunk chunk-dark" onClick={stopRecording}>
              <Square size={16} />
              <span className="tnum">停止录音 ({elapsed.toFixed(1)}s)</span>
            </button>
          )}
          <span style={{ fontSize: 13.5, color: 'var(--ink-sub)', fontWeight: 700 }}>
            {shadowMode === 'continuous'
              ? '建议佩戴耳机：开始后随原文连续跟读多句，停止后自动按句切分并分别存入对应句子下逐句打分。'
              : '先听原声示范，再点击红色录音键跟读；录音时会自动静音防串音并检测真实语音准确度。'}
          </span>
        </div>
      </div>

      {batchSummary && (batchSummary.results || []).length > 0 && (
        <div
          className="practice-card"
          data-testid="continuous-shadow-summary"
          style={{ background: '#F4FBF6', border: '2px solid #2A7E4B' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <strong style={{ fontSize: 15 }}>
              本次同步跟读已自动分句保存 {batchSummary.saved_count} 句（总时长 {batchSummary.total_duration_sec}s）
            </strong>
            <button
              type="button"
              className="chunk chunk-cream chunk-sm"
              onClick={() => setBatchSummary(null)}
            >
              收起汇总
            </button>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {batchSummary.results.map((item) => {
              const sc = item.recording?.feedback?.overall_score;
              return (
                <button
                  key={`${item.subtitle_id}-${item.recording?.id}`}
                  type="button"
                  className="chunk chunk-sm chunk-yellow tnum"
                  onClick={() => onSelectSubtitle?.(item.subtitle_id)}
                >
                  #{item.seq_index} {typeof sc === 'number' ? `${sc}分` : '已保存'}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {recordings.length === 0 ? (
        <div className="practice-card" style={{ alignItems: 'center', padding: 24 }}>
          <strong>本句还没有跟读记录</strong>
          <p style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>
            点击上方红色「开始跟读录音」按钮，录完后可一键「原声+跟读对比」顺序交替对比。
          </p>
        </div>
      ) : (
        recordings.map((rec, idx) => {
          const fb = rec.feedback || {};
          const hasScore = typeof fb.overall_score === 'number';
          const isComparingThis = comparingId === rec.id;
          const compareLabel = !isComparingThis
            ? '原声+跟读对比'
            : comparePhase === 'original'
              ? '停止对比（原声中）'
              : '停止对比（跟读中）';

          return (
            <div key={rec.id} className="practice-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div
                    className="score-ring tnum"
                    style={
                      !hasScore || fb.overall_score === 0
                        ? { background: '#850E29', color: '#FFFFFF' }
                        : undefined
                    }
                  >
                    <span>{hasScore ? fb.overall_score : '--'}</span>
                    <span style={{ fontSize: 10, fontWeight: 700, color: '#EAE4F8' }}>
                      {hasScore ? '分' : '待评'}
                    </span>
                  </div>
                  <div>
                    <div style={{ fontWeight: 900, fontSize: 15, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span>第 {recordings.length - idx} 次跟读记录</span>
                      <span className="pill-3d">{fb.engine || '语音评测'}</span>
                      {typeof fb.word_accuracy === 'number' && (
                        <span className="pill-3d mint tnum">词准 {fb.word_accuracy}%</span>
                      )}
                      {typeof fb.pace_score === 'number' && !fb.is_silent && (
                        <span className="pill-3d tnum">语速 {fb.pace_score}</span>
                      )}
                    </div>
                    <p style={{ fontSize: 13.5, color: 'var(--ink-sub)', marginTop: 3 }}>
                      {fb.pace_comment || `录音时长 ${rec.duration_sec}s`}
                    </p>
                  </div>
                </div>

                <div className="toolbar-group">
                  <button
                    type="button"
                    className={`chunk chunk-sm ${isComparingThis ? 'chunk-coral' : 'chunk-mint'}`}
                    disabled={recording || uploading || isRecording}
                    onClick={() => handleComparePlay(rec)}
                  >
                    {isComparingThis ? <Square size={13} /> : <Play size={14} />}
                    <span>{compareLabel}</span>
                  </button>
                  <button
                    type="button"
                    className="chunk chunk-white chunk-sm"
                    disabled={recording || isRecording}
                    onClick={() => handleDeleteRec(rec.id)}
                    title="删除录音"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              <audio
                controls
                src={rec.audio_url}
                style={{ width: '100%', height: 36 }}
                onPlay={(e) => {
                  if (recording || isRecording) {
                    e.currentTarget.pause();
                    return;
                  }
                  stopCompare();
                  onStopAllAudio?.(e.currentTarget);
                  pauseAllOtherMedia(e.currentTarget);
                }}
              />

              {fb.asr_warning && (
                <div
                  style={{
                    fontSize: 13.5,
                    background: '#FFE4E9',
                    color: '#850E29',
                    padding: '8px 12px',
                    borderRadius: 12,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    fontWeight: 700,
                  }}
                >
                  <AlertTriangle size={16} style={{ flexShrink: 0 }} />
                  <span>{fb.asr_warning}</span>
                </div>
              )}

              {fb.recognized_text && (
                <div style={{ fontSize: 13.5, background: 'var(--panel-bg)', padding: '8px 12px', borderRadius: 12 }}>
                  <strong>识别转写：</strong>
                  {fb.recognized_text}
                </div>
              )}

              {(fb.missing_words || []).length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 800, color: 'var(--ink-sub)' }}>漏读/待加强词：</span>
                  {fb.missing_words.map((w, i) => (
                    <span key={`${w}-${i}`} className="pill-3d coral">
                      {w}
                    </span>
                  ))}
                </div>
              )}

              {(fb.tips || []).length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {fb.tips.map((tip, i) => (
                    <span key={i} style={{ fontSize: 13, color: 'var(--ink-sub)' }}>
                      {tip}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

/* ===================== 2. CLOZE RECALL PANEL ===================== */
function tokenizeForCloze(sub) {
  // Parse annotated HTML to turn lex-term spans into cloze blanks; decode ALL HTML entities cleanly
  const parts = [];
  const regex = /<span class="lex-term"[^>]*>(.*?)<\/span>/g;
  let last = 0;
  let m;
  let blankIdx = 0;
  const htmlStr = sub.source_html || sub.source_text;
  while ((m = regex.exec(htmlStr)) !== null) {
    if (m.index > last) {
      const plainText = decodeHtmlEntities(htmlStr.slice(last, m.index).replace(/<[^>]+>/g, ''));
      parts.push({ type: 'text', text: plainText });
    }
    const cleanWord = decodeHtmlEntities(m[1].replace(/<[^>]+>/g, ''));
    parts.push({ type: 'blank', text: cleanWord, key: `${sub.id}-${blankIdx++}` });
    last = m.index + m[0].length;
  }
  if (last < htmlStr.length) {
    const tailText = decodeHtmlEntities(htmlStr.slice(last).replace(/<[^>]+>/g, ''));
    parts.push({ type: 'text', text: tailText });
  }
  if (blankIdx === 0) {
    // Fallback: blank up to 3 long words
    const tokens = decodeHtmlEntities(sub.source_text).split(/(\s+)/);
    return tokens.map((tok, i) => {
      if (/^[A-Za-z]{6,}$/.test(tok) && blankIdx < 3) {
        blankIdx += 1;
        return { type: 'blank', text: tok, key: `${sub.id}-fb-${i}` };
      }
      return { type: 'text', text: tok };
    });
  }
  return parts;
}

export function ClozePanel({
  episodeId,
  subtitles,
  activeSubtitleId,
  onSelectSubtitle,
  fontScale,
}) {
  const [revealed, setRevealed] = useState({});

  useEffect(() => {
    setRevealed({});
  }, [episodeId]);

  const parsedMap = useMemo(() => {
    const map = {};
    for (const s of subtitles) map[s.id] = tokenizeForCloze(s);
    return map;
  }, [subtitles]);

  const allKeys = useMemo(() => {
    const keys = [];
    for (const s of subtitles) {
      for (const p of parsedMap[s.id] || []) {
        if (p.type === 'blank') keys.push(p.key);
      }
    }
    return keys;
  }, [subtitles, parsedMap]);

  const revealedCount = allKeys.filter((k) => revealed[k]).length;

  const revealAll = () => {
    const next = {};
    allKeys.forEach((k) => {
      next[k] = true;
    });
    setRevealed(next);
  };

  return (
    <>
      <div className="sub-toolbar">
        <div className="toolbar-group">
          <span className="pill-3d dark tnum">
            已回忆 {revealedCount} / {allKeys.length} 个重点词块
          </span>
        </div>
        <div className="toolbar-group">
          <button type="button" className="chunk chunk-mint chunk-sm" onClick={revealAll}>
            <Eye size={14} />
            <span>全部揭晓</span>
          </button>
          <button
            type="button"
            className="chunk chunk-white chunk-sm"
            onClick={() => setRevealed({})}
          >
            <EyeOff size={14} />
            <span>重新遮罩</span>
          </button>
        </div>
      </div>

      <div className="cards-scroll">
        {subtitles.length === 0 ? (
          <div className="practice-card" style={{ alignItems: 'center', padding: 28 }}>
            <strong>当前篇目暂无可挖空字幕</strong>
            <p style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>
              可切换到「校对」页签添加或导入双语字幕后再进行词块挖空回忆。
            </p>
          </div>
        ) : (
          subtitles.map((sub) => {
            const isActive = sub.id === activeSubtitleId;
            const parts = parsedMap[sub.id] || [];
            return (
              <div
                key={sub.id}
                className={`cue-card ${isActive ? 'active' : ''}`}
                onClick={() => onSelectSubtitle(sub.id, true)}
              >
                <div className="cue-top tnum">
                  <span>
                    #{sub.seq_index} {formatTime(sub.start_sec)}
                  </span>
                  <span>点击黑色键帽揭晓答案</span>
                </div>
                <div className="cue-en" style={{ fontSize: `${Math.round(17 * fontScale)}px` }}>
                  {parts.map((part, idx) =>
                    part.type === 'text' ? (
                      <span key={idx}>{part.text}</span>
                    ) : (
                      <button
                        key={part.key}
                        type="button"
                        className={`cloze-cap ${revealed[part.key] ? 'open' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setRevealed((prev) => ({ ...prev, [part.key]: !prev[part.key] }));
                        }}
                      >
                        {part.text}
                      </button>
                    )
                  )}
                </div>
                {sub.target_text && <div className="cue-cn">{sub.target_text}</div>}
              </div>
            );
          })
        )}
      </div>
    </>
  );
}

/* ===================== 3. DICTATION GRADING PANEL ===================== */
export function DictationPanel({
  episodeId,
  subtitles,
  activeSubtitle,
  onSelectSubtitle,
  onPlayCurrent,
}) {
  const [dictMode, setDictMode] = useState('keyword'); // keyword | full
  const [keywordInputs, setKeywordInputs] = useState({});
  const [showAnswers, setShowAnswers] = useState(false);
  const [fullDrafts, setFullDrafts] = useState({});
  const [checkedFull, setCheckedFull] = useState({});

  useEffect(() => {
    setKeywordInputs({});
    setFullDrafts({});
    setCheckedFull({});
  }, [episodeId]);

  const parsedMap = useMemo(() => {
    const map = {};
    for (const s of subtitles) map[s.id] = tokenizeForCloze(s);
    return map;
  }, [subtitles]);

  const keywordStats = useMemo(() => {
    let total = 0;
    let correct = 0;
    for (const s of subtitles) {
      for (const p of parsedMap[s.id] || []) {
        if (p.type === 'blank') {
          total += 1;
          const typed = normalizeWord(keywordInputs[p.key] || '');
          const expected = normalizeWord(p.text);
          if (typed && typed === expected) correct += 1;
        }
      }
    }
    return { total, correct, pct: total ? Math.round((correct / total) * 100) : 0 };
  }, [subtitles, parsedMap, keywordInputs]);

  const gradeFullSentence = (sub) => {
    const expectedWords = decodeHtmlEntities(sub.source_text).split(/\s+/).filter(Boolean);
    const userWords = (fullDrafts[sub.id] || '').trim().split(/\s+/).filter(Boolean);
    return alignDictationWords(expectedWords, userWords);
  };

  return (
    <>
      <div className="sub-toolbar">
        <div className="toolbar-group">
          <button
            type="button"
            className={`seg-pill ${dictMode === 'keyword' ? 'active' : ''}`}
            onClick={() => setDictMode('keyword')}
          >
            关键词听写
          </button>
          <button
            type="button"
            className={`seg-pill ${dictMode === 'full' ? 'active' : ''}`}
            onClick={() => setDictMode('full')}
          >
            全句听写批改
          </button>
        </div>

        <div className="toolbar-group">
          {dictMode === 'keyword' && (
            <span className="pill-3d mint tnum">
              正确率 {keywordStats.pct}% ({keywordStats.correct}/{keywordStats.total})
            </span>
          )}
          <button
            type="button"
            className="chunk chunk-white chunk-sm"
            onClick={() => setShowAnswers((v) => !v)}
          >
            <Eye size={14} />
            <span>{showAnswers ? '隐藏参考' : '查看参考'}</span>
          </button>
          <button
            type="button"
            className="chunk chunk-white chunk-sm"
            onClick={() => {
              setKeywordInputs({});
              setFullDrafts({});
              setCheckedFull({});
            }}
          >
            <RotateCcw size={14} />
            <span>清空重填</span>
          </button>
        </div>
      </div>

      {dictMode === 'keyword' ? (
        <div className="cards-scroll">
          {subtitles.length === 0 ? (
            <div className="practice-card" style={{ alignItems: 'center', padding: 28 }}>
              <strong>当前篇目暂无可听写字幕</strong>
              <p style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>
                可切换到「校对」页签添加或导入双语字幕后再开始听写训练。
              </p>
            </div>
          ) : (
            subtitles.map((sub) => {
              const isActive = activeSubtitle?.id === sub.id;
              const parts = parsedMap[sub.id] || [];
              return (
                <div
                  key={sub.id}
                  className={`cue-card ${isActive ? 'active' : ''}`}
                  onClick={() => onSelectSubtitle(sub.id, true)}
                >
                  <div className="cue-top tnum">
                    <span>
                      #{sub.seq_index} {formatTime(sub.start_sec)}
                    </span>
                    <span>听音填入空缺词块</span>
                  </div>
                  <div className="cue-en" style={{ fontSize: 16 }}>
                    {parts.map((part, idx) => {
                      if (part.type === 'text') return <span key={idx}>{part.text}</span>;
                      const val = keywordInputs[part.key] || '';
                      const isFilled = val.trim().length > 0;
                      const isOk = isFilled && normalizeWord(val) === normalizeWord(part.text);
                      const cls = isFilled ? (isOk ? 'ok' : 'err') : '';
                      return (
                        <span key={part.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <input
                            type="text"
                            className={`dict-cap ${cls}`}
                            style={{ width: `${Math.max(88, part.text.length * 11)}px` }}
                            value={val}
                            placeholder={showAnswers ? part.text : '...'}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) =>
                              setKeywordInputs((prev) => ({ ...prev, [part.key]: e.target.value }))
                            }
                          />
                        </span>
                      );
                    })}
                  </div>
                  {sub.target_text && <div className="cue-cn">{sub.target_text}</div>}
                </div>
              );
            })
          )}
        </div>
      ) : (
        <div className="cards-scroll">
          {activeSubtitle ? (
            <div className="practice-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <span className="pill-3d dark tnum">
                  全句听写 #{activeSubtitle.seq_index} ({formatTime(activeSubtitle.start_sec)} -{' '}
                  {formatTime(activeSubtitle.end_sec)})
                </span>
                <button
                  type="button"
                  className="chunk chunk-yellow chunk-sm"
                  onClick={onPlayCurrent}
                >
                  <Volume2 size={15} />
                  <span>重听本句</span>
                </button>
              </div>

              <p style={{ fontSize: 14, color: 'var(--ink-sub)', fontWeight: 700 }}>
                中文提示：{activeSubtitle.target_text}
              </p>

              <textarea
                className="textarea-3d"
                placeholder="反复听本句原声，在此完整输入你听到的英文句子..."
                value={fullDrafts[activeSubtitle.id] || ''}
                onChange={(e) => {
                  const val = e.target.value;
                  setFullDrafts((prev) => ({ ...prev, [activeSubtitle.id]: val }));
                  setCheckedFull((prev) => {
                    if (!prev[activeSubtitle.id]) return prev;
                    const next = { ...prev };
                    delete next[activeSubtitle.id];
                    return next;
                  });
                }}
              />

              <div className="toolbar-group">
                <button
                  type="button"
                  className="chunk chunk-dark chunk-sm"
                  onClick={() =>
                    setCheckedFull((prev) => ({
                      ...prev,
                      [activeSubtitle.id]: gradeFullSentence(activeSubtitle),
                    }))
                  }
                >
                  <CheckCircle2 size={15} />
                  <span>立即逐词核对</span>
                </button>
                {showAnswers && (
                  <span style={{ fontSize: 14, fontWeight: 800, color: 'var(--ink-sub)' }}>
                    参考原句：{activeSubtitle.source_text}
                  </span>
                )}
              </div>

              {checkedFull[activeSubtitle.id] && (
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
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className="pill-3d mint tnum">
                      词级准确率 {checkedFull[activeSubtitle.id].accuracy}%
                    </span>
                    <span style={{ fontSize: 13, color: 'var(--ink-sub)', fontWeight: 700 }}>
                      绿色为命中，红色括号内为参考原词或多余词
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {checkedFull[activeSubtitle.id].items.map((it, idx) => (
                      <span
                        key={idx}
                        className={`pill-3d ${it.ok ? 'mint' : 'coral'}`}
                        style={{ fontSize: 14 }}
                      >
                        {it.ok
                          ? it.expected
                          : it.extra
                            ? `多余：${it.got}`
                            : `${it.got || '漏写'} (${it.expected})`}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="practice-card">请先选择一句字幕。</div>
          )}
        </div>
      )}
    </>
  );
}
