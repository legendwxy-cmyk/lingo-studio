import React, { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import LearningMachine from './components/LearningMachine';
import LibraryWorkspace from './components/LibraryWorkspace';
import LoginGate from './components/LoginGate';
import SettingsModal from './components/SettingsModal';
import TopBar from './components/TopBar';
import VocabDeckModal from './components/VocabDeckModal';

export default function App() {
  const [authState, setAuthState] = useState({
    checked: false,
    authEnabled: false,
    authenticated: false,
    desktopMode: false,
  });

  const [activeView, setActiveView] = useState('machine'); // machine | library
  const [skin, setSkin] = useState(() => localStorage.getItem('lingoreel_skin') || 'citrus');

  const [episodes, setEpisodes] = useState([]);
  const [currentEpisodeId, setCurrentEpisodeId] = useState(null);
  const [episodeDetail, setEpisodeDetail] = useState(null);
  const [targetSubtitleId, setTargetSubtitleId] = useState(null);

  const [vocabCount, setVocabCount] = useState(0);
  const [settingsInfo, setSettingsInfo] = useState({ has_asr_key: false, has_llm_key: false });

  const [vocabOpen, setVocabOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [toastMsg, setToastMsg] = useState('');

  const showToast = useCallback((msg) => {
    setToastMsg(msg);
  }, []);

  useEffect(() => {
    if (!toastMsg) return undefined;
    const t = setTimeout(() => setToastMsg(''), 3200);
    return () => clearTimeout(t);
  }, [toastMsg]);

  useEffect(() => {
    document.documentElement.setAttribute('data-skin', skin);
    localStorage.setItem('lingoreel_skin', skin);
  }, [skin]);

  const checkAuth = useCallback(async () => {
    try {
      const res = await api.authStatus();
      setAuthState({
        checked: true,
        authEnabled: Boolean(res.auth_enabled),
        authenticated: Boolean(res.authenticated),
        desktopMode: Boolean(res.desktop_mode),
      });
    } catch {
      setAuthState({ checked: true, authEnabled: false, authenticated: true, desktopMode: false });
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const refreshVocabCount = useCallback(async () => {
    try {
      const deck = await api.getVocabDeck();
      setVocabCount((deck.entries || []).length);
    } catch {
      // ignore
    }
  }, []);

  const loadEpisodeDetail = useCallback(
    async (epId) => {
      if (!epId) {
        setEpisodeDetail(null);
        return;
      }
      try {
        const detail = await api.getEpisode(epId);
        setEpisodeDetail(detail);
        setCurrentEpisodeId(epId);
      } catch (err) {
        if (err.status === 401) {
          setAuthState((s) => ({ ...s, authenticated: false }));
          return;
        }
        showToast(err.message || '加载篇目详情失败');
      }
    },
    [showToast]
  );

  const refreshEpisodes = useCallback(async () => {
    try {
      const res = await api.listEpisodes();
      const list = res.episodes || [];
      setEpisodes(list);
      if (!currentEpisodeId && list.length > 0) {
        const firstReady = list.find((e) => e.status === 'ready') || list[0];
        if (firstReady && firstReady.status === 'ready') {
          loadEpisodeDetail(firstReady.id);
        }
      } else if (currentEpisodeId && !list.some((e) => e.id === currentEpisodeId)) {
        const fallback = list.find((e) => e.status === 'ready');
        if (fallback) loadEpisodeDetail(fallback.id);
        else {
          setCurrentEpisodeId(null);
          setEpisodeDetail(null);
        }
      }
    } catch (err) {
      if (err.status === 401) {
        setAuthState((s) => ({ ...s, authenticated: false }));
        return;
      }
      showToast(err.message || '获取资料库列表失败');
    }
  }, [currentEpisodeId, loadEpisodeDetail, showToast]);

  useEffect(() => {
    if (!authState.checked || !authState.authenticated) return;
    refreshEpisodes();
    refreshVocabCount();
    api
      .getSettings()
      .then((res) => setSettingsInfo(res))
      .catch(() => {});
  }, [authState.checked, authState.authenticated]);

  const hasReadyEpisode = episodes.some((e) => e.status === 'ready');
  const hasBusyEpisode = episodes.some((e) => e.status === 'queued' || e.status === 'processing');

  // Auto-refresh during fresh cold-boot demo seeding or any active background upload/reprocess
  useEffect(() => {
    if (!authState.checked || !authState.authenticated) return undefined;
    if (hasReadyEpisode && !hasBusyEpisode) return undefined;
    let polls = 0;
    const timer = setInterval(() => {
      polls += 1;
      if (!hasBusyEpisode && polls > 20) {
        clearInterval(timer);
        return;
      }
      refreshEpisodes();
      refreshVocabCount();
    }, 1500);
    return () => clearInterval(timer);
  }, [authState.checked, authState.authenticated, hasReadyEpisode, hasBusyEpisode, refreshEpisodes, refreshVocabCount]);

  const handleLogout = async () => {
    if (isRecording) {
      showToast('录音进行中，请先停止录音后再退出');
      return;
    }
    try {
      await api.logout();
    } catch {
      // ignore
    }
    setEpisodes([]);
    setEpisodeDetail(null);
    setCurrentEpisodeId(null);
    setAuthState((s) => ({ ...s, authenticated: false }));
  };

  const handleShutdownDesktop = async () => {
    if (isRecording) {
      showToast('录音进行中，请先停止录音后再关闭服务');
      return;
    }
    if (!window.confirm('确定关闭 Lingo 本机后台服务吗？（下次点开应用程序图标即可重新启动）')) {
      return;
    }
    try {
      await api.shutdownDesktop();
      showToast('本机学习机服务已关闭，可以安全关闭此浏览器标签页。');
    } catch (err) {
      showToast(err.message || '关闭服务失败');
    }
  };

  const handleSwitchView = (nextView) => {
    if (isRecording) {
      showToast('录音进行中，请先点击「停止录音」再切换页面');
      return;
    }
    setActiveView(nextView);
    if (nextView === 'library') {
      refreshEpisodes();
    }
  };

  const handleSelectEpisode = async (epId) => {
    if (isRecording) return;
    await loadEpisodeDetail(epId);
    setActiveView('machine');
  };

  const handleJumpToOccurrence = async (epId, subtitleId) => {
    if (isRecording) {
      showToast('录音进行中，请先停止录音后再跳转');
      return;
    }
    setTargetSubtitleId(subtitleId);
    if (epId !== currentEpisodeId) {
      await loadEpisodeDetail(epId);
    }
    setActiveView('machine');
  };

  if (!authState.checked) {
    return null;
  }

  if (authState.authEnabled && !authState.authenticated) {
    return (
      <LoginGate
        onUnlocked={() => {
          setAuthState((s) => ({ ...s, checked: true, authEnabled: true, authenticated: true }));
          showToast('口令验证通过，欢迎回到 Lingo');
        }}
      />
    );
  }

  const processingCount = episodes.filter(
    (e) => e.status === 'queued' || e.status === 'processing'
  ).length;

  return (
    <>
      <div className="app-frame">
        <TopBar
          activeView={activeView}
          onSwitchView={handleSwitchView}
          currentEpisode={episodeDetail?.episode || null}
          episodeCount={episodes.length}
          processingCount={processingCount}
          vocabCount={vocabCount}
          skin={skin}
          onChangeSkin={setSkin}
          onOpenVocab={() => !isRecording && setVocabOpen(true)}
          onOpenSettings={() => !isRecording && setSettingsOpen(true)}
          authEnabled={authState.authEnabled}
          onLogout={handleLogout}
          desktopMode={authState.desktopMode}
          onShutdownDesktop={handleShutdownDesktop}
          isRecording={isRecording}
        />

        {activeView === 'machine' ? (
          <LearningMachine
            detail={episodeDetail}
            targetSubtitleId={targetSubtitleId}
            onClearTargetSubtitle={() => setTargetSubtitleId(null)}
            onReloadEpisode={() => {
              if (currentEpisodeId) loadEpisodeDetail(currentEpisodeId);
              refreshEpisodes();
            }}
            onJumpToOccurrence={handleJumpToOccurrence}
            onDeckChanged={refreshVocabCount}
            onOpenLibrary={() => handleSwitchView('library')}
            onToast={showToast}
            isRecording={isRecording}
            onRecordingChange={setIsRecording}
            shortcutsDisabled={vocabOpen || settingsOpen}
          />
        ) : (
          <LibraryWorkspace
            episodes={episodes}
            currentEpisodeId={currentEpisodeId}
            settingsInfo={settingsInfo}
            onSelectEpisode={handleSelectEpisode}
            onRefreshEpisodes={refreshEpisodes}
            onOpenSettings={() => setSettingsOpen(true)}
            onToast={showToast}
          />
        )}
      </div>

      <VocabDeckModal
        open={vocabOpen}
        onClose={() => setVocabOpen(false)}
        onJumpToOccurrence={handleJumpToOccurrence}
        onDeckChanged={() => {
          refreshVocabCount();
          if (currentEpisodeId) loadEpisodeDetail(currentEpisodeId);
        }}
        onToast={showToast}
      />

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={(res) => setSettingsInfo(res)}
        onToast={showToast}
      />

      {toastMsg && (
        <div className="toast-3d" role="status" aria-live="polite">
          <span>{toastMsg}</span>
        </div>
      )}
    </>
  );
}
