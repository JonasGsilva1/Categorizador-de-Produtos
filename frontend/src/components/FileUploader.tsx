'use client';

import React, { useState, useRef, useCallback } from 'react';

interface PropsCarregadorArquivo {
  id: string;
  onFileSelect: (arquivo: File) => void;
  selectedFile: File | null;
  onClear: () => void;
  disabled?: boolean;
}

export default function FileUploader({
  id,
  onFileSelect,
  selectedFile,
  onClear,
  disabled = false,
}: PropsCarregadorArquivo) {
  const [arrastando, setArrastando] = useState(false);
  const refInput = useRef<HTMLInputElement>(null);

  const aoArrastarSobre = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (!disabled) setArrastando(true);
    },
    [disabled]
  );

  const aoSairArraste = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setArrastando(false);
  }, []);

  const aoSoltar = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setArrastando(false);
      if (disabled) return;

      const arquivo = e.dataTransfer.files[0];
      if (arquivo && arquivo.name.endsWith('.xlsx')) {
        onFileSelect(arquivo);
      }
    },
    [disabled, onFileSelect]
  );

  const aoMudar = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const arquivo = e.target.files?.[0];
      if (arquivo) {
        onFileSelect(arquivo);
      }
    },
    [onFileSelect]
  );

  const formatarTamanho = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div>
      <div
        className={`drop-zone ${arrastando ? 'drag-over' : ''} ${
          selectedFile ? 'has-file' : ''
        }`}
        onDragOver={aoArrastarSobre}
        onDragLeave={aoSairArraste}
        onDrop={aoSoltar}
      >
        <input
          ref={refInput}
          id={id}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={aoMudar}
          disabled={disabled}
        />
        <div className="drop-zone-icon">
          {selectedFile ? '📄' : '📁'}
        </div>
        <p className="drop-zone-text">
          {selectedFile ? (
            <>Arquivo selecionado! Clique para trocar.</>
          ) : (
            <>
              Arraste o arquivo <strong>.xlsx</strong> aqui ou{' '}
              <strong>clique para selecionar</strong>
            </>
          )}
        </p>
        <p className="drop-zone-hint">
          Apenas arquivos Excel (.xlsx) • Máximo 50MB
        </p>
      </div>

      {selectedFile && (
        <div className="file-preview">
          <div className="file-preview-icon">📊</div>
          <div className="file-preview-info">
            <div className="file-preview-name">{selectedFile.name}</div>
            <div className="file-preview-size">
              {formatarTamanho(selectedFile.size)}
            </div>
          </div>
          <button
            className="file-preview-remove"
            onClick={(e) => {
              e.stopPropagation();
              onClear();
              if (refInput.current) refInput.current.value = '';
            }}
            disabled={disabled}
            title="Remover arquivo"
            type="button"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
