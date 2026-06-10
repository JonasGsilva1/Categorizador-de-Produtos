'use client';

import React, { useState } from 'react';
import FileUploader from './FileUploader';

interface FeedbackResult {
  message: string;
  inserted: number;
  updated: number;
  errors: number;
  total: number;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function FeedbackUploader({ session }: { session: any }) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<FeedbackResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!file || !session) return;

    setIsUploading(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_URL}/api/feedback`, {
        method: 'POST',
        body: formData,
        headers: { Authorization: `Bearer ${session.access_token}` }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || `Erro ${response.status}: ${response.statusText}`
        );
      }

      const data: FeedbackResult = await response.json();
      setResult(data);
      setFile(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Erro ao enviar retroalimentação. Tente novamente.'
      );
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div>
      {!result ? (
        <>
          <FileUploader
            id="feedback-file-input"
            onFileSelect={setFile}
            selectedFile={file}
            onClear={() => {
              setFile(null);
              setError(null);
            }}
            disabled={isUploading}
          />

          <button
            id="feedback-submit-btn"
            className="btn btn-success btn-full"
            onClick={handleSubmit}
            disabled={!file || isUploading}
          >
            {isUploading ? (
              <>⏳ Processando retroalimentação...</>
            ) : (
              <>🔄 Enviar Retroalimentação</>
            )}
          </button>
        </>
      ) : (
        <div className="feedback-result">
          <div className="feedback-result-icon">✅</div>
          <h4 className="feedback-result-title">{result.message}</h4>
          <p className="feedback-result-detail">
            {result.total} linhas processadas • {result.inserted} inseridas •{' '}
            {result.updated} atualizadas
            {result.errors > 0 && ` • ${result.errors} erros`}
          </p>

          <div className="metrics-grid" style={{ marginTop: '1rem' }}>
            <div className="metric-card">
              <div className="metric-value total">{result.total}</div>
              <div className="metric-label">Total</div>
            </div>
            <div className="metric-card">
              <div className="metric-value approved">{result.inserted}</div>
              <div className="metric-label">Inseridas</div>
            </div>
            <div className="metric-card">
              <div className="metric-value pending">{result.updated}</div>
              <div className="metric-label">Atualizadas</div>
            </div>
          </div>

          <button
            className="btn btn-primary btn-full"
            onClick={() => {
              setResult(null);
              setFile(null);
            }}
            style={{ marginTop: '1.5rem' }}
          >
            📄 Enviar nova retroalimentação
          </button>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <span className="error-banner-icon">⚠️</span>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
