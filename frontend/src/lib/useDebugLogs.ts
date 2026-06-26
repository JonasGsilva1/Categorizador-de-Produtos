import { useState, useCallback, useRef } from 'react';
import type { LogEntry, LogLevel } from '@/components/DebugPanel';

const MAX_REGISTROS = 200;

export function useDebugLogs() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const contadorRef = useRef(0);

  const adicionarLog = useCallback((nivel: LogLevel, mensagem: string, detalhe?: string) => {
    const agora = new Date();
    const marcaTempo = agora.toLocaleTimeString('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    const entrada: LogEntry = {
      id: ++contadorRef.current,
      timestamp: marcaTempo,
      level: nivel,
      message: mensagem,
      detail: detalhe,
    };
    setLogs(anterior => {
      const proximo = [...anterior, entrada];
      return proximo.length > MAX_REGISTROS ? proximo.slice(proximo.length - MAX_REGISTROS) : proximo;
    });
  }, []);

  const log     = useCallback((msg: string, detalhe?: string) => adicionarLog('info',    msg, detalhe), [adicionarLog]);
  const success = useCallback((msg: string, detalhe?: string) => adicionarLog('success', msg, detalhe), [adicionarLog]);
  const warn    = useCallback((msg: string, detalhe?: string) => adicionarLog('warning', msg, detalhe), [adicionarLog]);
  const error   = useCallback((msg: string, detalhe?: string) => adicionarLog('error',   msg, detalhe), [adicionarLog]);
  const debug   = useCallback((msg: string, detalhe?: string) => adicionarLog('debug',   msg, detalhe), [adicionarLog]);
  const clear   = useCallback(() => setLogs([]), []);

  return { logs, log, success, warn, error, debug, clear };
}
