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

interface PropsPainelDebug {
  logs: LogEntry[];
  onClear: () => void;
}

const ROTULOS_NIVEL: Record<LogLevel, string> = {
  info:    'Info',
  success: 'Sucesso',
  warning: 'Aviso',
  error:   'Erro',
  debug:   'Debug',
};

const CONFIGURACAO_NIVEL: Record<LogLevel, { icone: string; cor: string; fundo: string }> = {
  info:    { icone: 'ℹ',  cor: '#a0c4ff', fundo: 'rgba(100, 160, 255, 0.08)' },
  success: { icone: '✓',  cor: '#43e97b', fundo: 'rgba(67, 233, 123, 0.08)'  },
  warning: { icone: '⚠',  cor: '#f6d365', fundo: 'rgba(246, 211, 101, 0.08)' },
  error:   { icone: '✕',  cor: '#f5576c', fundo: 'rgba(245, 87, 108, 0.08)'  },
  debug:   { icone: '⬡',  cor: '#c084fc', fundo: 'rgba(192, 132, 252, 0.08)' },
};

export default function DebugPanel({ logs, onClear }: PropsPainelDebug) {
  const [aberto, setAberto] = useState(false);
  const [filtro, setFiltro] = useState<LogLevel | 'todos'>('todos');
  const [autoRolagem, setAutoRolagem] = useState(true);
  const refLista = useRef<HTMLDivElement>(null);
  const refTamanhoAnterior = useRef(0);

  // Auto-scroll quando novos logs chegam
  useEffect(() => {
    if (autoRolagem && aberto && logs.length !== refTamanhoAnterior.current) {
      refLista.current?.scrollTo({ top: refLista.current.scrollHeight, behavior: 'smooth' });
    }
    refTamanhoAnterior.current = logs.length;
  }, [logs, autoRolagem, aberto]);

  const logsFiltrados = filtro === 'todos' ? logs : logs.filter(l => l.level === filtro);

  const contadores = logs.reduce((acc, l) => {
    acc[l.level] = (acc[l.level] ?? 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const temErros  = (contadores.error   ?? 0) > 0;
  const temAvisos = (contadores.warning ?? 0) > 0;

  const corBadge = temErros
    ? '#f5576c'
    : temAvisos
    ? '#f6d365'
    : '#43e97b';

  const copiarTodos = useCallback(() => {
    const texto = logs
      .map(l => `[${l.timestamp}] [${l.level.toUpperCase()}] ${l.message}${l.detail ? ' — ' + l.detail : ''}`)
      .join('\n');
    navigator.clipboard.writeText(texto).catch(() => {});
  }, [logs]);

  return (
    <div style={{ position: 'fixed', bottom: '1.5rem', right: '1.5rem', zIndex: 9999 }}>
      {/* Botão flutuante */}
      {!aberto && (
        <button
          onClick={() => setAberto(true)}
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
          onMouseEnter={e => (e.currentTarget.style.borderColor = corBadge)}
          onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)')}
        >
          <span style={{ fontSize: '1rem' }}>🖥</span>
          <span>Logs</span>
          {logs.length > 0 && (
            <span style={{
              padding: '0.1rem 0.45rem',
              background: corBadge,
              color: temErros || temAvisos ? '#0a0a1a' : '#0a0a1a',
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
      {aberto && (
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
          {/* Cabeçalho */}
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
              {(['todos', 'info', 'success', 'warning', 'error', 'debug'] as const).map(lvl => {
                const ehNivel = lvl !== 'todos';
                const nivelConfig = ehNivel ? CONFIGURACAO_NIVEL[lvl] : null;
                const rotulo = lvl === 'todos' ? `Todos (${logs.length})` : `${ROTULOS_NIVEL[lvl]}${contadores[lvl] ? ` (${contadores[lvl]})` : ''}`;

                return (
                  <button
                    key={lvl}
                    onClick={() => setFiltro(lvl)}
                    title={lvl === 'todos' ? 'Todos' : ROTULOS_NIVEL[lvl]}
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
                      background: filtro === lvl
                        ? (lvl === 'todos' ? 'rgba(255,255,255,0.15)' : nivelConfig!.fundo)
                        : 'transparent',
                      color: filtro === lvl
                        ? (lvl === 'todos' ? '#e8e8f0' : nivelConfig!.cor)
                        : 'rgba(255,255,255,0.35)',
                      transition: 'all 150ms',
                    }}
                  >
                    {rotulo}
                  </button>
                );
              })}
            </div>

            {/* Ações */}
            <div style={{ display: 'flex', gap: '0.25rem', marginLeft: '0.25rem' }}>
              <button
                onClick={() => setAutoRolagem(s => !s)}
                title={autoRolagem ? 'Desativar auto-rolagem' : 'Ativar auto-rolagem'}
                style={{
                  padding: '0.25rem 0.45rem',
                  fontSize: '0.7rem',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  background: autoRolagem ? 'rgba(102,126,234,0.25)' : 'transparent',
                  color: autoRolagem ? '#a78bfa' : 'rgba(255,255,255,0.3)',
                  transition: 'all 150ms',
                }}
              >
                ⇓
              </button>
              <button
                onClick={copiarTodos}
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
                onClick={() => setAberto(false)}
                title="Fechar painel"
                style={{
                  padding: '0.25rem 0.5rem',
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  border: '1px solid rgba(245, 87, 108, 0.3)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  background: 'rgba(245, 87, 108, 0.1)',
                  color: '#f5576c',
                  transition: 'all 150ms',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'rgba(245, 87, 108, 0.25)';
                  e.currentTarget.style.borderColor = '#f5576c';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'rgba(245, 87, 108, 0.1)';
                  e.currentTarget.style.borderColor = 'rgba(245, 87, 108, 0.3)';
                }}
              >
                ✕ Fechar
              </button>
            </div>
          </div>

          {/* Lista de logs */}
          <div
            ref={refLista}
            onScroll={e => {
              const el = e.currentTarget;
              const noFinal = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
              setAutoRolagem(noFinal);
            }}
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '0.375rem 0',
              scrollbarWidth: 'thin',
              scrollbarColor: 'rgba(255,255,255,0.1) transparent',
            }}
          >
            {logsFiltrados.length === 0 ? (
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
                Nenhum log{filtro !== 'todos' ? ` de nível "${ROTULOS_NIVEL[filtro]}"` : ''}
              </div>
            ) : (
              logsFiltrados.map(entrada => {
                const cfg = CONFIGURACAO_NIVEL[entrada.level];
                return (
                  <div
                    key={entrada.id}
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
                      (e.currentTarget as HTMLDivElement).style.background = cfg.fundo;
                      (e.currentTarget as HTMLDivElement).style.borderLeftColor = cfg.cor;
                    }}
                    onMouseLeave={e => {
                      (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                      (e.currentTarget as HTMLDivElement).style.borderLeftColor = 'transparent';
                    }}
                  >
                    {/* Marca de tempo */}
                    <span style={{ color: 'rgba(255,255,255,0.25)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', fontSize: '0.68rem' }}>
                      {entrada.timestamp}
                    </span>
                    {/* Badge do nível */}
                    <span style={{
                      color: cfg.cor,
                      fontWeight: 700,
                      fontSize: '0.65rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      whiteSpace: 'nowrap',
                      minWidth: '3.5rem',
                    }}>
                      {cfg.icone} {ROTULOS_NIVEL[entrada.level]}
                    </span>
                    {/* Mensagem */}
                    <span style={{ color: '#d0d0e8', wordBreak: 'break-word' }}>
                      {entrada.message}
                      {entrada.detail && (
                        <span style={{ color: 'rgba(255,255,255,0.35)', marginLeft: '0.4rem' }}>
                          — {entrada.detail}
                        </span>
                      )}
                    </span>
                  </div>
                );
              })
            )}
          </div>

          {/* Rodapé */}
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
              {logsFiltrados.length} entrada{logsFiltrados.length !== 1 ? 's' : ''}
              {filtro !== 'todos' ? ` (filtrado: ${ROTULOS_NIVEL[filtro]})` : ''}
            </span>
            <span style={{
              fontSize: '0.65rem',
              color: autoRolagem ? '#a78bfa' : 'rgba(255,255,255,0.2)',
            }}>
              {autoRolagem ? '⇓ auto-rolagem ativa' : '⇓ auto-rolagem pausada'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
