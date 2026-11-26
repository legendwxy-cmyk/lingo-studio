import React, { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  FileText,
  Film,
  Headphones,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react';
import { api } from '../api';
import { formatTime } from '../utils/speech';

const DIFFICULTIES = ['全部', 'A2', 'B1', 'B2', 'C1'];

export default function LibraryWorkspace({
  episodes,
  currentEpisodeId,
  settingsInfo,
  onSelectEpisode,
  onRefreshEpisodes,
  onOpenSettings,
  onToast,
}) {
  const [uploadOpen, setUploadOpen] = useState(true);
  const [mediaFile, setMediaFile] = useState(null);
  const [subtitleFile, setSubtitleFile] = useState(null);
  const [title, setTitle] = useState('');
  const [seriesName, setSeriesName] = useState('自建精听库');
  const [difficulty, setDifficulty] = useState('B1');
  const [description, setDescription] = useState('');
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [trackedEpisodeId, setTrackedEpisodeId] = useState(null);
  const [trackedStatus, setTrackedStatus] = useState(null);

  const [searchText, setSearchText] = useState('');
  const [diffFilter, setDiffFilter] = useState('全部');

  const mediaInputRef = useRef(null);
  const subInputRef = useRef(null);

  // Auto-select any currently processing episode or the newest episode for pipeline preview
  useEffect(() => {
    const busy = episodes.find((e) => e.status === 'processing' || e.status === 'queued');
    if (busy && trackedEpisodeId !== busy.id) {
      setTrackedEpisodeId(busy.id);
      setTrackedStatus({
        id: busy.id,
        title: busy.title,
        status: busy.status,
        pipeline_steps: busy.pipeline_steps,
        error_message: busy.error_message,
        engine_used: busy.engine_used,
        subtitle_count: busy.subtitle_count,
        entry_count: busy.entry_count,
      });
    } else if (!trackedEpisodeId && episodes.length > 0) {
      const first = episodes[0];
      setTrackedEpisodeId(first.id);
      setTrackedStatus({
        id: first.id,
        title: first.title,
        status: first.status,
        pipeline_steps: first.pipeline_steps,
        error_message: first.error_message,
        engine_used: first.engine_used,
        subtitle_count: first.subtitle_count,
        entry_count: first.entry_count,
      });
    }
  }, [episodes, trackedEpisodeId]);

  // Poll active decomposing episode every 1.2 seconds (only depend on status, not entire object)
  const trackedStatusValue = trackedStatus?.status || '';
  useEffect(() => {
    if (!trackedEpisodeId) return undefined;
    const isBusy =
      !trackedStatusValue ||
      trackedStatusValue === 'queued' ||
      trackedStatusValue === 'processing';
    if (!isBusy) return undefined;

    const timer = setInterval(async () => {
      try {
        const st = await api.getEpisodeStatus(trackedEpisodeId);
        setTrackedStatus(st);
        if (st.status === 'ready') {
          onToast(`「${st.title}」拆解完成，已生成 ${st.subtitle_count} 句与 ${st.entry_count} 组词块`);
          onRefreshEpisodes();
        } else if (st.status === 'error') {
          onToast(`拆解异常：${st.error_message}`);
          onRefreshEpisodes();
        }
      } catch (err) {
        if (err && err.status === 404) {
          setTrackedEpisodeId(null);
          setTrackedStatus(null);
        }
      }
    }, 1200);
    return () => clearInterval(timer);
  }, [trackedEpisodeId, trackedStatusValue, onRefreshEpisodes, onToast]);

  const handlePickMedia = (file) => {
    if (!file) return;
    setMediaFile(file);
    if (!title.trim()) {
      const clean = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim();
      setTitle(clean);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files || []);
    for (const f of files) {
      if (/\.(srt|vtt)$/i.test(f.name)) {
        setSubtitleFile(f);
      } else {
        handlePickMedia(f);
      }
    }
  };

  const handleSubmitUpload = async (e) => {
    e.preventDefault();
    if (!mediaFile) {
      onToast('请先选择视频或音频文件');
      return;
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append('media_file', mediaFile);
      if (subtitleFile) fd.append('subtitle_file', subtitleFile);
      fd.append('title', title.trim() || mediaFile.name);
      fd.append('series_name', seriesName.trim() || '自建精听库');
      fd.append('difficulty', difficulty);
      fd.append('description', description.trim());

      const { episode } = await api.uploadEpisode(fd);
      setTrackedEpisodeId(episode.id);
      setTrackedStatus({
        id: episode.id,
        title: episode.title,
        status: episode.status,
        pipeline_steps: episode.pipeline_steps,
        error_message: '',
        engine_used: '',
        subtitle_count: 0,
        entry_count: 0,
      });
      setMediaFile(null);
      setSubtitleFile(null);
      setTitle('');
      setDescription('');
      onToast(`已投入拆解流水线：「${episode.title}」`);
      onRefreshEpisodes();
    } catch (err) {
      onToast(err.message || '上传失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReprocess = async (ep) => {
    if (
      ep.recording_count > 0 &&
      !window.confirm(`「${ep.title}」已有 ${ep.recording_count} 条跟读录音，重新拆解会清空旧字幕与跟读录音，确定继续吗？`)
    ) {
      return;
    }
    try {
      await api.reprocessEpisode(ep.id);
      setTrackedEpisodeId(ep.id);
      setTrackedStatus({
        id: ep.id,
        title: ep.title,
        status: 'processing',
        pipeline_steps: ep.pipeline_steps,
        error_message: '',
        engine_used: '',
        subtitle_count: ep.subtitle_count,
        entry_count: ep.entry_count,
      });
      setUploadOpen(true);
      onToast(`正在重新拆解「${ep.title}」`);
      onRefreshEpisodes();
    } catch (err) {
      onToast(err.message || '重新拆解失败');
    }
  };

  const handleToggleDone = async (ep) => {
    try {
      await api.patchEpisode(ep.id, { is_completed: !ep.is_completed });
      onRefreshEpisodes();
    } catch (err) {
      onToast(err.message || '更新状态失败');
    }
  };

  const handleDelete = async (ep) => {
    if (!window.confirm(`确定删除「${ep.title}」及其音画与跟读录音吗？`)) return;
    try {
      await api.deleteEpisode(ep.id);
      onToast(`已删除「${ep.title}」`);
      if (trackedEpisodeId === ep.id) {
        setTrackedEpisodeId(null);
        setTrackedStatus(null);
      }
      onRefreshEpisodes();
    } catch (err) {
      onToast(err.message || '删除失败');
    }
  };

  const filteredEpisodes = episodes.filter((ep) => {
    if (diffFilter !== '全部' && ep.difficulty !== diffFilter) return false;
    if (searchText.trim()) {
      const q = searchText.trim().toLowerCase();
      const hay = `${ep.title} ${ep.description} ${ep.series_name}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const engineModeLabel =
    settingsInfo?.has_llm_key || settingsInfo?.has_asr_key
      ? '云端 API + 本地混排引擎'
      : '零密钥本地离线引擎（支持 SRT 与 faster-whisper）';

  return (
    <main className="library-shell">
      {/* Integrated Upload & 5-Step Auto-Decomposition Bay */}
      <section className="upload-bay">
        <div className="upload-bay-head">
          <div className="upload-bay-title">
            <span className="pill-3d dark">投料与自动拆解</span>
            <h2>上传视频物料，自动拆解入库</h2>
          </div>

          <div className="toolbar-group">
            <button
              type="button"
              className="pill-3d mint"
              onClick={onOpenSettings}
              title="点击切换云端 API 或本地模型"
            >
              <Cpu size={14} />
              <span>{engineModeLabel}</span>
            </button>
            <button
              type="button"
              className="chunk chunk-white chunk-sm"
              onClick={() => setUploadOpen((v) => !v)}
            >
              {uploadOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              <span>{uploadOpen ? '收起投料台' : '展开上传物料'}</span>
            </button>
          </div>
        </div>

        {uploadOpen && (
          <form onSubmit={handleSubmitUpload}>
            <div className="upload-grid">
              <div
                className={`dropzone-3d ${dragging ? 'dragging' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                onClick={() => mediaInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    mediaInputRef.current?.click();
                  }
                }}
              >
                <input
                  ref={mediaInputRef}
                  type="file"
                  accept="video/*,audio/*,.mp4,.mov,.webm,.mkv,.mp3,.wav,.m4a"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    handlePickMedia(e.target.files?.[0]);
                    e.target.value = '';
                  }}
                />
                <input
                  ref={subInputRef}
                  type="file"
                  accept=".srt,.vtt"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    setSubtitleFile(e.target.files?.[0] || null);
                    e.target.value = '';
                  }}
                />

                <div className="chunk chunk-yellow" style={{ pointerEvents: 'none' }}>
                  <Upload size={18} />
                  <span>{mediaFile ? '更换视频或音频文件' : '拖拽或点击选择视频 / 音频'}</span>
                </div>

                {mediaFile ? (
                  <div className="pill-3d dark">
                    <Film size={14} />
                    <span>
                      {mediaFile.name} ({(mediaFile.size / 1024 / 1024).toFixed(1)} MB)
                    </span>
                  </div>
                ) : (
                  <p style={{ fontSize: 13.5, color: 'var(--ink-sub)', fontWeight: 700 }}>
                    支持 MP4、MOV、WebM、MP3、WAV、M4A；不传字幕时自动语音识别断句
                  </p>
                )}

                <div
                  style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}
                  onClick={(ev) => ev.stopPropagation()}
                >
                  <button
                    type="button"
                    className="chunk chunk-white chunk-sm"
                    onClick={() => subInputRef.current?.click()}
                  >
                    <FileText size={14} />
                    <span>{subtitleFile ? `字幕：${subtitleFile.name}` : '附带 SRT / VTT 字幕（可选）'}</span>
                  </button>
                  {subtitleFile && (
                    <button
                      type="button"
                      className="pill-3d coral"
                      onClick={() => setSubtitleFile(null)}
                    >
                      清除字幕
                    </button>
                  )}
                </div>
              </div>

              <div className="upload-meta-form">
                <div>
                  <label className="field-label" htmlFor="ep-title-input">
                    物料标题
                  </label>
                  <input
                    id="ep-title-input"
                    className="input-3d"
                    placeholder="例如：TED 演讲精听 03 刻意练习"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                  />
                </div>

                <div className="form-row-2">
                  <div>
                    <label className="field-label" htmlFor="ep-series-input">
                      所属合集
                    </label>
                    <input
                      id="ep-series-input"
                      className="input-3d"
                      value={seriesName}
                      onChange={(e) => setSeriesName(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="ep-diff-select">
                      难度评级
                    </label>
                    <select
                      id="ep-diff-select"
                      className="select-3d"
                      value={difficulty}
                      onChange={(e) => setDifficulty(e.target.value)}
                    >
                      <option value="A2">A2 基础入门</option>
                      <option value="B1">B1 日常进阶</option>
                      <option value="B2">B2 职场与访谈</option>
                      <option value="C1">C1 高阶学术</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="field-label" htmlFor="ep-desc-input">
                    学习备注（选填）
                  </label>
                  <input
                    id="ep-desc-input"
                    className="input-3d"
                    placeholder="记录语料来源或重点训练目标"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
                  <button
                    type="submit"
                    className="chunk chunk-dark"
                    disabled={submitting || !mediaFile}
                  >
                    {submitting ? (
                      <Loader2 size={16} className="spin-icon" />
                    ) : (
                      <Sparkles size={16} />
                    )}
                    <span>{submitting ? '正在提交物料...' : '开始 5 步自动拆解'}</span>
                  </button>
                </div>
              </div>
            </div>
          </form>
        )}

        {/* Live 5-Step Decomposition Pipeline Integrated Inside Library */}
        {trackedStatus && (
          <div className="pipeline-panel">
            <div className="pipeline-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span
                  className={`pill-3d ${
                    trackedStatus.status === 'ready'
                      ? 'mint'
                      : trackedStatus.status === 'error'
                        ? 'coral'
                        : 'dark'
                  }`}
                >
                  {trackedStatus.status === 'ready'
                    ? '拆解就绪'
                    : trackedStatus.status === 'error'
                      ? '拆解受阻'
                      : '流水线运行中'}
                </span>
                <strong style={{ fontSize: 15 }}>
                  最近拆解任务：「{trackedStatus.title}」
                </strong>
                {trackedStatus.engine_used && (
                  <span className="pill-3d">{trackedStatus.engine_used}</span>
                )}
              </div>

              {trackedStatus.status === 'ready' && (
                <button
                  type="button"
                  className="chunk chunk-yellow chunk-sm"
                  onClick={() => onSelectEpisode(trackedStatus.id)}
                >
                  <Headphones size={15} />
                  <span>装入学习机精听</span>
                </button>
              )}
            </div>

            {trackedStatus.status === 'error' && trackedStatus.error_message && (
              <div
                role="alert"
                style={{
                  background: '#FFE4E9',
                  color: '#850E29',
                  borderRadius: 12,
                  padding: '8px 12px',
                  fontSize: 13.5,
                  fontWeight: 800,
                }}
              >
                失败原因：{trackedStatus.error_message}
              </div>
            )}

            <div className="pipe-grid-3d">
              {(trackedStatus.pipeline_steps || []).map((st, idx) => (
                <div key={st.key} className={`pipe-card-3d ${st.status}`}>
                  <span className="pipe-step-tag tnum">
                    步骤 #{idx + 1}{' '}
                    {st.status === 'done'
                      ? '已完成'
                      : st.status === 'running'
                        ? '处理中'
                        : st.status === 'error'
                          ? '失败'
                          : '排队中'}
                  </span>
                  <div className="pipe-step-name">{st.label}</div>
                  <div className="pipe-step-detail">{st.detail}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Episode Cassette Library Shelf */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="library-toolbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <h2 style={{ fontSize: 20, fontWeight: 900 }}>语料卡带资料库</h2>
            <span className="pill-3d dark tnum">共 {filteredEpisodes.length} 篇</span>
            <div className="toolbar-group">
              {DIFFICULTIES.map((d) => (
                <button
                  key={d}
                  type="button"
                  className={`chunk chunk-sm ${diffFilter === d ? 'chunk-dark' : 'chunk-white'}`}
                  onClick={() => setDiffFilter(d)}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div className="library-search">
            <Search size={16} className="library-search-icon" />
            <input
              type="search"
              className="input-3d"
              placeholder="搜索标题、合集或备注..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
          </div>
        </div>

        {filteredEpisodes.length === 0 ? (
          <div className="practice-card" style={{ alignItems: 'center', padding: 34 }}>
            <strong style={{ fontSize: 16 }}>资料库里还没有匹配的语料</strong>
            <p style={{ color: 'var(--ink-sub)', fontSize: 14 }}>
              可在上方投料台拖入任意英语视频或音频，系统会自动拆解出双语字幕、IPA 音标与重点词块。
            </p>
          </div>
        ) : (
          <div className="lib-cards">
            {filteredEpisodes.map((ep) => {
              const isCurrent = ep.id === currentEpisodeId;
              return (
                <article key={ep.id} className={`lib-3d ${isCurrent ? 'active-ep' : ''}`}>
                  <div className="lib-cover-wrap">
                    {ep.cover_url ? (
                      <img src={ep.cover_url} alt={ep.title} />
                    ) : (
                      <div
                        style={{
                          width: '100%',
                          height: '100%',
                          display: 'grid',
                          placeItems: 'center',
                          color: '#FFE24C',
                        }}
                      >
                        <Film size={44} />
                      </div>
                    )}
                    <div className="lib-cover-badges">
                      <span className="pill-3d dark tnum">
                        {ep.difficulty} {formatTime(ep.duration_sec)}
                      </span>
                      <span
                        className={`pill-3d ${
                          ep.status === 'ready'
                            ? ep.is_completed
                              ? 'mint'
                              : ''
                            : ep.status === 'error'
                              ? 'coral'
                              : 'dark'
                        }`}
                      >
                        {ep.status === 'ready'
                          ? ep.is_completed
                            ? '已学完'
                            : '待精听'
                          : ep.status === 'error'
                            ? '拆解失败'
                            : '拆解中'}
                      </span>
                    </div>
                  </div>

                  <div className="lib-card-body">
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <h3 className="lib-card-title">{ep.title}</h3>
                      {isCurrent && <span className="pill-3d dark">当前装机</span>}
                    </div>
                    <p className="lib-card-desc">
                      {ep.description || `${ep.series_name}，自动拆解生成双语精听与词块练习卡带。`}
                    </p>
                    <div className="lib-meta-strip tnum">
                      <span className="pill-3d">{ep.series_name}</span>
                      <span className="pill-3d">{ep.subtitle_count} 句字幕</span>
                      <span className="pill-3d">{ep.entry_count} 组词块</span>
                      {ep.recording_count > 0 && (
                        <span className="pill-3d mint">{ep.recording_count} 条跟读</span>
                      )}
                    </div>

                    <div className="lib-actions">
                      <button
                        type="button"
                        className="chunk chunk-yellow chunk-sm"
                        style={{ flex: 1 }}
                        disabled={ep.status !== 'ready'}
                        onClick={() => onSelectEpisode(ep.id)}
                      >
                        <Headphones size={15} />
                        <span>{isCurrent ? '回到学习机' : '装入学习机'}</span>
                      </button>

                      <button
                        type="button"
                        className={`chunk chunk-sm ${ep.is_completed ? 'chunk-mint' : 'chunk-white'}`}
                        onClick={() => handleToggleDone(ep)}
                        title={ep.is_completed ? '取消已完成标记' : '标记本篇已学完'}
                      >
                        <CheckCircle2 size={15} />
                      </button>

                      <button
                        type="button"
                        className="chunk chunk-white chunk-sm"
                        onClick={() => handleReprocess(ep)}
                        title="重新执行 5 步拆解"
                      >
                        <RefreshCw size={15} />
                      </button>

                      <button
                        type="button"
                        className="chunk chunk-white chunk-sm"
                        onClick={() => handleDelete(ep)}
                        title="删除此篇目"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
