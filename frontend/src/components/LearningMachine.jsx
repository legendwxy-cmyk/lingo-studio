import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Download,
  Edit3,
  Globe2,
  Maximize2,
  Mic,
  Minus,
  Pause,
  PictureInPicture2,
  Play,
  Plus,
  Printer,
  SkipBack,
  SkipForward,
  Sparkles,
  Star,
  Volume2,
} from 'lucide-react';
import { api } from '../api';
import { formatTime, speakWord, stopSpeechSynthesis } from '../utils/speech';
import { AiCoachPanel, ProofreadEditorPanel } from './AiAndEditorPanels';
import LexiconPanel from './LexiconPanel';
import { ClozePanel, DictationPanel, ShadowingPanel } from './PracticeModes';
import PrintPreviewModal from './PrintPreviewModal';

const SPEEDS = [0.5, 0.75, 0.85, 1.0, 1.25, 1.5, 2.0];
const DIAL_ANGLES = [-120, -80, -40, 0, 40, 80, 120];

const MODES = [
  { id: 'bilingual', label: '双语精听' },
  { id: 'shadow', label: '跟读' },
  { id: 'cloze', label: '挖空' },
  { id: 'dictation', label: '听写' },
  { id: 'lexicon', label: '词典' },
  { id: 'ai', label: 'AI 精讲' },
  { id: 'editor', label: '校对' },
];

function escapeHtmlFallback(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function pauseOtherDomMedia(exceptEl = null) {
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

export default function LearningMachine({
  detail,
  targetSubtitleId,
  onClearTargetSubtitle,
  onReloadEpisode,
  onJumpToOccurrence,
  onDeckChanged,
  onOpenLibrary,
  onToast,
  isRecording = false,
  onRecordingChange,
  shortcutsDisabled = false,
}) {
  const episode = detail?.episode || null;
  const subtitles = detail?.subtitles || [];
  const entries = detail?.entries || [];

  const mediaRef = useRef(null);
  const pauseGuardRef = useRef(false);
  const pausedBySentenceEndRef = useRef(false);
  const oneShotPausedRef = useRef(false);
  const stopAtSecRef = useRef(null);
  const onStopAtFinishedRef = useRef(null);
  const onStopAtCancelledRef = useRef(null);
  const playbackGenRef = useRef(0);
  const pendingSeekRef = useRef(null);
  const cueRefs = useRef({});
  const lastSavedPosRef = useRef(0);
  const prevEpisodeIdRef = useRef(null);
  const activeSubRef = useRef(null);

  const [mode, setMode] = useState('bilingual');
  const [captionMode, setCaptionMode] = useState('bilingual'); // bilingual | en | cn
  const [fontScale, setFontScale] = useState(1.0);

  const [activeSubId, setActiveSubId] = useState(null);
  const [selectedEntryId, setSelectedEntryId] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speedIdx, setSpeedIdx] = useState(3); // 1.0x

  // 6 Physical 3D Toggle Switches
  const [singleLoop, setSingleLoop] = useState(false);
  const [pausePerSentence, setPausePerSentence] = useState(false);
  const [blindMode, setBlindMode] = useState(false);
  const [showIpa, setShowIpa] = useState(true);
  const [abLoop, setAbLoop] = useState(false);
  const [showScreenCaption, setShowScreenCaption] = useState(true);

  const [abRange, setAbRange] = useState([0, 1]);
  const [printOpen, setPrintOpen] = useState(false);
  const [continuousShadowing, setContinuousShadowing] = useState(false);
  const continuousShadowingRef = useRef(false);
  const [mediaEndedTick, setMediaEndedTick] = useState(0);

  const clearOneShotStop = useCallback(() => {
    const cancelCb = onStopAtCancelledRef.current;
    playbackGenRef.current += 1;
    oneShotPausedRef.current = false;
    stopAtSecRef.current = null;
    onStopAtFinishedRef.current = null;
    onStopAtCancelledRef.current = null;
    if (cancelCb) cancelCb();
  }, []);

  const stopAllAudio = useCallback((exceptEl = null) => {
    clearOneShotStop();
    pausedBySentenceEndRef.current = false;
    if (mediaRef.current && mediaRef.current !== exceptEl && !mediaRef.current.paused) {
      try {
        mediaRef.current.pause();
      } catch {
        // ignore
      }
    }
    pauseOtherDomMedia(exceptEl);
    if (!exceptEl || mediaRef.current !== exceptEl) {
      setIsPlaying(false);
    }
  }, [clearOneShotStop]);

  // Reset loop & playback state when switching to a different episode
  useEffect(() => {
    if (episode?.id !== prevEpisodeIdRef.current) {
      prevEpisodeIdRef.current = episode?.id ?? null;
      clearOneShotStop();
      continuousShadowingRef.current = false;
      setContinuousShadowing(false);
      pausedBySentenceEndRef.current = false;
      pauseGuardRef.current = false;
      setAbLoop(false);
      setSingleLoop(false);
      setIsPlaying(false);
      setCurrentTime(0);
      setDuration(0);
      setAbRange([0, Math.min(2, Math.max(0, subtitles.length - 1))]);
    }
  }, [episode?.id, clearOneShotStop]);

  // Sync active subtitle, handle cross-episode jump & restore last playback position cleanly
  useEffect(() => {
    if (!subtitles.length) {
      setActiveSubId(null);
      activeSubRef.current = null;
      setAbLoop(false);
      return;
    }
    if (targetSubtitleId && subtitles.some((s) => s.id === targetSubtitleId)) {
      const found = subtitles.find((s) => s.id === targetSubtitleId);
      setMode('bilingual');
      setActiveSubId(found.id);
      activeSubRef.current = found;
      if (found.entry_ids?.length) {
        setSelectedEntryId(found.entry_ids[0]);
      }
      const targetSec = Math.max(0, found.start_sec + 0.01);
      setCurrentTime(found.start_sec);
      if (mediaRef.current && mediaRef.current.readyState >= 1) {
        clearOneShotStop();
        pauseOtherDomMedia(mediaRef.current);
        mediaRef.current.currentTime = targetSec;
        mediaRef.current.play().catch(() => {});
        pendingSeekRef.current = null;
      } else {
        pendingSeekRef.current = { sec: targetSec, autoPlay: true };
      }
      onClearTargetSubtitle();
    } else if (!activeSubId || !subtitles.some((s) => s.id === activeSubId)) {
      const savedPos = Number(episode?.last_position_sec || 0);
      if (savedPos > 1.0) {
        const matched =
          subtitles.find((s) => savedPos >= s.start_sec && savedPos <= s.end_sec + 0.5) || subtitles[0];
        setActiveSubId(matched.id);
        activeSubRef.current = matched;
        setCurrentTime(savedPos);
        if (mediaRef.current && mediaRef.current.readyState >= 1) {
          mediaRef.current.currentTime = savedPos;
          pendingSeekRef.current = null;
        } else {
          pendingSeekRef.current = { sec: savedPos, autoPlay: false };
        }
      } else {
        setActiveSubId(subtitles[0].id);
        activeSubRef.current = subtitles[0];
      }
    }
    setAbRange(([a, b]) => {
      const maxIdx = Math.max(0, subtitles.length - 1);
      const nextA = Math.min(a, maxIdx);
      const nextB = Math.min(Math.max(nextA, b), maxIdx);
      return [nextA, nextB];
    });
    if (subtitles.length < 2) setAbLoop(false);
    lastSavedPosRef.current = Number(episode?.last_position_sec || 0);
  }, [episode?.id, subtitles.length, targetSubtitleId]);

  useEffect(() => {
    if (entries.length && (!selectedEntryId || !entries.some((e) => e.id === selectedEntryId))) {
      setSelectedEntryId(entries[0].id);
    } else if (!entries.length) {
      setSelectedEntryId(null);
    }
  }, [episode?.id, entries.length]);

  // Smoothly keep the active subtitle card in view during playback
  useEffect(() => {
    if (!activeSubId || mode !== 'bilingual') return;
    const node = cueRefs.current[activeSubId];
    if (node && isPlaying) {
      node.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [activeSubId, isPlaying, mode]);

  const activeIdx = useMemo(() => {
    const idx = subtitles.findIndex((s) => s.id === activeSubId);
    return idx >= 0 ? idx : 0;
  }, [subtitles, activeSubId]);

  const activeSubtitle = subtitles[activeIdx] || null;
  activeSubRef.current = activeSubtitle;
  const activeSpokenWord = useMemo(() => {
    if (!isPlaying || !activeSubtitle?.words?.length) return '';
    const hit = activeSubtitle.words.find(
      (w) => currentTime >= w.start - 0.05 && currentTime <= w.end + 0.08
    );
    return hit?.word || '';
  }, [isPlaying, activeSubtitle, currentTime]);

  const selectedEntry = useMemo(
    () => entries.find((e) => e.id === selectedEntryId) || entries[0] || null,
    [entries, selectedEntryId]
  );

  const hasRecordings = useMemo(
    () => subtitles.some((s) => (s.recordings || []).length > 0),
    [subtitles]
  );

  // Apply playbackRate whenever speed or episode changes
  useEffect(() => {
    if (mediaRef.current) {
      mediaRef.current.playbackRate = SPEEDS[speedIdx];
    }
  }, [speedIdx, episode?.id]);

  // Apply pending seek once media metadata loads
  const handleLoadedMetadata = useCallback(
    (e) => {
      const el = e.currentTarget;
      el.playbackRate = SPEEDS[speedIdx];
      setDuration(el.duration || episode?.duration_sec || 0);
      if (pendingSeekRef.current) {
        const { sec, autoPlay } = pendingSeekRef.current;
        pendingSeekRef.current = null;
        el.currentTime = Math.min(sec, Math.max(0, (el.duration || sec) - 0.05));
        setCurrentTime(el.currentTime);
        if (autoPlay && !isRecording) {
          pauseOtherDomMedia(el);
          el.play().catch(() => {});
        }
      }
    },
    [speedIdx, episode?.duration_sec, isRecording]
  );

  const seekAndPlaySubtitle = useCallback(
    (subId, shouldPlay = true) => {
      if (isRecording) return;
      const target = subtitles.find((s) => s.id === subId);
      if (!target) return;
      clearOneShotStop();
      pauseGuardRef.current = false;
      pausedBySentenceEndRef.current = false;
      activeSubRef.current = target;
      setActiveSubId(target.id);
      if (target.entry_ids?.length) {
        setSelectedEntryId(target.entry_ids[0]);
      }
      if (mediaRef.current) {
        mediaRef.current.currentTime = Math.max(0, target.start_sec + 0.01);
        setCurrentTime(target.start_sec);
        if (shouldPlay) {
          pauseOtherDomMedia(mediaRef.current);
          mediaRef.current.play().catch(() => {});
        }
      }
    },
    [subtitles, isRecording, clearOneShotStop]
  );

  /**
   * Play ONLY [sub.start_sec, sub.end_sec] at the active playbackRate, pause precisely at end_sec,
   * and invoke onFinished cleanly (used by Shadowing Original Preview & Compare Playback).
   */
  const playSentenceOnce = useCallback(
    (sub, onFinished = null, onCancel = null) => {
      if (isRecording || !sub || !mediaRef.current) {
        return () => {};
      }
      clearOneShotStop();
      const myGen = playbackGenRef.current;
      const el = mediaRef.current;

      pauseGuardRef.current = false;
      pausedBySentenceEndRef.current = false;
      activeSubRef.current = sub;
      setActiveSubId(sub.id);
      stopAtSecRef.current = sub.end_sec;
      onStopAtFinishedRef.current = () => {
        if (playbackGenRef.current === myGen) {
          onFinished?.();
        }
      };
      onStopAtCancelledRef.current = () => {
        onCancel?.();
      };

      pauseOtherDomMedia(el);
      el.currentTime = Math.max(0, sub.start_sec + 0.01);
      setCurrentTime(sub.start_sec);
      el.play().catch(() => {
        if (playbackGenRef.current === myGen) {
          stopAtSecRef.current = null;
          onStopAtFinishedRef.current = null;
          onStopAtCancelledRef.current = null;
          onCancel?.();
        }
      });

      return () => {
        if (playbackGenRef.current === myGen) {
          stopAtSecRef.current = null;
          onStopAtFinishedRef.current = null;
          onStopAtCancelledRef.current = null;
          if (mediaRef.current && !mediaRef.current.paused) {
            mediaRef.current.pause();
          }
        }
      };
    },
    [isRecording, clearOneShotStop]
  );

  const togglePlayPause = useCallback(() => {
    if (isRecording) return;
    const el = mediaRef.current;
    if (!el) return;
    clearOneShotStop();
    if (el.paused) {
      pauseGuardRef.current = false;
      // If previously auto-paused by 逐句暂停 at sentence end, pressing Play/Space advances to next sentence!
      if (pausePerSentence && pausedBySentenceEndRef.current && subtitles.length > 0) {
        pausedBySentenceEndRef.current = false;
        const refIdx = activeSubRef.current
          ? subtitles.findIndex((s) => s.id === activeSubRef.current.id)
          : -1;
        const baseIdx = refIdx >= 0 ? refIdx : activeIdx;
        const nextIdx = baseIdx + 1 < subtitles.length ? baseIdx + 1 : 0;
        const nextSub = subtitles[nextIdx];
        if (nextSub) {
          activeSubRef.current = nextSub;
          setActiveSubId(nextSub.id);
          el.currentTime = Math.max(0, nextSub.start_sec + 0.01);
          setCurrentTime(nextSub.start_sec);
        }
      } else if (
        singleLoop &&
        activeSubtitle &&
        (el.currentTime < activeSubtitle.start_sec - 0.1 || el.currentTime >= activeSubtitle.end_sec - 0.06)
      ) {
        el.currentTime = Math.max(0, activeSubtitle.start_sec + 0.01);
      }
      pauseOtherDomMedia(el);
      el.play().catch(() => {});
    } else {
      el.pause();
    }
  }, [isRecording, clearOneShotStop, pausePerSentence, subtitles, activeIdx, singleLoop, activeSubtitle]);

  const stepSentence = useCallback(
    (delta) => {
      if (isRecording || !subtitles.length) return;
      const nextIdx = Math.max(0, Math.min(subtitles.length - 1, activeIdx + delta));
      seekAndPlaySubtitle(subtitles[nextIdx].id, true);
    },
    [isRecording, subtitles, activeIdx, seekAndPlaySubtitle]
  );

  const replayCurrentSentence = useCallback(() => {
    if (isRecording || !activeSubtitle) return;
    seekAndPlaySubtitle(activeSubtitle.id, true);
  }, [isRecording, activeSubtitle, seekAndPlaySubtitle]);

  const playActiveSentenceOnce = useCallback(() => {
    if (isRecording || !activeSubtitle) return;
    playSentenceOnce(activeSubtitle, null);
  }, [isRecording, activeSubtitle, playSentenceOnce]);

  const prepareContinuousShadowing = useCallback(() => {
    continuousShadowingRef.current = true;
    setContinuousShadowing(true);
  }, []);

  const startContinuousShadowPlayback = useCallback(() => {
    const el = mediaRef.current;
    continuousShadowingRef.current = true;
    setContinuousShadowing(true);
    if (!el) return;
    clearOneShotStop();
    pauseGuardRef.current = false;
    pausedBySentenceEndRef.current = false;
    pauseOtherDomMedia(el);
    const curSub = activeSubRef.current || activeSubtitle;
    if (el.paused || el.ended) {
      if (
        curSub &&
        (el.ended || el.currentTime < curSub.start_sec - 0.1 || el.currentTime >= curSub.end_sec - 0.1)
      ) {
        el.currentTime = Math.max(0, curSub.start_sec + 0.01);
        setCurrentTime(curSub.start_sec);
      }
      el.play().catch(() => {});
    }
  }, [clearOneShotStop, activeSubtitle]);

  const stopContinuousShadowPlayback = useCallback((pauseMedia = true) => {
    const wasContinuous = continuousShadowingRef.current;
    continuousShadowingRef.current = false;
    setContinuousShadowing(false);
    if (pauseMedia && wasContinuous && mediaRef.current && !mediaRef.current.paused) {
      try {
        mediaRef.current.pause();
      } catch {
        // ignore
      }
    }
  }, []);

  // Global Keyboard Shortcuts in Learning Machine (disabled behind modals, inputs, buttons, or recording)
  useEffect(() => {
    const onKeyDown = (e) => {
      if (shortcutsDisabled || printOpen || isRecording) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target;
      const tag = (target?.tagName || '').toLowerCase();
      if (
        tag === 'input' ||
        tag === 'textarea' ||
        tag === 'select' ||
        tag === 'button' ||
        tag === 'a' ||
        target?.isContentEditable ||
        target?.getAttribute?.('role') === 'button'
      ) {
        return;
      }
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlayPause();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        stepSentence(-1);
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        stepSentence(1);
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        replayCurrentSentence();
      } else if (e.key === 'l' || e.key === 'L') {
        e.preventDefault();
        setSingleLoop((v) => !v);
        setAbLoop(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [shortcutsDisabled, printOpen, isRecording, togglePlayPause, stepSentence, replayCurrentSentence]);

  const persistPosition = useCallback(
    (sec) => {
      if (!episode?.id) return;
      const rounded = +Number(sec || 0).toFixed(2);
      if (Math.abs(rounded - lastSavedPosRef.current) < 1.0) return;
      lastSavedPosRef.current = rounded;
      api.patchEpisode(episode.id, { last_position_sec: rounded }).catch(() => {});
    },
    [episode?.id]
  );

  const handleTimeUpdate = () => {
    const el = mediaRef.current;
    if (!el) return;
    const isContShadow = continuousShadowingRef.current;
    if (isRecording && !isContShadow) {
      if (!el.paused) el.pause();
      return;
    }
    if (el.seeking) return;
    const t = el.currentTime;
    setCurrentTime(t);

    if (Math.abs(t - lastSavedPosRef.current) >= 6.0) {
      persistPosition(t);
    }

    const curSub = activeSubRef.current || activeSubtitle;

    // Highest priority: exact one-shot sentence playback (Shadowing Original Demo / Compare)
    if (stopAtSecRef.current !== null && !el.paused) {
      if (t >= stopAtSecRef.current - 0.05) {
        const doneCb = onStopAtFinishedRef.current;
        stopAtSecRef.current = null;
        onStopAtFinishedRef.current = null;
        onStopAtCancelledRef.current = null;
        oneShotPausedRef.current = true;
        el.pause();
        doneCb?.();
        return;
      }
      // Do NOT auto-advance activeSubId during one-shot preview/compare!
      return;
    }

    if (!isContShadow && singleLoop && curSub && !el.paused) {
      if (t >= curSub.end_sec - 0.04) {
        el.currentTime = Math.max(0, curSub.start_sec + 0.01);
        return;
      }
    }

    if (!isContShadow && abLoop && subtitles.length > 1 && !el.paused) {
      const startSub = subtitles[Math.min(abRange[0], subtitles.length - 1)];
      const endSub = subtitles[Math.min(abRange[1], subtitles.length - 1)];
      if (startSub && endSub && t >= endSub.end_sec - 0.04) {
        el.currentTime = Math.max(0, startSub.start_sec + 0.01);
        activeSubRef.current = startSub;
        setActiveSubId(startSub.id);
        return;
      }
    }

    if (!isContShadow && pausePerSentence && curSub && !el.paused && !pauseGuardRef.current) {
      if (t >= curSub.end_sec - 0.04) {
        pauseGuardRef.current = true;
        pausedBySentenceEndRef.current = true;
        el.pause();
        return;
      }
    }

    // Track currently spoken sentence: keep curSub if it strictly contains t,
    // prefer strict half-open [start_sec, end_sec) match so touching timestamps
    // never yank activeSubId backward, and ignore trailing timeupdates after auto-pause or one-shot stop.
    if ((isContShadow || !singleLoop) && !pausedBySentenceEndRef.current && !oneShotPausedRef.current) {
      const curStillMatches =
        curSub && t >= curSub.start_sec && t < curSub.end_sec;
      if (!curStillMatches) {
        const found =
          subtitles.find((s) => t >= s.start_sec && t < s.end_sec) ||
          subtitles.find((s) => t >= s.start_sec - 0.08 && t <= s.end_sec + 0.08);
        if (found && found.id !== (curSub?.id ?? activeSubId)) {
          const isStalePrevCue =
            curSub &&
            found.end_sec <= curSub.start_sec + 0.02 &&
            t >= curSub.start_sec - 0.08;
          if (!isStalePrevCue) {
            pauseGuardRef.current = false;
            pausedBySentenceEndRef.current = false;
            activeSubRef.current = found;
            setActiveSubId(found.id);
          }
        }
      }
    }
  };

  const handleMediaEnded = () => {
    const el = mediaRef.current;
    if (!el) {
      setIsPlaying(false);
      return;
    }
    if (continuousShadowingRef.current) {
      setIsPlaying(false);
      setMediaEndedTick((n) => n + 1);
      return;
    }
    if (isRecording) {
      setIsPlaying(false);
      return;
    }
    if (stopAtSecRef.current !== null) {
      const doneCb = onStopAtFinishedRef.current;
      stopAtSecRef.current = null;
      onStopAtFinishedRef.current = null;
      onStopAtCancelledRef.current = null;
      oneShotPausedRef.current = true;
      setIsPlaying(false);
      doneCb?.();
      return;
    }
    const curSub = activeSubRef.current || activeSubtitle;
    if (singleLoop && curSub) {
      el.currentTime = Math.max(0, curSub.start_sec + 0.01);
      el.play().catch(() => setIsPlaying(false));
      return;
    }
    if (abLoop && subtitles.length > 1) {
      const startSub = subtitles[Math.min(abRange[0], subtitles.length - 1)];
      if (startSub) {
        activeSubRef.current = startSub;
        setActiveSubId(startSub.id);
        el.currentTime = Math.max(0, startSub.start_sec + 0.01);
        el.play().catch(() => setIsPlaying(false));
        return;
      }
    }
    if (pausePerSentence && curSub) {
      pausedBySentenceEndRef.current = true;
    }
    setIsPlaying(false);
  };

  const handleScrub = (e) => {
    if (isRecording) return;
    const el = mediaRef.current;
    const total = duration || episode?.duration_sec || 0;
    if (!el || total <= 0) return;
    clearOneShotStop();
    pauseGuardRef.current = false;
    pausedBySentenceEndRef.current = false;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const nextSec = ratio * total;
    el.currentTime = nextSec;
    setCurrentTime(nextSec);
    if (!singleLoop) {
      const matched =
        subtitles.find((s) => nextSec >= s.start_sec && nextSec < s.end_sec) ||
        subtitles.find((s) => nextSec >= s.start_sec - 0.08 && nextSec <= s.end_sec + 0.08);
      if (matched) {
        activeSubRef.current = matched;
        setActiveSubId(matched.id);
      }
    }
  };

  const handlePip = async () => {
    if (isRecording) return;
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
      } else if (mediaRef.current && mediaRef.current.requestPictureInPicture) {
        await mediaRef.current.requestPictureInPicture();
      }
    } catch {
      onToast('当前浏览器不支持画中画模式');
    }
  };

  const handleFullscreen = () => {
    if (isRecording) return;
    const el = mediaRef.current;
    if (!el) return;
    if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
  };

  const handleToggleSubFavorite = async (subId, e) => {
    e.stopPropagation();
    if (isRecording) return;
    try {
      await api.toggleSubtitleFavorite(subId);
      onReloadEpisode();
      onDeckChanged();
    } catch (err) {
      onToast(err.message || '收藏失败');
    }
  };

  const handleToggleEntryBookmark = async (entryId) => {
    if (isRecording) return;
    try {
      const res = await api.toggleEntryBookmark(entryId);
      onToast(res.is_bookmarked ? '已加入个人生词本' : '已从生词本移除');
      onReloadEpisode();
      onDeckChanged();
    } catch (err) {
      onToast(err.message || '操作失败');
    }
  };

  const handleCueHtmlClick = (e) => {
    if (isRecording) return;
    const term = e.target.closest('.lex-term');
    if (term) {
      e.stopPropagation();
      const eid = Number(term.getAttribute('data-entry-id'));
      if (eid) setSelectedEntryId(eid);
    }
  };

  const handleToggleAbLoop = () => {
    if (isRecording) return;
    if (!abLoop && subtitles.length < 2) {
      onToast('至少需要 2 句字幕才能开启 AB 区间复读');
      return;
    }
    const next = !abLoop;
    setAbLoop(next);
    if (next && subtitles.length > 1) {
      const a = activeIdx;
      const b = Math.min(subtitles.length - 1, activeIdx + 2);
      setAbRange([a, b]);
      setSingleLoop(false);
      onToast(`已开启 AB 复读：#${a + 1} 至 #${b + 1}`);
    }
  };

  const handleSwitchMode = (nextMode) => {
    if (isRecording) {
      onToast('录音进行中，请先点击「停止录音」后再切换学习模式');
      return;
    }
    setMode(nextMode);
  };

  if (!episode) {
    return (
      <main className="library-shell" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div className="practice-card" style={{ alignItems: 'center', padding: 36, maxWidth: 460 }}>
          <h2 style={{ fontSize: 22, fontWeight: 900 }}>还没有装入学习卡带</h2>
          <p style={{ color: 'var(--ink-sub)', textAlign: 'center' }}>
            前往「资料库」选择已有视频或上传任意英语素材，自动拆解后即可装入学习机精听。
          </p>
          <button type="button" className="chunk chunk-yellow" onClick={onOpenLibrary}>
            前往资料库上传与选片
          </button>
        </div>
      </main>
    );
  }

  const totalDur = duration || episode.duration_sec || 1;
  const progressPct = Math.min(100, Math.max(0, (currentTime / totalDur) * 100));

  return (
    <>
      <main className="studio-body">
        {/* ==================== LEFT CITRUS 3D HARDWARE CONSOLE ==================== */}
        <section className="console-left">
          <div className="screen-bezel">
            <div className="screen-inner">
              {episode.media_kind === 'video' && episode.video_url ? (
                <video
                  key={episode.id}
                  ref={mediaRef}
                  className="screen-video"
                  src={episode.video_url}
                  poster={episode.cover_url || undefined}
                  playsInline
                  onPlay={(e) => {
                    if (isRecording && !continuousShadowingRef.current) {
                      e.currentTarget.pause();
                      return;
                    }
                    oneShotPausedRef.current = false;
                    pauseOtherDomMedia(e.currentTarget);
                    setIsPlaying(true);
                  }}
                  onPause={(e) => {
                    setIsPlaying(false);
                    if (stopAtSecRef.current !== null && !e.currentTarget.ended) {
                      clearOneShotStop();
                    }
                    persistPosition(e.currentTarget.currentTime);
                  }}
                  onSeeking={() => {
                    oneShotPausedRef.current = false;
                    pausedBySentenceEndRef.current = false;
                    pauseGuardRef.current = false;
                  }}
                  onEnded={handleMediaEnded}
                  onLoadedMetadata={handleLoadedMetadata}
                  onTimeUpdate={handleTimeUpdate}
                  onClick={togglePlayPause}
                />
              ) : (
                <>
                  <audio
                    key={episode.id}
                    ref={mediaRef}
                    src={episode.audio_url}
                    onPlay={(e) => {
                      if (isRecording && !continuousShadowingRef.current) {
                        e.currentTarget.pause();
                        return;
                      }
                      oneShotPausedRef.current = false;
                      pauseOtherDomMedia(e.currentTarget);
                      setIsPlaying(true);
                    }}
                    onPause={(e) => {
                      setIsPlaying(false);
                      if (stopAtSecRef.current !== null && !e.currentTarget.ended) {
                        clearOneShotStop();
                      }
                      persistPosition(e.currentTarget.currentTime);
                    }}
                    onSeeking={() => {
                      oneShotPausedRef.current = false;
                      pausedBySentenceEndRef.current = false;
                      pauseGuardRef.current = false;
                    }}
                    onEnded={handleMediaEnded}
                    onLoadedMetadata={handleLoadedMetadata}
                    onTimeUpdate={handleTimeUpdate}
                  />
                  <div
                    className="audio-stage"
                    onClick={togglePlayPause}
                    onKeyDown={(e) => {
                      if (isRecording) return;
                      if (e.code === 'Space' || e.key === 'Enter') {
                        e.preventDefault();
                        togglePlayPause();
                      }
                    }}
                    role="button"
                    tabIndex={isRecording ? -1 : 0}
                  >
                    <div className={`eq-bars ${isPlaying ? 'playing' : ''}`}>
                      {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                        <span key={i} className="eq-bar" />
                      ))}
                    </div>
                    <strong style={{ fontSize: 17 }}>{episode.title}</strong>
                    <span style={{ fontSize: 13.5, color: '#D7CEF0' }}>纯音频精听卡带（点击画面播放或暂停）</span>
                  </div>
                </>
              )}

              <div className="screen-hud-top">
                <span className="screen-badge tnum">
                  {subtitles.length > 0 ? `#${activeIdx + 1} / ${subtitles.length}` : '#0 / 0'}
                  {abLoop && subtitles.length > 0 ? ` AB(#${abRange[0] + 1}-#${abRange[1] + 1})` : ''}
                  {singleLoop && subtitles.length > 0 ? ' 单句循环' : ''}
                  {isRecording ? (continuousShadowing ? ' 同步跟读中' : ' 录音静音中') : ''}
                </span>
                <div className="screen-tools">
                  {episode.media_kind === 'video' && (
                    <>
                      <button
                        type="button"
                        className="screen-icon-btn"
                        disabled={isRecording}
                        onClick={handlePip}
                        title="画中画悬浮窗"
                      >
                        <PictureInPicture2 size={16} />
                      </button>
                      <button
                        type="button"
                        className="screen-icon-btn"
                        disabled={isRecording}
                        onClick={handleFullscreen}
                        title="全屏观看"
                      >
                        <Maximize2 size={16} />
                      </button>
                    </>
                  )}
                </div>
              </div>

              {showScreenCaption && !blindMode && activeSubtitle && (
                <div className="screen-caption">
                  {(captionMode === 'bilingual' || captionMode === 'en') && (
                    <div className="screen-caption-en">{activeSubtitle.source_text}</div>
                  )}
                  {(captionMode === 'bilingual' || captionMode === 'cn') && activeSubtitle.target_text && (
                    <div className="screen-caption-cn">{activeSubtitle.target_text}</div>
                  )}
                </div>
              )}
            </div>

            <div className="scrubber-row tnum">
              <span>{formatTime(currentTime)}</span>
              <div
                className="scrubber-track"
                style={{ pointerEvents: isRecording ? 'none' : 'auto', opacity: isRecording ? 0.5 : 1 }}
                onClick={handleScrub}
                role="slider"
                aria-label="播放进度条"
                aria-disabled={isRecording}
              >
                <div className="scrubber-fill" style={{ width: `${progressPct}%` }} />
              </div>
              <span>{formatTime(totalDur)}</span>
            </div>
          </div>

          {/* Chunky 3D Sentence Keys */}
          <div className="seg-blocks" aria-label="逐句定位按键">
            {subtitles.map((sub, idx) => {
              const isAct = sub.id === activeSubId;
              const isInAb = abLoop && idx >= abRange[0] && idx <= abRange[1];
              const hasRec = (sub.recordings || []).length > 0;
              return (
                <button
                  key={sub.id}
                  type="button"
                  disabled={isRecording}
                  className={`seg-key tnum ${isAct ? 'active' : isInAb ? 'ab' : ''}`}
                  onClick={() => seekAndPlaySubtitle(sub.id, true)}
                  title={
                    isRecording
                      ? '录音进行中已锁定切句'
                      : `跳到第 ${sub.seq_index} 句：${sub.source_text.slice(0, 40)}`
                  }
                >
                  #{sub.seq_index}
                  {hasRec && <span className="seg-rec-dot" title="已录入跟读" />}
                </button>
              );
            })}
          </div>

          {abLoop && subtitles.length > 1 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                background: 'var(--accent)',
                padding: '6px 12px',
                borderRadius: 14,
                boxShadow: '0 4px 0 var(--accent-deep)',
                flexShrink: 0,
              }}
            >
              <div className="toolbar-group tnum" style={{ fontSize: 13, fontWeight: 800 }}>
                <span>AB 区间：</span>
                <select
                  aria-label="AB 复读起点句"
                  className="select-3d"
                  disabled={isRecording}
                  style={{ width: 'auto', padding: '3px 8px', fontSize: 13 }}
                  value={abRange[0]}
                  onChange={(e) => {
                    const a = Number(e.target.value);
                    setAbRange([a, Math.max(a, abRange[1])]);
                  }}
                >
                  {subtitles.map((s, idx) => (
                    <option key={s.id} value={idx}>
                      起点 #{s.seq_index}
                    </option>
                  ))}
                </select>
                <span>至</span>
                <select
                  aria-label="AB 复读终点句"
                  className="select-3d"
                  disabled={isRecording}
                  style={{ width: 'auto', padding: '3px 8px', fontSize: 13 }}
                  value={abRange[1]}
                  onChange={(e) => {
                    const b = Number(e.target.value);
                    setAbRange([Math.min(abRange[0], b), b]);
                  }}
                >
                  {subtitles.map((s, idx) => (
                    <option key={s.id} value={idx}>
                      终点 #{s.seq_index}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                className="chunk chunk-dark chunk-sm"
                disabled={isRecording}
                onClick={() => {
                  const startSub = subtitles[abRange[0]];
                  if (startSub) seekAndPlaySubtitle(startSub.id, true);
                }}
              >
                从起点复读
              </button>
            </div>
          )}

          {/* Signature 3D Rotary Speed Dial + Physical Buttons + 6 Glossy Switches */}
          <div className="tactile-deck">
            <div className="dial-wrap">
              <div
                className="dial-3d"
                style={{
                  opacity: isRecording ? 0.55 : 1,
                  pointerEvents: isRecording ? 'none' : 'auto',
                }}
                onClick={() => !isRecording && setSpeedIdx((i) => (i + 1) % SPEEDS.length)}
                onWheel={(e) => {
                  if (isRecording) return;
                  e.preventDefault();
                  setSpeedIdx((i) =>
                    e.deltaY > 0 ? Math.max(0, i - 1) : Math.min(SPEEDS.length - 1, i + 1)
                  );
                }}
                role="button"
                tabIndex={isRecording ? -1 : 0}
                aria-disabled={isRecording}
                onKeyDown={(e) => {
                  if (isRecording) return;
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSpeedIdx((i) => (i + 1) % SPEEDS.length);
                  }
                }}
                title="点击或滚轮旋转 3D 倍速旋钮"
                aria-label={`当前倍速 ${SPEEDS[speedIdx].toFixed(2)}x，点击切换`}
              >
                <span
                  className="dial-dot"
                  style={{ transform: `rotate(${DIAL_ANGLES[speedIdx]}deg)` }}
                />
                <div className="dial-inner">
                  <span className="dial-val tnum">{SPEEDS[speedIdx]}x</span>
                  <span className="dial-sub">精听倍速</span>
                </div>
              </div>

              <div className="dial-steps">
                <button
                  type="button"
                  className="chunk chunk-cream chunk-sm"
                  onClick={() => setSpeedIdx((i) => Math.max(0, i - 1))}
                  disabled={isRecording || speedIdx === 0}
                  aria-label="减速"
                >
                  <Minus size={14} />
                </button>
                <button
                  type="button"
                  className="chunk chunk-cream chunk-sm tnum"
                  onClick={() => setSpeedIdx(3)}
                  disabled={isRecording}
                  title="复位到 1.0x 原速"
                >
                  原速
                </button>
                <button
                  type="button"
                  className="chunk chunk-cream chunk-sm"
                  onClick={() => setSpeedIdx((i) => Math.min(SPEEDS.length - 1, i + 1))}
                  disabled={isRecording || speedIdx === SPEEDS.length - 1}
                  aria-label="加速"
                >
                  <Plus size={14} />
                </button>
              </div>
            </div>

            <div className="deck-right">
              <div className="big-btns">
                <button
                  type="button"
                  className="chunk chunk-cream"
                  disabled={isRecording || !subtitles.length}
                  onClick={() => stepSentence(-1)}
                  title="上一句 (←)"
                  aria-label="上一句"
                >
                  <SkipBack size={18} />
                </button>
                <button
                  type="button"
                  className="chunk chunk-dark"
                  disabled={isRecording}
                  onClick={togglePlayPause}
                  title="播放或暂停 (Space)"
                >
                  {isPlaying ? <Pause size={18} /> : <Play size={18} />}
                  <span>{isPlaying ? '暂停' : '播放本句'}</span>
                </button>
                <button
                  type="button"
                  className="chunk chunk-mint"
                  disabled={isRecording}
                  onClick={() => handleSwitchMode('shadow')}
                  title="进入影子跟读对比"
                >
                  <Mic size={18} />
                  <span>跟读对比</span>
                </button>
                <button
                  type="button"
                  className="chunk chunk-cream"
                  disabled={isRecording || !subtitles.length}
                  onClick={() => stepSentence(1)}
                  title="下一句 (→)"
                  aria-label="下一句"
                >
                  <SkipForward size={18} />
                </button>
              </div>

              <div className="switch-cards">
                <div className={`sw-tile ${singleLoop ? 'hi' : ''}`}>
                  <span className="sw-label">单句循环</span>
                  <button
                    type="button"
                    className={`toggle-3d ${singleLoop ? 'on' : ''}`}
                    disabled={isRecording}
                    onClick={() => {
                      setSingleLoop((v) => !v);
                      setAbLoop(false);
                    }}
                    aria-pressed={singleLoop}
                    aria-label="切换单句循环"
                  />
                </div>

                <div className={`sw-tile ${pausePerSentence ? 'hi' : ''}`}>
                  <span className="sw-label">逐句暂停</span>
                  <button
                    type="button"
                    className={`toggle-3d ${pausePerSentence ? 'on' : ''}`}
                    disabled={isRecording}
                    onClick={() => {
                      pauseGuardRef.current = false;
                      pausedBySentenceEndRef.current = false;
                      setPausePerSentence((v) => !v);
                    }}
                    aria-pressed={pausePerSentence}
                    aria-label="切换逐句暂停"
                  />
                </div>

                <div className={`sw-tile ${blindMode ? 'hi' : ''}`}>
                  <span className="sw-label">盲听模式</span>
                  <button
                    type="button"
                    className={`toggle-3d ${blindMode ? 'on' : ''}`}
                    disabled={isRecording}
                    onClick={() => setBlindMode((v) => !v)}
                    aria-pressed={blindMode}
                    aria-label="切换盲听模式"
                  />
                </div>

                <div className={`sw-tile ${showIpa ? 'hi' : ''}`}>
                  <span className="sw-label">音标 IPA</span>
                  <button
                    type="button"
                    className={`toggle-3d ${showIpa ? 'on' : ''}`}
                    disabled={isRecording}
                    onClick={() => setShowIpa((v) => !v)}
                    aria-pressed={showIpa}
                    aria-label="切换国际音标显示"
                  />
                </div>

                <div className={`sw-tile ${abLoop ? 'hi' : ''}`}>
                  <span className="sw-label">AB 复读</span>
                  <button
                    type="button"
                    className={`toggle-3d ${abLoop ? 'on' : ''}`}
                    disabled={isRecording}
                    onClick={handleToggleAbLoop}
                    aria-pressed={abLoop}
                    aria-label="切换 AB 区间复读"
                  />
                </div>

                <div className={`sw-tile ${showScreenCaption ? 'hi' : ''}`}>
                  <span className="sw-label">画面字幕</span>
                  <button
                    type="button"
                    className={`toggle-3d ${showScreenCaption ? 'on' : ''}`}
                    disabled={isRecording}
                    onClick={() => setShowScreenCaption((v) => !v)}
                    aria-pressed={showScreenCaption}
                    aria-label="切换视频画面字幕"
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ==================== RIGHT WARM CREAM WORKBENCH ==================== */}
        <section className="panel-right">
          <div className="mode-rack" role="tablist" aria-label="精听学习模式">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                role="tab"
                aria-selected={mode === m.id}
                disabled={isRecording && mode !== m.id}
                className={`chunk m-key ${mode === m.id ? 'active' : ''}`}
                onClick={() => handleSwitchMode(m.id)}
              >
                {m.id === 'lexicon' && <BookOpen size={15} />}
                {m.id === 'ai' && <Sparkles size={15} />}
                {m.id === 'editor' && <Edit3 size={15} />}
                <span>{m.label}</span>
                {m.id === 'lexicon' && <span className="tnum">({entries.length})</span>}
              </button>
            ))}
          </div>

          {/* MODE 1: Bilingual / EN / CN / Blind Subtitle Stack */}
          {mode === 'bilingual' && (
            <>
              <div className="sub-toolbar">
                <div className="toolbar-group">
                  {[
                    { id: 'bilingual', label: '双语' },
                    { id: 'en', label: '仅英' },
                    { id: 'cn', label: '仅中' },
                  ].map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className={`seg-pill ${!blindMode && captionMode === c.id ? 'active' : ''}`}
                      onClick={() => {
                        setBlindMode(false);
                        setCaptionMode(c.id);
                      }}
                    >
                      {c.label}
                    </button>
                  ))}
                  {blindMode && <span className="pill-3d coral">盲听遮罩中</span>}
                </div>

                <div className="toolbar-group">
                  <button
                    type="button"
                    className="chunk chunk-white chunk-sm"
                    onClick={() => setFontScale((s) => Math.max(0.85, +(s - 0.1).toFixed(2)))}
                    title="缩小字号"
                  >
                    A-
                  </button>
                  <button
                    type="button"
                    className="chunk chunk-white chunk-sm"
                    onClick={() => setFontScale((s) => Math.min(1.35, +(s + 0.1).toFixed(2)))}
                    title="放大字号"
                  >
                    A+
                  </button>
                  <button
                    type="button"
                    className="chunk chunk-white chunk-sm"
                    onClick={() => setPrintOpen(true)}
                    title="预览并打印 PDF 精听讲义"
                  >
                    <Printer size={14} />
                    <span>讲义</span>
                  </button>
                  <a
                    href={`/api/episodes/${episode.id}/export/srt?bilingual=true`}
                    className="chunk chunk-white chunk-sm"
                    style={{ textDecoration: 'none' }}
                    title="下载双语 SRT 字幕"
                  >
                    <Download size={14} />
                    <span>SRT</span>
                  </a>
                </div>
              </div>

              <div className="cards-scroll">
                {subtitles.length === 0 ? (
                  <div className="practice-card" style={{ alignItems: 'center', padding: 28 }}>
                    <strong>当前篇目暂无字幕</strong>
                    <p style={{ fontSize: 14, color: 'var(--ink-sub)' }}>
                      可切换到「校对」页签点击「插新句」或「替换 SRT」导入双语字幕。
                    </p>
                  </div>
                ) : (
                  subtitles.map((sub) => {
                    const isActive = sub.id === activeSubId;
                    const baseHtml = sub.source_html || escapeHtmlFallback(sub.source_text);
                    const htmlMarked = baseHtml.replace(
                      new RegExp(`data-entry-id="${selectedEntry?.id}"`, 'g'),
                      `data-entry-id="${selectedEntry?.id}" data-sel="1"`
                    );
                    const htmlWithSelectedClass = htmlMarked.replace(
                      new RegExp(`class="lex-term" data-entry-id="${selectedEntry?.id}"`, 'g'),
                      `class="lex-term selected" data-entry-id="${selectedEntry?.id}"`
                    );

                    return (
                      <article
                        key={sub.id}
                        ref={(el) => {
                          if (el) cueRefs.current[sub.id] = el;
                        }}
                        className={`cue-card ${isActive ? 'active' : ''}`}
                        onClick={() => seekAndPlaySubtitle(sub.id, true)}
                      >
                        <div className="cue-top tnum">
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                            <span>
                              #{sub.seq_index} {formatTime(sub.start_sec)} - {formatTime(sub.end_sec)}
                            </span>
                            {isActive && activeSpokenWord && (
                              <span className="pill-3d dark">正在朗读：{activeSpokenWord}</span>
                            )}
                          </span>
                          <div className="cue-actions">
                            {sub.recordings?.length > 0 && (
                              <span className="pill-3d mint">已跟读</span>
                            )}
                            <button
                              type="button"
                              className={`cue-mini-btn ${sub.is_favorite ? 'starred' : ''}`}
                              onClick={(e) => handleToggleSubFavorite(sub.id, e)}
                              title={sub.is_favorite ? '取消收藏金句' : '收藏金句'}
                            >
                              <Star size={14} fill={sub.is_favorite ? 'currentColor' : 'none'} />
                            </button>
                            <button
                              type="button"
                              className="cue-mini-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                seekAndPlaySubtitle(sub.id, true);
                              }}
                              title="播放此句"
                            >
                              <Play size={14} />
                            </button>
                          </div>
                        </div>

                        {blindMode ? (
                          <div
                            style={{
                              padding: '10px 14px',
                              borderRadius: 12,
                              background: 'rgba(27,19,48,0.08)',
                              fontSize: 14,
                              fontWeight: 800,
                              color: 'var(--ink-sub)',
                            }}
                          >
                            盲听模式已开启：专注辨音，关闭左侧「盲听模式」开关即可核对双语字幕与词块
                          </div>
                        ) : (
                          <>
                            {(captionMode === 'bilingual' || captionMode === 'en') && (
                              <div
                                className="cue-en"
                                style={{ fontSize: `${Math.round(17 * fontScale)}px` }}
                                onClick={handleCueHtmlClick}
                                dangerouslySetInnerHTML={{ __html: htmlWithSelectedClass }}
                              />
                            )}
                            {showIpa && sub.ipa && captionMode !== 'cn' && (
                              <div className="cue-ipa">{sub.ipa}</div>
                            )}
                            {(captionMode === 'bilingual' || captionMode === 'cn') && sub.target_text && (
                              <div className="cue-cn">{sub.target_text}</div>
                            )}
                          </>
                        )}
                      </article>
                    );
                  })
                )}
              </div>
            </>
          )}

          {/* MODE 2: Shadowing & Recording Compare */}
          {mode === 'shadow' && (
            <ShadowingPanel
              episodeId={episode.id}
              activeSubtitle={activeSubtitle}
              isRecording={isRecording}
              mediaEndedTick={mediaEndedTick}
              onRecordingChange={onRecordingChange}
              onStopAllAudio={stopAllAudio}
              onPrepareContinuousShadowing={prepareContinuousShadowing}
              onStartContinuousPlayback={startContinuousShadowPlayback}
              onStopContinuousPlayback={stopContinuousShadowPlayback}
              onPlaySentenceOnce={playSentenceOnce}
              onPlayOriginalSentence={playActiveSentenceOnce}
              onSelectSubtitle={(sid) => seekAndPlaySubtitle(sid, false)}
              onRecordingsChanged={onReloadEpisode}
              onToast={onToast}
            />
          )}

          {/* MODE 3: Cloze Active Recall */}
          {mode === 'cloze' && (
            <ClozePanel
              episodeId={episode.id}
              subtitles={subtitles}
              activeSubtitleId={activeSubId}
              onSelectSubtitle={seekAndPlaySubtitle}
              fontScale={fontScale}
            />
          )}

          {/* MODE 4: Keyword & Full-Sentence Dictation */}
          {mode === 'dictation' && (
            <DictationPanel
              episodeId={episode.id}
              subtitles={subtitles}
              activeSubtitle={activeSubtitle}
              onSelectSubtitle={seekAndPlaySubtitle}
              onPlayCurrent={playActiveSentenceOnce}
            />
          )}

          {/* MODE 5: Embedded Bilingual Dictionary & Cross-Episode Jumps */}
          {mode === 'lexicon' && (
            <LexiconPanel
              episodeId={episode.id}
              entries={entries}
              activeSubtitle={activeSubtitle}
              selectedEntryId={selectedEntry?.id}
              onSelectEntry={setSelectedEntryId}
              onToggleBookmark={handleToggleEntryBookmark}
              onJumpToSubtitle={(sid) => {
                setMode('bilingual');
                seekAndPlaySubtitle(sid, true);
              }}
              onJumpToOccurrence={onJumpToOccurrence}
            />
          )}

          {/* MODE 6: AI Sentence Breakdown & Retelling Coach */}
          {mode === 'ai' && (
            <AiCoachPanel
              episode={episode}
              activeSubtitle={activeSubtitle}
              isRecording={isRecording}
              onRecordingChange={onRecordingChange}
              onStopAllAudio={stopAllAudio}
              onSubtitleAnalyzed={() => onReloadEpisode()}
              onEpisodeReload={onReloadEpisode}
              onPlayCurrent={playActiveSentenceOnce}
              onToast={onToast}
            />
          )}

          {/* MODE 7: Subtitle & Custom Lexicon Proofread Editor */}
          {mode === 'editor' && (
            <ProofreadEditorPanel
              episodeId={episode.id}
              hasRecordings={hasRecordings}
              activeSubtitle={activeSubtitle}
              onStopAllAudio={stopAllAudio}
              onEpisodeReload={onReloadEpisode}
              onDeckChanged={onDeckChanged}
              onToast={onToast}
            />
          )}

          {/* Pinned Bottom Dark-Plum Quick Lexicon Dock */}
          {selectedEntry && (
            <div className="lex-dock-3d">
              <div className="lex-dock-main">
                <div className="lex-dock-head">
                  <span className="lex-dock-word">{selectedEntry.headword}</span>
                  <span className="pill-3d">{selectedEntry.category}</span>
                  {selectedEntry.pronunciations?.[0]?.ipa && (
                    <span className="lex-dock-ipa">{selectedEntry.pronunciations[0].ipa}</span>
                  )}
                  {selectedEntry.cross_episode_count > 1 && (
                    <span className="pill-3d mint">
                      <Globe2 size={12} />
                      <span>跨 {selectedEntry.cross_episode_count} 篇复现</span>
                    </span>
                  )}
                </div>
                <div className="lex-dock-def">
                  {selectedEntry.definitions?.[0]?.definition_target ||
                    selectedEntry.definitions?.[0]?.definition_source}
                </div>
              </div>

              <div className="lex-dock-btns">
                <button
                  type="button"
                  className="chunk chunk-cream chunk-sm"
                  disabled={isRecording}
                  onClick={() => {
                    if (isRecording) return;
                    speakWord(selectedEntry.headword, 'US');
                  }}
                  title="朗读美式发音"
                >
                  <Volume2 size={14} />
                  <span>发音</span>
                </button>
                <button
                  type="button"
                  className={`chunk chunk-sm ${selectedEntry.is_bookmarked ? 'chunk-coral' : 'chunk-white'}`}
                  disabled={isRecording}
                  onClick={() => handleToggleEntryBookmark(selectedEntry.id)}
                  title={selectedEntry.is_bookmarked ? '移出生词本' : '加入生词本'}
                >
                  <Star size={14} fill={selectedEntry.is_bookmarked ? 'currentColor' : 'none'} />
                  <span>{selectedEntry.is_bookmarked ? '已收藏' : '收藏'}</span>
                </button>
                <button
                  type="button"
                  className="chunk chunk-yellow chunk-sm"
                  disabled={isRecording}
                  onClick={() => handleSwitchMode('lexicon')}
                  title="在词典面板查看完整例句与跨篇复现"
                >
                  <span>精解</span>
                </button>
              </div>
            </div>
          )}
        </section>
      </main>

      <PrintPreviewModal
        open={printOpen}
        onClose={() => setPrintOpen(false)}
        episode={episode}
        subtitles={subtitles}
        entries={entries}
      />
    </>
  );
}
