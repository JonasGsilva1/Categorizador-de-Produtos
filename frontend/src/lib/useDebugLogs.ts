import { useState, useCallback, useRef } from 'react';
import type { LogEntry, LogLevel } from '@/components/DebugPanel';

const MAX_LOGS = 200;

export function useDebugLogs() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const counterRef = useRef(0);

  const addLog = useCallback((level: LogLevel, message: string, detail?: string) => {
    const now = new Date();
    const timestamp = now.toLocaleTimeString('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    const entry: LogEntry = {
      id: ++counterRef.current,
      timestamp,
      level,
      message,
      detail,
    };
    setLogs(prev => {
      const next = [...prev, entry];
      return next.length > MAX_LOGS ? next.slice(next.length - MAX_LOGS) : next;
    });
  }, []);

  const log     = useCallback((msg: string, detail?: string) => addLog('info',    msg, detail), [addLog]);
  const success = useCallback((msg: string, detail?: string) => addLog('success', msg, detail), [addLog]);
  const warn    = useCallback((msg: string, detail?: string) => addLog('warning', msg, detail), [addLog]);
  const error   = useCallback((msg: string, detail?: string) => addLog('error',   msg, detail), [addLog]);
  const debug   = useCallback((msg: string, detail?: string) => addLog('debug',   msg, detail), [addLog]);
  const clear   = useCallback(() => setLogs([]), []);

  return { logs, log, success, warn, error, debug, clear };
}
