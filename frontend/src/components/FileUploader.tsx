'use client';

import React, { useState, useRef, useCallback } from 'react';

interface FileUploaderProps {
  id: string;
  onFileSelect: (file: File) => void;
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
}: FileUploaderProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (!disabled) setIsDragOver(true);
    },
    [disabled]
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      if (disabled) return;

      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith('.xlsx')) {
        onFileSelect(file);
      }
    },
    [disabled, onFileSelect]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        onFileSelect(file);
      }
    },
    [onFileSelect]
  );

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div>
      <div
        className={`drop-zone ${isDragOver ? 'drag-over' : ''} ${
          selectedFile ? 'has-file' : ''
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          id={id}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={handleChange}
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
              {formatSize(selectedFile.size)}
            </div>
          </div>
          <button
            className="file-preview-remove"
            onClick={(e) => {
              e.stopPropagation();
              onClear();
              if (inputRef.current) inputRef.current.value = '';
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
