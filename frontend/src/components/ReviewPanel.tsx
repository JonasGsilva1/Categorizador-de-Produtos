'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { API_BASE } from '@/lib/api';

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export interface ResultItem {
  row_index: number;
  descricao: string;
  ean: string;
  ncm: string;
  grupo: string;
  subgrupo: string;
  origem: string;
  status: string;
}

interface ReviewPanelProps {
  jobId: string;
  session: any;
  onFinalized: () => void;
  onBack: () => void;
}

// ---------------------------------------------------------------------------
// Taxonomia — mesma do backend
// ---------------------------------------------------------------------------

const TAXONOMY: Record<string, string[]> = {
  'Bazar e Utilidades':        ['Utensílios de Cozinha','Recipientes de Plástico','Vidros e Taças','Panelas','Garrafas Térmicas','Talheres'],
  'Móveis':                    ['Cadeiras e Poltronas','Mesas','Colchões e Camas','Armários e Roupeiros','Estantes e Racks'],
  'Decoração':                 ['Espelhos','Relógios de Parede','Vasos','Quadros'],
  'Lazer e Camping':           ['Piscinas e Acessórios','Caixas Térmicas','Barracas','Cadeiras de Praia'],
  'Ferramentas e Ferragens':   ['Elétricas','Manuais','Medição','Ferragens e Cadeados'],
  'Materiais de Construção':   ['Pintura','Hidráulica','Elétrica'],
  'Eletro e Eletrônicos':      ['Eletroportáteis','Cabos e Carregadores','Áudio e Som','Acessórios de Celular','Pilhas e Baterias'],
  'Limpeza':                   ['Utensílios de Limpeza (Vassouras/Rodos)','Produtos Químicos','Lixeiras e Cestos','Organização'],
  'Bebidas':                   ['Vinhos','Cervejas','Refrigerantes','Sucos e Chás','Água','Destilados e Ice','Energéticos'],
  'Alimentos (Mercearia)':     ['Biscoitos e Salgadinhos','Doces e Sobremesas','Conservas e Molhos','Grãos e Massas','Óleos e Temperos','Pipoca'],
  'Frios e Congelados':        ['Carnes e Aves','Sorvetes e Picolés','Pratos Prontos'],
  'Higiene e Cuidados Pessoais':['Cabelo','Sabonetes','Desodorantes','Higiene Oral','Cosméticos','Absorventes'],
  'Automotivo e Moto':         ['Capacetes','Acessórios Moto','Acessórios Carro'],
  'Brinquedos':                ['Bonecas','Carrinhos e Pistas','Jogos de Tabuleiro','Pelúcias','Praia e Piscina Infantil'],
  'Vestuário e Calçados':      ['Chinelos e Sandálias','Peças Íntimas','Roupas','Capas de Chuva'],
  'Tabacaria':                 ['Cigarros','Isqueiros e Fósforos','Acessórios'],
  'Cama, Mesa e Banho':        ['Toalhas','Tapetes','Cortinas e Varões'],
  'Padaria e Lanchonete':      ['Pães e Salgados','Bolos e Tortas','Refeições Prontas','Lanches Rápidos'],
};

const ALL_GROUPS = Object.keys(TAXONOMY);

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function ReviewPanel({ jobId, session, onFinalized, onBack }: ReviewPanelProps) {
  const [results, setResults]         = useState<ResultItem[]>([]);
  const [loading, setLoading]         = useState(true);
  const [saving, setSaving]           = useState(false);
  const [finalizing, setFinalizing]   = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [filter, setFilter]           = useState<'pendentes' | 'todos'>('pendentes');
  const [search, setSearch]           = useState('');

  // Edições locais: row_index → {grupo, subgrupo}
  const [edits, setEdits] = useState<Record<number, { grupo: string; subgrupo: string }>>({});

  // ---------------------------------------------------------------------------
  // Carregar resultados
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}/results`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) throw new Error(`Erro ${res.status}`);
        const data = await res.json();
        setResults(data.results);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Erro ao carregar resultados.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [jobId, session]);

  // ---------------------------------------------------------------------------
  // Filtro e busca
  // ---------------------------------------------------------------------------
  const displayed = useMemo(() => {
    let list = filter === 'pendentes'
      ? results.filter(r => r.status === 'Pendente de Revisão')
      : results;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(r => r.descricao.toLowerCase().includes(q));
    }
    return list;
  }, [results, filter, search]);

  const pendentesCount  = results.filter(r => r.status === 'Pendente de Revisão').length;
  const aprovadosCount  = results.filter(r => r.status === 'Aprovado').length;
  const editedCount     = Object.keys(edits).length;

  // ---------------------------------------------------------------------------
  // Edição de um item
  // ---------------------------------------------------------------------------
  const handleEdit = (rowIndex: number, field: 'grupo' | 'subgrupo', value: string) => {
    setEdits(prev => {
      const current = prev[rowIndex] ?? {
        grupo:    results.find(r => r.row_index === rowIndex)?.grupo    ?? '',
        subgrupo: results.find(r => r.row_index === rowIndex)?.subgrupo ?? '',
      };
      const updated = { ...current, [field]: value };
      // Se mudou o grupo, resetar subgrupo
      if (field === 'grupo') updated.subgrupo = '';
      return { ...prev, [rowIndex]: updated };
    });
  };

  const getGrupo    = (item: ResultItem) => edits[item.row_index]?.grupo    ?? item.grupo;
  const getSubgrupo = (item: ResultItem) => edits[item.row_index]?.subgrupo ?? item.subgrupo;

  // ---------------------------------------------------------------------------
  // Salvar edições (PATCH)
  // ---------------------------------------------------------------------------
  const handleSave = async () => {
    if (editedCount === 0) return;
    setSaving(true);
    setError(null);
    try {
      const items = Object.entries(edits)
        .filter(([, v]) => v.grupo && v.subgrupo)
        .map(([rowIndex, v]) => ({ row_index: Number(rowIndex), ...v }));

      const res = await fetch(`${API_BASE}/jobs/${jobId}/results`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ items }),
      });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const data = await res.json();

      // Aplicar edições ao estado local
      setResults(prev => prev.map(r => {
        const edit = edits[r.row_index];
        if (!edit || !edit.grupo || !edit.subgrupo) return r;
        return { ...r, grupo: edit.grupo, subgrupo: edit.subgrupo, status: 'Aprovado', origem: 'Revisão Manual' };
      }));
      setEdits({});
      if (data.pendentes_restantes === 0) setFilter('todos');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao salvar.');
    } finally {
      setSaving(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Finalizar (regenerar XLSX)
  // ---------------------------------------------------------------------------
  const handleFinalize = async () => {
    // Salvar quaisquer edições pendentes primeiro
    if (editedCount > 0) await handleSave();
    setFinalizing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/jobs/${jobId}/finalize`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      onFinalized();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao finalizar.');
    } finally {
      setFinalizing(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  if (loading) return (
    <div style={{ textAlign: 'center', padding: '3rem', color: '#a0a0c0' }}>
      <div className="processing-spinner" style={{ margin: '0 auto 1rem' }} />
      <p>Carregando resultados...</p>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

      {/* Header de métricas */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: '0.75rem' }}>
        {[
          { label: 'Total',    value: results.length,  cls: 'total'    },
          { label: 'Aprovados', value: aprovadosCount, cls: 'approved' },
          { label: 'Pendentes', value: pendentesCount, cls: 'pending'  },
        ].map(m => (
          <div key={m.label} className="metric-card">
            <div className={`metric-value ${m.cls}`}>{m.value}</div>
            <div className="metric-label">{m.label}</div>
          </div>
        ))}
      </div>

      {/* Controles */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '0.25rem' }}>
          {(['pendentes','todos'] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: '0.35rem 0.75rem', fontSize: '0.78rem', fontWeight: 600,
              border: 'none', borderRadius: '6px', cursor: 'pointer', fontFamily: 'inherit',
              background: filter === f ? 'rgba(167,139,250,0.2)' : 'rgba(255,255,255,0.06)',
              color: filter === f ? '#a78bfa' : '#a0a0c0',
            }}>
              {f === 'pendentes' ? `⚠ Pendentes (${pendentesCount})` : `☰ Todos (${results.length})`}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="Buscar descrição..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: 1, minWidth: '160px', padding: '0.35rem 0.65rem',
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '6px', color: '#e8e8f0', fontSize: '0.78rem', fontFamily: 'inherit',
          }}
        />
      </div>

      {/* Tabela de itens */}
      <div style={{ maxHeight: '420px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
        {displayed.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#6a6a8e', fontSize: '0.85rem' }}>
            {filter === 'pendentes' ? '✅ Nenhum produto pendente!' : 'Nenhum produto encontrado.'}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
            <thead>
              <tr style={{ background: 'rgba(255,255,255,0.04)', position: 'sticky', top: 0 }}>
                {['#','Descrição','Origem','Grupo','Subgrupo'].map(h => (
                  <th key={h} style={{ padding: '0.5rem 0.6rem', textAlign: 'left', color: '#6a6a8e',
                    fontWeight: 600, borderBottom: '1px solid rgba(255,255,255,0.08)', whiteSpace: 'nowrap' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayed.map((item, idx) => {
                const isPending = item.status === 'Pendente de Revisão';
                const isEdited  = !!edits[item.row_index];
                const grupo     = getGrupo(item);
                const subgrupo  = getSubgrupo(item);
                const subgrupos = grupo ? TAXONOMY[grupo] ?? [] : [];
                return (
                  <tr key={item.row_index} style={{
                    background: isEdited ? 'rgba(167,139,250,0.06)' : isPending ? 'rgba(246,211,101,0.04)' : 'transparent',
                    borderBottom: '1px solid rgba(255,255,255,0.05)',
                  }}>
                    <td style={{ padding: '0.45rem 0.6rem', color: '#4a4a6a', whiteSpace: 'nowrap' }}>{item.row_index}</td>
                    <td style={{ padding: '0.45rem 0.6rem', color: isPending ? '#f6d365' : '#d0d0e8', maxWidth: '220px' }}>
                      <span title={item.descricao} style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.descricao}
                      </span>
                    </td>
                    <td style={{ padding: '0.45rem 0.6rem', color: '#6a6a8e', whiteSpace: 'nowrap' }}>
                      <span style={{ fontSize: '0.68rem', padding: '0.1rem 0.35rem', borderRadius: '4px',
                        background: isPending ? 'rgba(246,211,101,0.12)' : 'rgba(255,255,255,0.06)',
                        color: isPending ? '#f6d365' : '#8a8aaa' }}>
                        {item.origem || '—'}
                      </span>
                    </td>
                    <td style={{ padding: '0.3rem 0.4rem', minWidth: '140px' }}>
                      <select value={grupo} onChange={e => handleEdit(item.row_index, 'grupo', e.target.value)}
                        style={selectStyle(!!edits[item.row_index])}>
                        <option value="">— Selecionar —</option>
                        {ALL_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
                      </select>
                    </td>
                    <td style={{ padding: '0.3rem 0.4rem', minWidth: '160px' }}>
                      <select value={subgrupo} onChange={e => handleEdit(item.row_index, 'subgrupo', e.target.value)}
                        disabled={!grupo} style={selectStyle(!!edits[item.row_index])}>
                        <option value="">— Selecionar —</option>
                        {subgrupos.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-banner-icon">⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {/* Ações */}
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
        <button className="btn" onClick={onBack} style={{ background: 'rgba(255,255,255,0.07)', color: '#a0a0c0' }}>
          ← Voltar
        </button>
        {editedCount > 0 && (
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? '⏳ Salvando...' : `💾 Salvar ${editedCount} correção${editedCount > 1 ? 'ões' : ''}`}
          </button>
        )}
        <button
          className="btn btn-success"
          onClick={handleFinalize}
          disabled={finalizing || saving}
          style={{ flex: 1 }}
        >
          {finalizing ? '⏳ Finalizando...' : pendentesCount > 0
            ? `✅ Finalizar com ${pendentesCount} pendente${pendentesCount > 1 ? 's' : ''}`
            : '✅ Finalizar e liberar download'}
        </button>
      </div>

      {pendentesCount > 0 && (
        <p style={{ fontSize: '0.72rem', color: '#6a6a8e', textAlign: 'center', marginTop: '-0.25rem' }}>
          Você pode finalizar com pendentes — eles serão marcados como "Pendente de Revisão" no arquivo.
        </p>
      )}
    </div>
  );
}

function selectStyle(edited: boolean): React.CSSProperties {
  return {
    width: '100%', padding: '0.25rem 0.4rem', fontSize: '0.73rem',
    background: edited ? 'rgba(167,139,250,0.12)' : 'rgba(255,255,255,0.05)',
    border: `1px solid ${edited ? 'rgba(167,139,250,0.4)' : 'rgba(255,255,255,0.1)'}`,
    borderRadius: '5px', color: '#d0d0e8', fontFamily: 'inherit', cursor: 'pointer',
  };
}
