import React, { useState } from 'react';
import { Lock, ShieldCheck, Unlock } from 'lucide-react';
import { api } from '../api';

export default function LoginGate({ onUnlocked }) {
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!password.trim()) {
      setError('请输入访问口令');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await api.login(password);
      onUnlocked();
    } catch (err) {
      setError(err.message || '访问口令验证失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      <section
        style={{
          width: '100%',
          maxWidth: 440,
          background: 'var(--panel-bg)',
          borderRadius: 30,
          padding: '32px 30px 30px',
          boxShadow:
            '0 12px 0 var(--panel-deep), inset 0 4px 0 #FFFFFF, 0 26px 46px var(--shell-shadow)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 16,
          textAlign: 'center',
        }}
      >
        <img
          src="/lingo-logo.png"
          alt="Lingo"
          style={{
            height: 74,
            width: 'auto',
            objectFit: 'contain',
            display: 'block',
            filter: 'drop-shadow(0 5px 8px rgba(27, 19, 48, 0.14))',
          }}
        />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <span className="pill-3d dark">
              <ShieldCheck size={14} />
              <span>云端安全访问锁</span>
            </span>
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 900, letterSpacing: '-0.02em' }}>Lingo 学习机</h1>
          <p style={{ fontSize: 14, color: 'var(--ink-sub)', fontWeight: 600 }}>
            当前服务已开启公网口令保护，请输入访问口令解锁你的资料库与精听主机。
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 12, marginTop: 4 }}
        >
          <div style={{ textAlign: 'left' }}>
            <label className="field-label" htmlFor="access-password-input">
              访问口令
            </label>
            <div style={{ position: 'relative' }}>
              <Lock
                size={16}
                style={{
                  position: 'absolute',
                  left: 13,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--ink-sub)',
                  pointerEvents: 'none',
                }}
              />
              <input
                id="access-password-input"
                type="password"
                autoFocus
                autoComplete="current-password"
                className="input-3d"
                style={{ paddingLeft: 38, height: 46, fontSize: 15 }}
                placeholder="请输入服务器配置的访问口令..."
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          {error && (
            <div
              className="pill-3d coral"
              role="alert"
              style={{ justifyContent: 'center', padding: '7px 12px', borderRadius: 12 }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            className="chunk chunk-dark"
            style={{ width: '100%', height: 48, fontSize: 15 }}
            disabled={submitting}
          >
            <Unlock size={17} />
            <span>{submitting ? '正在验证口令...' : '解锁进入学习机'}</span>
          </button>
        </form>
      </section>
    </main>
  );
}
