import React from 'react';
import { BookMarked, FolderOpen, Headphones, LogOut, Power, Settings2 } from 'lucide-react';

const SKINS = [
  { id: 'citrus', label: '柑橘旋钮机', color: '#FF7A2D' },
  { id: 'lavender', label: '薰衣草工坊', color: '#B5A1FF' },
  { id: 'ceramic', label: '奶油陶瓷台', color: '#EAE7DF' },
];

export default function TopBar({
  activeView,
  onSwitchView,
  currentEpisode,
  episodeCount,
  processingCount,
  vocabCount,
  skin,
  onChangeSkin,
  onOpenVocab,
  onOpenSettings,
  authEnabled,
  onLogout,
  desktopMode,
  onShutdownDesktop,
  isRecording = false,
}) {
  return (
    <header className="top-bar">
      <div className="brand-group">
        <button
          type="button"
          className="brand-logo-btn"
          disabled={isRecording}
          onClick={() => onSwitchView('machine')}
          title="回到 Lingo 学习机"
          aria-label="Lingo 首页"
        >
          <img src="/lingo-logo.png" alt="Lingo" className="brand-wordmark" />
        </button>

        {currentEpisode && (
          <button
            type="button"
            className="brand-ep-btn"
            disabled={isRecording}
            onClick={() => onSwitchView('library')}
            title={isRecording ? '录音进行中已锁定切换篇目' : '前往资料库切换或上传新视频'}
          >
            <span>{currentEpisode.title}</span>
            <span className="pill-3d dark tnum">{currentEpisode.difficulty}</span>
          </button>
        )}
      </div>

      {/* Simplified 2-Tab Navigation: 学习机 & 资料库 (Upload + Pipeline integrated in 资料库) */}
      <nav className="primary-nav" aria-label="主导航">
        <button
          type="button"
          className={`chunk chunk-cream primary-tab ${activeView === 'machine' ? 'active' : ''}`}
          disabled={isRecording}
          onClick={() => onSwitchView('machine')}
        >
          <Headphones size={17} strokeWidth={2.4} />
          <span>学习机</span>
        </button>
        <button
          type="button"
          className={`chunk chunk-cream primary-tab ${activeView === 'library' ? 'active' : ''}`}
          disabled={isRecording}
          onClick={() => onSwitchView('library')}
        >
          <FolderOpen size={17} strokeWidth={2.4} />
          <span>资料库</span>
          {processingCount > 0 ? (
            <span className="nav-badge busy tnum" title="正在自动拆解中">
              拆解 {processingCount}
            </span>
          ) : (
            <span className="nav-badge tnum">{episodeCount}</span>
          )}
        </button>
      </nav>

      <div className="utility-rack">
        {isRecording && (
          <span className="pill-3d coral" role="status">
            录音锁定中
          </span>
        )}

        <div className="skin-dots" role="group" aria-label="切换学习机外壳配色">
          {SKINS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`skin-dot ${skin === s.id ? 'active' : ''}`}
              style={{ background: s.color }}
              disabled={isRecording}
              onClick={() => onChangeSkin(s.id)}
              title={`外壳皮肤：${s.label}`}
              aria-label={`切换到${s.label}`}
            />
          ))}
        </div>

        <button
          type="button"
          className="chunk chunk-cream chunk-sm"
          disabled={isRecording}
          onClick={onOpenVocab}
          title="打开个人生词本与闪卡复习"
        >
          <BookMarked size={16} strokeWidth={2.3} />
          <span>生词本</span>
          <span className="tnum">({vocabCount})</span>
        </button>

        <button
          type="button"
          className="chunk chunk-dark chunk-sm"
          disabled={isRecording}
          onClick={onOpenSettings}
          title="配置云端 API 或本地离线拆解引擎"
        >
          <Settings2 size={16} strokeWidth={2.3} />
          <span>引擎</span>
        </button>

        {authEnabled && (
          <button
            type="button"
            className="chunk chunk-coral chunk-sm"
            disabled={isRecording}
            onClick={onLogout}
            title="锁定并退出当前访问会话"
            aria-label="锁定退出"
          >
            <LogOut size={15} strokeWidth={2.3} />
          </button>
        )}

        {desktopMode && (
          <button
            type="button"
            className="chunk chunk-white chunk-sm"
            disabled={isRecording}
            onClick={onShutdownDesktop}
            title="关闭本机 Lingo 后台服务"
            aria-label="关闭本机服务"
          >
            <Power size={15} strokeWidth={2.3} />
          </button>
        )}
      </div>
    </header>
  );
}
