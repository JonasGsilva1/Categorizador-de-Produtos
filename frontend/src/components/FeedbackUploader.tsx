'use client';

import React, { useState } from 'react';
import FileUploader from './FileUploader';
import { API_BASE } from '@/lib/api';

interface ResultadoRetroalimentacao {
  message: string;
  inserted: number;
  updated: number;
  errors: number;
  total: number;
}

export default function FeedbackUploader({ session }: { session: any }) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoRetroalimentacao | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const enviarRetroalimentacao = async () => {
    if (!arquivo || !session) return;

    setEnviando(true);
    setErro(null);
    setResultado(null);

    try {
      const formData = new FormData();
      formData.append('file', arquivo);

      const resposta = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        body: formData,
        headers: { Authorization: `Bearer ${session.access_token}` }
      });

      if (!resposta.ok) {
        const dadosErro = await resposta.json().catch(() => null);
        throw new Error(
          dadosErro?.detail || `Erro ${resposta.status}: ${resposta.statusText}`
        );
      }

      const dados: ResultadoRetroalimentacao = await resposta.json();
      setResultado(dados);
      setArquivo(null);
    } catch (err) {
      setErro(
        err instanceof Error
          ? err.message
          : 'Erro ao enviar retroalimentação. Tente novamente.'
      );
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div>
      {!resultado ? (
        <>
          <FileUploader
            id="feedback-file-input"
            onFileSelect={setArquivo}
            selectedFile={arquivo}
            onClear={() => {
              setArquivo(null);
              setErro(null);
            }}
            disabled={enviando}
          />

          <button
            id="feedback-submit-btn"
            className="btn btn-success btn-full"
            onClick={enviarRetroalimentacao}
            disabled={!arquivo || enviando}
          >
            {enviando ? (
              <>⏳ Processando retroalimentação...</>
            ) : (
              <>🔄 Enviar Retroalimentação</>
            )}
          </button>
        </>
      ) : (
        <div className="feedback-result">
          <div className="feedback-result-icon">✅</div>
          <h4 className="feedback-result-title">{resultado.message}</h4>
          <p className="feedback-result-detail">
            {resultado.total} linhas processadas • {resultado.inserted} inseridas •{' '}
            {resultado.updated} atualizadas
            {resultado.errors > 0 && ` • ${resultado.errors} erros`}
          </p>

          <div className="metrics-grid" style={{ marginTop: '1rem' }}>
            <div className="metric-card">
              <div className="metric-value total">{resultado.total}</div>
              <div className="metric-label">Total</div>
            </div>
            <div className="metric-card">
              <div className="metric-value approved">{resultado.inserted}</div>
              <div className="metric-label">Inseridas</div>
            </div>
            <div className="metric-card">
              <div className="metric-value pending">{resultado.updated}</div>
              <div className="metric-label">Atualizadas</div>
            </div>
          </div>

          <button
            className="btn btn-primary btn-full"
            onClick={() => {
              setResultado(null);
              setArquivo(null);
            }}
            style={{ marginTop: '1.5rem' }}
          >
            📄 Enviar nova retroalimentação
          </button>
        </div>
      )}

      {erro && (
        <div className="error-banner">
          <span className="error-banner-icon">⚠️</span>
          <span>{erro}</span>
        </div>
      )}
    </div>
  );
}
