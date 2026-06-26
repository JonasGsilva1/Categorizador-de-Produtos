'use client';

import React from 'react';

interface PropsStatusProcessamento {
  status: string;
  total: number;
  processados: number;
}

export default function ProcessingStatus({ status, total, processados }: PropsStatusProcessamento) {
  const porcentagem = total > 0 ? Math.round((processados / total) * 100) : 0;
  
  return (
    <div className="processing-overlay">
      {status === 'PROCESSING' || status === 'PENDING' ? (
        <div className="processing-spinner" />
      ) : status === 'COMPLETED' ? (
        <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>✅</div>
      ) : (
        <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>❌</div>
      )}
      
      <h3 className="processing-title">
        {status === 'PENDING' && 'Na fila de processamento...'}
        {status === 'PROCESSING' && 'Processando produtos...'}
        {status === 'COMPLETED' && 'Concluído!'}
        {status === 'FAILED' && 'Falha no processamento'}
      </h3>
      
      {total > 0 && (
        <>
          <p className="processing-subtitle" style={{ marginBottom: '1rem' }}>
            {processados} de {total} analisados ({porcentagem}%)
          </p>
          <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
            <div 
              style={{ 
                height: '100%', 
                width: `${porcentagem}%`, 
                background: 'linear-gradient(90deg, #667eea, #764ba2)',
                transition: 'width 0.5s ease-out'
              }} 
            />
          </div>
        </>
      )}

      {status === 'PROCESSING' && (
        <div className="funnel-steps" style={{ marginTop: '2rem' }}>
          <div className="funnel-step active">
            <span className="funnel-step-icon">🤖</span>
            <span>Motor do Gemini trabalhando em segundo plano...</span>
          </div>
        </div>
      )}
    </div>
  );
}
