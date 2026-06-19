'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';

export type LogLevel = 'info' | 'success' | 'warning' | 'error' | 'debug';

export interface LogEntry {
  id: number;
  timestamp: string;
  level: LogLevel;
  message: string;
  detail?: string;
}

interface DebugPanelProps {
  logs: LogEntry[];
  onClear: () => void;
}

const LEVEL_CONFIG: Record<LogLevel, { icon: string; color: string; bg: string }> = {
  info:    { icon: 'ℹ',  color: '#a0c4ff', bg: 'rgba(100, 160, 255, 0.08)' },
  success: { icon: '✓',  color: '#43e97b', bg: 'rgba(67, 233, 123, 0.08)'  },
  warning: { icon: '⚠',  color: '#f6d365', bg: 'rgba(246, 211, 101, 0.08)' },
  error:   { icon: '✕',  color: '#f5576c', bg: 'rgba(245, 87, 108, 0.08)'  },
  debug:   { icon: '⬡',  color: '#c084fc', bg: 'rgba(192, 132, 252, 0.08)' },
};

export default function DebugPanel({ logs, onClear }: DebugPanelProps) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<LogLevel | 'all'>('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const prevLenRef = useRef(0);

  // Auto-scroll quando novos logs chegam
  useEffect(() => {
    if (autoScroll && open && logs.length !== prevLenRef.current) {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
    }
    prevLenRef.current = logs.length;
  }, [logs, autoScroll, open]);

  const filtered = filter === 'all' ? logs : logs.filter(l => l.level === filter);

  const counts = logs.reduce((acc, l) => {
    acc[l.level] = (acc[l.level] ?? 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const hasErrors   = (counts.error   ?? 0) > 0;
  const hasWarnings = (counts.warning ?? 0) > 0;

  const badgeColor = hasErrors
    ? '#f5576c'
    : hasWarnings
    ? '#f6d365'
    : '#43e97b';

  const handleCopyAll = useCallback(() => {
    const text = logs
      .map(l => `[${l.timestamp}] [${l.level.toUpperCase()}] ${l.message}${l.detail ? ' — ' + l.detail : ''}`)
      .join('\n');
    navigator.clipboard.writeText(text).catch(() => {});
  }, [logs]);

  return (
    <div style={{ position: 'fixed', bottom: '1.5rem', right: '1.5rem', zIndex: 9999 }}>
      {/* Botão flutuante */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          title="Abrir painel de logs"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.6rem 1rem',
            background: 'rgba(20, 20, 50, 0.92)',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: '9999px',
            color: '#e8e8f0',
            fontSize: '0.8rem',
            fontWeight: 600,
            cursor: 'pointer',
            backdropFilter: 'blur(16px)',
            boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
            transition: 'all 200ms ease',
            fontFamily: 'inherit',
          }}
          onMouseEnter={e => (e.currentTarget.style.borderColor = badgeColor)}
          onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)')}
        >
          <span style={{ fontSize: '1rem' }}>🖥</span>
          <span>Logs</span>
          {logs.length > 0 && (
            <span style={{
              padding: '0.1rem 0.45rem',
              background: badgeColor,
              color: hasErrors || hasWarnings ? '#0a0a1a' : '#0a0a1a',
              borderRadius: '9999px',
              fontSize: '0.7rem',
              fontWeight: 700,
              minWidth: '1.4rem',
              textAlign: 'center',
            }}>
              {logs.length > 99 ? '99+' : logs.length}
            </span>
          )}
        </button>
      )}

      {/* Painel expandido */}
      {open && (
        <div style={{
          width: 'min(520px, calc(100vw - 2rem))',
          height: '420px',
          display: 'flex',
          flexDirection: 'column',
          background: 'rgba(10, 10, 26, 0.97)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '12px',
          boxShadow: '0 8px 40px rgba(0,0,0,0.7)',
          backdropFilter: 'blur(24px)',
          overflow: 'hidden',
          animation: 'fadeSlideUp 0.2s ease-out',
          fontFamily: 'inherit',
        }}>
          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.65rem 0.875rem',
            borderBottom: '1px solid rgba(255,255,255,0.07)',
            background: 'rgba(255,255,255,0.03)',
            flexShrink: 0,
          }}>
            <span style={{ fontSize: '0.85rem' }}>🖥</span>
            <span style={{ fontWeight: 700, fontSize: '0.8rem', color: '#e8e8f0', flex: 1 }}>
              Console de Logs
            </span>

            {/* Filtros de nível */}
            <div style={{ display: 'flex', gap: '0.25rem' }}>
              {(['all', 'info', 'success', 'warning', 'error', 'debug'] as const).map(lvl => (
                <button
                  key={lvl}
                  onClick={() => setFilter(lvl)}
                  title={lvl === 'all' ? 'Todos' : lvl}
                  style={{
                    padding: '0.2rem 0.45rem',
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    background: filter === lvl
                      ? (lvl === 'all' ? 'rgba(255,255,255,0.15)' : LEVEL_CONFIG[lvl].bg)
                      : 'transparent',
                    color: filter === lvl
                      ? (lvl === 'all' ? '#e8e8f0' : LEVEL_CONFIG[lvl].color)
                      : 'rgba(255,255,255,0.35)',
                    transition: 'all 150ms',
                  }}
                >
                  {lvl === 'all' ? `Todos (${logs.length})` : `${lvl}${counts[lvl] ? ` (${counts[lvl]})` : ''}`}
                </button>
              ))}
            </div>

            {/* Ações */}
            <div style={{ display: 'flex', gap: '0.25rem', marginLeft: '0.25rem' }}>
              <button
                onClick={() => setAutoScroll(s => !s)}
                title={autoScroll ? 'Desativar auto-scroll' : 'Ativar auto-scroll'}
                style={{
                  padding: '0.25rem 0.45rem',
                  fontSize: '0.7rem',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  background: autoScroll ? 'rgba(102,126,234,0.25)' : 'transparent',
                  color: autoScroll ? '#a78bfa' : 'rgba(255,255,255,0.3)',
                  transition: 'all 150ms',
                }}
              >
                ⇓
              </button>
              <button
                onClick={handleCopyAll}
                title="Copiar todos os logs"
                style={{
                  padding: '0.25rem 0.45rem',
                  fontSize: '0.7rem',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  background: 'transparent',
                  color: 'rgba(255,255,255,0.3)',
                  transition: 'all 150ms',
                }}
                onMouseEnter={e => (e.currentTarget.style.color = '#e8e8f0')}
                onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.3)')}
              >
                ⎘
              </button>
              <button
                onClick={onClear}
                title="Limpar logs"
                style={{
                  padding: '0.25rem 0.45rem',
                  fontSize: '0.7rem',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  background: 'transparent',
                  color: 'rgba(255,255,255,0.3)',
                  transition: 'all 150ms',
                }}
                onMouseEnter={e => (e.currentTarget.style.color = '#f5576c')}
                onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.3)')}
              >
                ✕ limpar
              </button>
              <button
                onClick={() => setOpen(false)}
                title="Minimizar"
                style={{
                  padding: '0.25rem 0.45rem',
                  fontSize: '0.7rem',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  background: 'transparent',
                  color: 'rgba(255,255,255,0.3)',
                  transition: 'all 150ms',
                }}
                onMouseEnter={e => (e.currentTarget.style.color = '#e8e8f0')}
                onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.3)')}
              >
                ─
              </button>
            </div>
          </div>

          {/* Lista de logs */}
          <div
            ref={listRef}
            onScroll={e => {
              const el = e.currentTarget;
              const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
              setAutoScroll(atBottom);
            }}
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '0.375rem 0',
              scrollbarWidth: 'thin',
              scrollbarColor: 'rgba(255,255,255,0.1) transparent',
            }}
          >
            {filtered.length === 0 ? (
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                color: 'rgba(255,255,255,0.2)',
                fontSize: '0.8rem',
                gap: '0.5rem',
              }}>
                <span style={{ fontSize: '1.5rem', opacity: 0.4 }}>📭</span>
                Nenhum log{filter !== 'all' ? ` de nível "${filter}"` : ''}
              </div>
            ) : (
              filtered.map(entry => {
                const cfg = LEVEL_CONFIG[entry.level];
                return (
                  <div
                    key={entry.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'auto auto 1fr',
                      gap: '0 0.5rem',
                      alignItems: 'baseline',
                      padding: '0.3rem 0.875rem',
                      fontSize: '0.73rem',
                      lineHeight: 1.5,
                      borderLeft: `2px solid transparent`,
                      transition: 'background 100ms',
                    }}
                    onMouseEnter={e => {
                      (e.currentTarget as HTMLDivElement).style.background = cfg.bg;
                      (e.currentTarget as HTMLDivElement).style.borderLeftColor = cfg.color;
                    }}
                    onMouseLeave={e => {
                      (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                      (e.currentTarget as HTMLDivElement).style.borderLeftColor = 'transparent';
                    }}
                  >
                    {/* Timestamp */}
                    <span style={{ color: 'rgba(255,255,255,0.25)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', fontSize: '0.68rem' }}>
                      {entry.timestamp}
                    </span>
                    {/* Badge nível */}
                    <span style={{
                      color: cfg.color,
                      fontWeight: 700,
                      fontSize: '0.65rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      whiteSpace: 'nowrap',
                      minWidth: '3.5rem',
                    }}>
                      {cfg.icon} {entry.level}
                    </span>
                    {/* Mensagem */}
                    <span style={{ color: '#d0d0e8', wordBreak: 'break-word' }}>
                      {entry.message}
                      {entry.detail && (
                        <span style={{ color: 'rgba(255,255,255,0.35)', marginLeft: '0.4rem' }}>
                          — {entry.detail}
                        </span>
                      )}
                    </span>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div style={{
            padding: '0.35rem 0.875rem',
            borderTop: '1px solid rgba(255,255,255,0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
            background: 'rgba(255,255,255,0.02)',
          }}>
            <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.2)' }}>
              {filtered.length} entrada{filtered.length !== 1 ? 's' : ''}
              {filter !== 'all' ? ` (filtrado: ${filter})` : ''}
            </span>
            <span style={{
              fontSize: '0.65rem',
              color: autoScroll ? '#a78bfa' : 'rgba(255,255,255,0.2)',
            }}>
              {autoScroll ? '⇓ auto-scroll ativo' : '⇓ auto-scroll pausado'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
