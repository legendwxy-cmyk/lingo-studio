import React, { useEffect, useState } from 'react';
import { CheckCircle2, Cpu, PlugZap, Save, X } from 'lucide-react';
import { api } from '../api';

const PRESETS = [
  { name: 'OpenAI', base: 'https://api.openai.com/v1', model: 'gpt-4o-mini', asrBase: 'https://api.openai.com/v1', asrModel: 'whisper-1' },
  { name: 'DeepSeek', base: 'https://api.deepseek.com/v1', model: 'deepseek-chat', asrBase: null, asrModel: null },
  { name: '通义千问', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', asrBase: null, asrModel: null },
  { name: 'Groq', base: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile', asrBase: 'https://api.groq.com/openai/v1', asrModel: 'whisper-large-v3-turbo' },
  { name: 'SiliconFlow', base: 'https://api.siliconflow.cn/v1', model: 'Qwen/Qwen2.5-72B-Instruct', asrBase: 'https://api.siliconflow.cn/v1', asrModel: 'FunAudioLLM/SenseVoiceSmall' },
  { name: 'Gemini 兼容', base: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.0-flash', asrBase: null, asrModel: null },
];

export default function SettingsModal({ open, onClose, onSaved, onToast }) {
  const [form, setForm] = useState({
    asr_mode: 'auto',
    asr_base_url: 'https://api.openai.com/v1',
    asr_api_key: '',
    asr_model: 'whisper-1',
    local_whisper_model: 'tiny.en',
    llm_base_url: 'https://api.openai.com/v1',
    llm_api_key: '',
    llm_model: 'gpt-4o-mini',
    enable_online_dict_fallback: 'true',
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    setTestResult(null);
    api
      .getSettings()
      .then((res) => {
        if (res.settings) setForm((prev) => ({ ...prev, ...res.settings }));
      })
      .catch(() => {});
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const applyPreset = (p) => {
    setForm((prev) => ({
      ...prev,
      llm_base_url: p.base,
      llm_model: p.model,
      ...(p.asrBase ? { asr_base_url: p.asrBase, asr_model: p.asrModel } : {}),
    }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.saveSettings(form);
      onSaved(res);
      onToast('引擎配置已保存');
      onClose();
    } catch (err) {
      onToast(err.message || '保存配置失败');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testLLM({
        base_url: form.llm_base_url,
        api_key: form.llm_api_key,
        model: form.llm_model,
      });
      setTestResult(res);
    } catch (err) {
      setTestResult({ ok: false, message: err.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-3d" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>
            <Cpu size={22} />
            <span>双引擎拆解与 AI 模型配置</span>
          </h2>
          <button type="button" className="chunk chunk-dark chunk-sm" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <form className="modal-body" onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="practice-card">
            <strong style={{ fontSize: 15 }}>不填 API Key 也能完整使用离线模式</strong>
            <p style={{ fontSize: 13.5, color: 'var(--ink-sub)' }}>
              离线模式下：上传视频自动通过 FFmpeg 抽帧与本地 faster-whisper 断句转写（或直接解析 SRT/VTT），再用内置 CMUdict IPA 与离线词库完成词块绑定；填写兼容 OpenAI 的 API Key 后可解锁云端高精度转写、逐句精译、AI 词典抽取与 AI 复述批改。
            </p>
            <div className="toolbar-group">
              <span style={{ fontSize: 13, fontWeight: 800 }}>一键填入厂商端点：</span>
              {PRESETS.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  className="chunk chunk-cream chunk-sm"
                  onClick={() => applyPreset(p)}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>

          <div className="practice-card">
            <h3 style={{ fontSize: 16, fontWeight: 900 }}>1. 语音转写引擎（无字幕视频时生效）</h3>
            <div className="form-row-2">
              <div>
                <label className="field-label">识别策略</label>
                <select
                  className="select-3d"
                  value={form.asr_mode}
                  onChange={(e) => setForm({ ...form, asr_mode: e.target.value })}
                >
                  <option value="auto">自动（有云端 Key 优先云端，否则本地 Whisper）</option>
                  <option value="local_whisper">强制本地离线 faster-whisper</option>
                  <option value="cloud_api">强制云端 Whisper API</option>
                  <option value="subtitle_only">仅使用上传的 SRT/VTT 字幕</option>
                </select>
              </div>
              <div>
                <label className="field-label">本地 faster-whisper 模型</label>
                <select
                  className="select-3d"
                  value={form.local_whisper_model}
                  onChange={(e) => setForm({ ...form, local_whisper_model: e.target.value })}
                >
                  <option value="tiny.en">tiny.en（极速，约 75MB）</option>
                  <option value="base.en">base.en（均衡推荐，约 145MB）</option>
                  <option value="small.en">small.en（高精度，约 480MB）</option>
                </select>
              </div>
            </div>

            <div className="form-row-2">
              <div>
                <label className="field-label">云端 ASR Base URL</label>
                <input
                  className="input-3d"
                  value={form.asr_base_url}
                  onChange={(e) => setForm({ ...form, asr_base_url: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">云端 ASR 模型名</label>
                <input
                  className="input-3d"
                  value={form.asr_model}
                  onChange={(e) => setForm({ ...form, asr_model: e.target.value })}
                />
              </div>
            </div>

            <div>
              <label className="field-label">云端 ASR API Key（留空则走离线模式）</label>
              <input
                type="password"
                className="input-3d"
                placeholder="sk-..."
                value={form.asr_api_key}
                onChange={(e) => setForm({ ...form, asr_api_key: e.target.value })}
              />
            </div>
          </div>

          <div className="practice-card">
            <h3 style={{ fontSize: 16, fontWeight: 900 }}>2. 大模型精译 / 词块抽取 / AI 教练引擎</h3>
            <div className="form-row-2">
              <div>
                <label className="field-label">LLM Base URL（OpenAI 兼容接口）</label>
                <input
                  className="input-3d"
                  value={form.llm_base_url}
                  onChange={(e) => setForm({ ...form, llm_base_url: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">LLM 模型名</label>
                <input
                  className="input-3d"
                  value={form.llm_model}
                  onChange={(e) => setForm({ ...form, llm_model: e.target.value })}
                />
              </div>
            </div>

            <div>
              <label className="field-label">LLM API Key（留空则使用内置离线词典与语法引擎）</label>
              <input
                type="password"
                className="input-3d"
                placeholder="sk-..."
                value={form.llm_api_key}
                onChange={(e) => setForm({ ...form, llm_api_key: e.target.value })}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="chunk chunk-white chunk-sm"
                disabled={testing}
                onClick={handleTest}
              >
                <PlugZap size={15} />
                <span>{testing ? '测试中...' : '测试 LLM 连通性'}</span>
              </button>

              {testResult && (
                <span className={`pill-3d ${testResult.ok ? 'mint' : 'coral'}`}>
                  {testResult.ok && <CheckCircle2 size={14} />}
                  <span>{testResult.message}</span>
                </span>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button type="button" className="chunk chunk-white" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="chunk chunk-dark" disabled={saving}>
              <Save size={16} />
              <span>{saving ? '保存中...' : '保存引擎配置'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
