'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '@/lib/supabaseClient';
import FileUploader from '../components/FileUploader';
import ProcessingStatus from '../components/ProcessingStatus';
import FeedbackUploader from '../components/FeedbackUploader';
import DebugPanel from '../components/DebugPanel';
import ReviewPanel from '../components/ReviewPanel';
import { useDebugLogs } from '@/lib/useDebugLogs';
import { API_BASE } from '@/lib/api';

interface JobStatus {
  id: string;
  status: string;
  total_rows: number;
  processed_rows: number;
  aprovados: number;
  pendentes: number;
  erros: number;
  error_message: string | null;
}

export default function Home() {
  const router = useRouter();
  const [session, setSession] = useState<any>(null);
  
  const [file, setFile]   = useState<File | null>(null);
  const [job, setJob]     = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);

  const { logs, log, success, warn, error: logError, debug, clear } = useDebugLogs();

  // Verificação de Auth
  useEffect(() => {
    log('Verificando sessão Supabase...');
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        warn('Sessão não encontrada — redirecionando para login');
        router.push('/login');
      } else {
        success('Sessão válida', session.user.email);
        setSession(session);
      }
    });

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        warn('Sessão encerrada — redirecionando para login');
        router.push('/login');
      } else {
        setSession(session);
      }
    });

    return () => authListener.subscription.unsubscribe();
  }, [router]);

  // Polling do Job
  useEffect(() => {
    let interval: NodeJS.Timeout;

    const checkStatus = async () => {
      if (!job || !session) return;
      if (job.status === 'COMPLETED' || job.status === 'FAILED') return;

      debug(`Polling job ${job.id.slice(0, 8)}...`);
      try {
        const response = await fetch(`${API_BASE}/jobs/${job.id}`, {
          headers: { Authorization: `Bearer ${session.access_token}` }
        });

        debug(`Polling respondeu`, `HTTP ${response.status}`);
        
        if (response.ok) {
          const data: JobStatus = await response.json();
          if (data.status !== job.status) {
            log(`Status do job mudou: ${job.status} → ${data.status}`);
          }
          if (data.processed_rows !== job.processed_rows) {
            log(`Progresso: ${data.processed_rows}/${data.total_rows} itens processados`);
          }
          setJob(data);

          if (data.status === 'COMPLETED') {
            success(`Processamento concluído!`, `${data.aprovados} aprovados · ${data.pendentes} para revisão · ${data.erros} erros`);
          } else if (data.status === 'FAILED') {
            logError('Job falhou no backend', data.error_message ?? undefined);
          }
        } else {
          const body = await response.json().catch(() => null);
          warn(`Polling retornou erro`, `HTTP ${response.status} — ${body?.detail ?? response.statusText}`);
        }
      } catch (err) {
        logError('Erro de rede no polling', err instanceof Error ? err.message : String(err));
      }
    };

    if (job && (job.status === 'PENDING' || job.status === 'PROCESSING')) {
      interval = setInterval(checkStatus, 3000);
    }

    return () => clearInterval(interval);
  }, [job?.id, job?.status, session]);

  const handleCategorize = async () => {
    if (!file || !session) return;

    setError(null);
    setJob(null);
    log(`Enviando arquivo para categorização`, file.name);
    debug(`Endpoint: POST ${API_BASE}/categorize`);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_BASE}/categorize`, {
        method: 'POST',
        body: formData,
        headers: { Authorization: `Bearer ${session.access_token}` }
      });

      debug(`Resposta recebida`, `HTTP ${response.status}`);

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const msg = errorData?.detail || `Erro ${response.status}: ${response.statusText}`;
        logError('Falha ao iniciar job', msg);
        throw new Error(msg);
      }

      const data = await response.json();
      success(`Job criado com sucesso`, `ID: ${data.job_id}`);
      log('Aguardando início do processamento...');

      setJob({
        id: data.job_id,
        status: 'PENDING',
        total_rows: 0,
        processed_rows: 0,
        aprovados: 0,
        pendentes: 0,
        erros: 0,
        error_message: null
      });
      
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido ao iniciar.';
      const displayMsg = message === 'Failed to fetch'
        ? 'Não foi possível conectar ao backend. Verifique se BACKEND_URL (Vercel) e FRONTEND_URL (Railway) estão configurados corretamente.'
        : message;
      setError(displayMsg);
    }
  };

  const handleDownload = async () => {
    if (!job || !session) return;
    log(`Solicitando download do resultado`, `Job ${job.id.slice(0, 8)}`);
    debug(`Endpoint: GET ${API_BASE}/jobs/${job.id}/download`);
    try {
      const response = await fetch(`${API_BASE}/jobs/${job.id}/download`, {
        headers: { Authorization: `Bearer ${session.access_token}` }
      });

      debug(`Resposta download`, `HTTP ${response.status}`);

      if (!response.ok) {
        logError('Falha no download', `HTTP ${response.status}`);
        throw new Error("Erro ao baixar arquivo.");
      }

      success('Download iniciado com sucesso');
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `resultado_categorizado.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
      
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro no download.';
      logError('Erro no download', msg);
      setError(msg);
    }
  };

  if (!session) return null; // Previne piscar a tela antes de redirecionar

  return (
    <>
      <main className="app-container">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
          <div style={{ color: '#a0a0c0', fontSize: '0.875rem' }}>
            Logado como <strong>{session.user.email}</strong>
          </div>
          <button 
            onClick={() => supabase.auth.signOut()} 
            style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', color: '#e8e8f0', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer' }}
          >
            Sair
          </button>
        </div>

        <section className="hero" style={{ paddingTop: '1rem', marginBottom: '4rem' }}>
          <div className="hero-badge">
            <span className="hero-badge-dot"></span>
            Motor Gemini Ativo
          </div>
          <h1>Categorização Inteligente</h1>
          <p>
            Processamento em background otimizado para grandes planilhas (até 10.000 linhas).
          </p>
        </section>

        <div className="sections-grid">
          {/* --- Card 1: Categorização em Lote --- */}
          <div className="glass-card">
            <h2 className="section-title">
              <span className="section-title-icon categorize">⚡</span>
              Categorização em Lote
            </h2>
            <p className="section-description">
              O motor rodará em segundo plano. Você pode fechar a aba se quiser.
            </p>

            {!job && (
              <>
                <FileUploader
                  id="categorize-file-input"
                  onFileSelect={setFile}
                  selectedFile={file}
                  onClear={() => { setFile(null); setError(null); }}
                />
                <button
                  className="btn btn-primary btn-full"
                  onClick={handleCategorize}
                  disabled={!file}
                >
                  🚀 Iniciar Categorização Assíncrona
                </button>
              </>
            )}

            {job && (job.status === 'PENDING' || job.status === 'PROCESSING') && (
              <ProcessingStatus status={job.status} total={job.total_rows} processed={job.processed_rows} />
            )}

            {job?.status === 'COMPLETED' && !reviewing && (
              <div className="feedback-result" style={{ animation: 'none' }}>
                <ProcessingStatus status={job.status} total={job.total_rows} processed={job.processed_rows} />
                
                <div className="metrics-grid" style={{ marginTop: '1.5rem' }}>
                  <div className="metric-card">
                    <div className="metric-value total">{job.total_rows}</div>
                    <div className="metric-label">Total</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-value approved">{job.aprovados}</div>
                    <div className="metric-label">Aprovados</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-value pending">{job.pendentes}</div>
                    <div className="metric-label">Revisão</div>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
                  {job.pendentes > 0 ? (
                    <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => setReviewing(true)}>
                      🔍 Revisar {job.pendentes} pendente{job.pendentes > 1 ? 's' : ''} e baixar
                    </button>
                  ) : (
                    <button className="btn btn-success" style={{ flex: 1 }} onClick={handleDownload}>
                      ⬇️ Baixar Resultado
                    </button>
                  )}
                  <button className="btn" style={{ flex: 1, background: 'rgba(255,255,255,0.1)', color: '#fff' }}
                    onClick={() => { setJob(null); setFile(null); setReviewing(false); }}>
                    Nova Planilha
                  </button>
                </div>
              </div>
            )}

            {job?.status === 'COMPLETED' && reviewing && (
              <ReviewPanel
                jobId={job.id}
                session={session}
                onBack={() => setReviewing(false)}
                onFinalized={() => {
                  setReviewing(false);
                  success('Revisão finalizada — pronto para download!');
                  handleDownload();
                }}
              />
            )}

            {job?.status === 'FAILED' && (
              <div className="error-banner">
                <span className="error-banner-icon">❌</span>
                <span>Erro: {job.error_message}</span>
                <button className="btn btn-primary" style={{ marginLeft: 'auto' }} onClick={() => setJob(null)}>Tentar novamente</button>
              </div>
            )}

            {error && (
              <div className="error-banner" style={{ marginTop: '1rem' }}>
                <span className="error-banner-icon">⚠️</span>
                <span>{error}</span>
              </div>
            )}
          </div>

          {/* --- Card 2: Retroalimentação --- */}
          <div className="glass-card">
            <h2 className="section-title">
              <span className="section-title-icon feedback">🔄</span>
              Retroalimentação (Treinamento)
            </h2>
            <p className="section-description">
              Após revisar os produtos com "Baixa Confiança", faça o upload da planilha corrigida.
            </p>
            <FeedbackUploader session={session} />
          </div>
        </div>
      </main>

      <DebugPanel logs={logs} onClear={clear} />
    </>
  );
}
