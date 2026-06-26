'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { API_BASE } from '@/lib/api';

// ─────────────────────────────────────────────────────────────────────────────
// Tipos de dados
// ─────────────────────────────────────────────────────────────────────────────

export interface ItemResultado {
  row_index: number;
  descricao: string;
  ean: string;
  ncm: string;
  grupo: string;
  subgrupo: string;
  origem: string;
  status: string;
}

interface PropsPainelRevisao {
  jobId: string;
  session: any;
  aoFinalizar: () => void;
  aoVoltar: () => void;
}

interface EdicaoItem {
  grupo: string;
  subgrupo: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Taxonomia de grupos e subgrupos pré-definidos
// ─────────────────────────────────────────────────────────────────────────────

const TAXONOMIA: Record<string, string[]> = {
  'Bazar e Utilidades':         ['Utensílios de Cozinha','Recipientes de Plástico','Vidros e Taças','Panelas','Garrafas Térmicas','Talheres'],
  'Móveis':                     ['Cadeiras e Poltronas','Mesas','Colchões e Camas','Armários e Roupeiros','Estantes e Racks'],
  'Decoração':                  ['Espelhos','Relógios de Parede','Vasos','Quadros'],
  'Lazer e Camping':            ['Piscinas e Acessórios','Caixas Térmicas','Barracas','Cadeiras de Praia'],
  'Ferramentas e Ferragens':    ['Elétricas','Manuais','Medição','Ferragens e Cadeados'],
  'Materiais de Construção':    ['Pintura','Hidráulica','Elétrica'],
  'Eletro e Eletrônicos':       ['Eletroportáteis','Cabos e Carregadores','Áudio e Som','Acessórios de Celular','Pilhas e Baterias'],
  'Limpeza':                    ['Utensílios de Limpeza (Vassouras/Rodos)','Produtos Químicos','Lixeiras e Cestos','Organização'],
  'Bebidas':                    ['Vinhos','Cervejas','Refrigerantes','Sucos e Chás','Água','Destilados e Ice','Energéticos'],
  'Alimentos (Mercearia)':      ['Biscoitos e Salgadinhos','Doces e Sobremesas','Conservas e Molhos','Grãos e Massas','Óleos e Temperos','Pipoca'],
  'Frios e Congelados':         ['Carnes e Aves','Sorvetes e Picolés','Pratos Prontos'],
  'Higiene e Cuidados Pessoais':['Cabelo','Sabonetes','Desodorantes','Higiene Oral','Cosméticos','Absorventes'],
  'Automotivo e Moto':          ['Capacetes','Acessórios Moto','Acessórios Carro'],
  'Brinquedos':                 ['Bonecas','Carrinhos e Pistas','Jogos de Tabuleiro','Pelúcias','Praia e Piscina Infantil'],
  'Vestuário e Calçados':       ['Chinelos e Sandálias','Peças Íntimas','Roupas','Capas de Chuva'],
  'Tabacaria':                  ['Cigarros','Isqueiros e Fósforos','Acessórios'],
  'Cama, Mesa e Banho':         ['Toalhas','Tapetes','Cortinas e Varões'],
  'Padaria e Lanchonete':       ['Pães e Salgados','Bolos e Tortas','Refeições Prontas','Lanches Rápidos'],
};

const OPCAO_PERSONALIZADO = '__personalizado__';

// ─────────────────────────────────────────────────────────────────────────────
// Componente principal de revisão
// ─────────────────────────────────────────────────────────────────────────────

export default function ReviewPanel({ jobId, session, aoFinalizar, aoVoltar }: PropsPainelRevisao) {

  // ── Estado dos resultados vindos do backend ──────────────────────────────
  const [resultados, setResultados]     = useState<ItemResultado[]>([]);
  const [carregando, setCarregando]     = useState(true);
  const [salvando, setSalvando]         = useState(false);
  const [finalizando, setFinalizando]   = useState(false);
  const [erro, setErro]                 = useState<string | null>(null);

  // ── Filtro e busca da tabela ─────────────────────────────────────────────
  const [filtro, setFiltro]   = useState<'pendentes' | 'todos'>('pendentes');
  const [busca, setBusca]     = useState('');

  // ── Edições individuais: row_index → {grupo, subgrupo} ──────────────────
  const [edicoes, setEdicoes] = useState<Record<number, EdicaoItem>>({});

  // ── Seleção múltipla para alteração em massa ─────────────────────────────
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());

  // ── Painel de alteração em massa ─────────────────────────────────────────
  const [grupoPainelMassa, setGrupoPainelMassa] = useState('');
  const [subgrupoPainelMassa, setSubgrupoPainelMassa] = useState('');
  const [grupoPersonalizadoMassa, setGrupoPersonalizadoMassa]       = useState('');
  const [subgrupoPersonalizadoMassa, setSubgrupoPersonalizadoMassa] = useState('');

  // ── Grupos personalizados criados pelo usuário nesta sessão ─────────────
  const [gruposPersonalizados, setGruposPersonalizados] = useState<Record<string, string[]>>({});

  // Taxonomia completa = pré-definida + personalizados criados na sessão
  const taxonomiaCompleta = useMemo<Record<string, string[]>>(() => ({
    ...TAXONOMIA,
    ...gruposPersonalizados,
  }), [gruposPersonalizados]);

  const todosOsGrupos = useMemo(() => Object.keys(taxonomiaCompleta), [taxonomiaCompleta]);

  // Carregar resultados do backend
  useEffect(() => {
    const carregarResultados = async () => {
      setCarregando(true);
      setErro(null);
      try {
        const resposta = await fetch(`${API_BASE}/jobs/${jobId}/results`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!resposta.ok) throw new Error(`Erro HTTP ${resposta.status}`);
        const dados = await resposta.json();
        setResultados(dados.results);
      } catch (e) {
        setErro(e instanceof Error ? e.message : 'Erro ao carregar resultados.');
      } finally {
        setCarregando(false);
      }
    };
    carregarResultados();
  }, [jobId, session]);

  // Itens filtrados
  const itensFiltrados = useMemo(() => {
    let lista = filtro === 'pendentes'
      ? resultados.filter(r => r.status === 'Pendente de Revisão')
      : resultados;

    if (busca.trim()) {
      const termoBusca = busca.toLowerCase();
      lista = lista.filter(r => r.descricao.toLowerCase().includes(termoBusca));
    }
    return lista;
  }, [resultados, filtro, busca]);

  const totalPendentes  = resultados.filter(r => r.status === 'Pendente de Revisão').length;
  const totalAprovados  = resultados.filter(r => r.status === 'Aprovado').length;

  const obterGrupo = (item: ItemResultado) => edicoes[item.row_index]?.grupo ?? item.grupo;
  const obterSubgrupo = (item: ItemResultado) => edicoes[item.row_index]?.subgrupo ?? item.subgrupo;

  const editarCampo = useCallback((rowIndex: number, campo: 'grupo' | 'subgrupo', valor: string) => {
    setEdicoes(anterior => {
      const atual = anterior[rowIndex] ?? {
        grupo:    resultados.find(r => r.row_index === rowIndex)?.grupo    ?? '',
        subgrupo: resultados.find(r => r.row_index === rowIndex)?.subgrupo ?? '',
      };
      const atualizado = { ...atual, [campo]: valor };
      if (campo === 'grupo') atualizado.subgrupo = ''; // reseta subgrupo ao trocar grupo
      return { ...anterior, [rowIndex]: atualizado };
    });
  }, [resultados]);

  const criarGrupoPersonalizado = useCallback((nomeGrupo: string, nomeSubgrupo: string): boolean => {
    const grupoLimpo    = nomeGrupo.trim();
    const subgrupoLimpo = nomeSubgrupo.trim();
    if (!grupoLimpo || !subgrupoLimpo) return false;

    setGruposPersonalizados(anterior => {
      const subgruposExistentes = anterior[grupoLimpo] ?? [];
      if (subgruposExistentes.includes(subgrupoLimpo)) return anterior;
      return { ...anterior, [grupoLimpo]: [...subgruposExistentes, subgrupoLimpo] };
    });
    return true;
  }, []);

  const alternarSelecaoTodos = useCallback(() => {
    const indicesVisiveis = itensFiltrados.map(i => i.row_index);
    const todosSelecionados = indicesVisiveis.length > 0 && indicesVisiveis.every(idx => selecionados.has(idx));

    setSelecionados(anterior => {
      const nova = new Set(anterior);
      if (todosSelecionados) {
        indicesVisiveis.forEach(idx => nova.delete(idx));
      } else {
        indicesVisiveis.forEach(idx => nova.add(idx));
      }
      return nova;
    });
  }, [itensFiltrados, selecionados]);

  const alternarSelecaoItem = useCallback((rowIndex: number) => {
    setSelecionados(anterior => {
      const nova = new Set(anterior);
      if (nova.has(rowIndex)) nova.delete(rowIndex);
      else nova.add(rowIndex);
      return nova;
    });
  }, []);

  // ── Funções de salvar e finalizar ────────────────────────────────────────

  const salvarAlteracoes = async (ehFinalizacao = false) => {
    try {
      const itemsPayload = Object.entries(edicoes).map(([row_index, edicao]) => ({
        row_index: parseInt(row_index),
        grupo: edicao.grupo,
        subgrupo: edicao.subgrupo,
      }));

      if (itemsPayload.length === 0 && !ehFinalizacao) {
        alert('Nenhuma alteração pendente para salvar.');
        return;
      }

      if (itemsPayload.length > 0) {
        setSalvando(true);
        const res = await fetch(`${API_BASE}/jobs/${jobId}/results`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({ items: itemsPayload }),
        });
        if (!res.ok) throw new Error('Falha ao salvar edições no servidor.');

        setResultados(anteriores => anteriores.map(item => {
          if (edicoes[item.row_index]) {
            return {
              ...item,
              grupo: edicoes[item.row_index].grupo,
              subgrupo: edicoes[item.row_index].subgrupo,
              status: 'Aprovado',
            };
          }
          return item;
        }));
        setEdicoes({});
        setSelecionados(new Set());
      }

      if (ehFinalizacao) {
        setFinalizando(true);
        const resFinalize = await fetch(`${API_BASE}/jobs/${jobId}/finalize`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!resFinalize.ok) throw new Error('Falha ao finalizar o job.');
        aoFinalizar();
      } else {
        alert('Progresso salvo com sucesso!');
      }
    } catch (err: any) {
      setErro(err.message || 'Ocorreu um erro.');
    } finally {
      setSalvando(false);
      setFinalizando(false);
    }
  };

  const aplicarEdicaoEmMassa = () => {
    let grupoFinal = grupoPainelMassa;
    let subgrupoFinal = subgrupoPainelMassa;

    if (grupoFinal === OPCAO_PERSONALIZADO) {
      if (!grupoPersonalizadoMassa.trim() || !subgrupoPersonalizadoMassa.trim()) {
        alert('Por favor, preencha os nomes do grupo e subgrupo personalizados.');
        return;
      }
      grupoFinal = grupoPersonalizadoMassa.trim();
      subgrupoFinal = subgrupoPersonalizadoMassa.trim();
      criarGrupoPersonalizado(grupoFinal, subgrupoFinal);
    } else if (subgrupoFinal === OPCAO_PERSONALIZADO) {
      if (!subgrupoPersonalizadoMassa.trim()) {
        alert('Por favor, preencha o nome do subgrupo personalizado.');
        return;
      }
      subgrupoFinal = subgrupoPersonalizadoMassa.trim();
      criarGrupoPersonalizado(grupoFinal, subgrupoFinal);
    }

    if (!grupoFinal || !subgrupoFinal) {
      alert('Selecione um grupo e um subgrupo para aplicar a alteração em massa.');
      return;
    }

    setEdicoes(anteriores => {
      const novasEdicoes = { ...anteriores };
      selecionados.forEach(rowIndex => {
        novasEdicoes[rowIndex] = { grupo: grupoFinal, subgrupo: subgrupoFinal };
      });
      return novasEdicoes;
    });

    // Limpar painel de massa após aplicar
    setGrupoPainelMassa('');
    setSubgrupoPainelMassa('');
    setGrupoPersonalizadoMassa('');
    setSubgrupoPersonalizadoMassa('');
    alert(`${selecionados.size} itens foram alterados localmente. Lembre-se de salvar!`);
  };

  if (carregando) {
    return (
      <div style={{ color: 'white', padding: '2rem', textAlign: 'center' }}>
        <h2>Carregando resultados da revisão...</h2>
      </div>
    );
  }

  // ── Renderização da Interface Premium ────────────────────────────────────

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', color: 'white', width: '100%' }}>
      
      {/* Cabeçalho de Métricas e Controles */}
      <div style={{ 
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '15px',
        background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--bg-glass)'
      }}>
        <div style={{ display: 'flex', gap: '20px' }}>
          <div>
            <span style={{ fontSize: '0.85rem', color: '#aaa' }}>Pendentes</span>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#ff9800' }}>{totalPendentes}</div>
          </div>
          <div>
            <span style={{ fontSize: '0.85rem', color: '#aaa' }}>Aprovados</span>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#4caf50' }}>{totalAprovados}</div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
          <input 
            type="text" 
            placeholder="Buscar por descrição..." 
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            style={{ 
              padding: '10px 15px', borderRadius: '8px', border: '1px solid var(--bg-glass)', 
              background: 'var(--bg-tertiary)', color: 'white', minWidth: '250px'
            }}
          />
          <select 
            value={filtro} 
            onChange={(e) => setFiltro(e.target.value as any)}
            style={{ 
              padding: '10px 15px', borderRadius: '8px', border: '1px solid var(--bg-glass)', 
              background: 'var(--bg-tertiary)', color: 'white'
            }}
          >
            <option value="pendentes">Mostrar Pendentes</option>
            <option value="todos">Mostrar Todos</option>
          </select>
          <button 
            onClick={aoVoltar}
            style={{ 
              padding: '10px 20px', borderRadius: '8px', border: 'none', cursor: 'pointer',
              background: 'var(--bg-glass)', color: 'white', fontWeight: 'bold'
            }}
          >
            Voltar
          </button>
        </div>
      </div>

      {erro && (
        <div style={{ background: '#f4433622', color: '#f44336', padding: '15px', borderRadius: '8px', border: '1px solid #f44336' }}>
          {erro}
        </div>
      )}

      {/* Painel de Alteração em Massa */}
      {selecionados.size > 0 && (
        <div style={{ 
          background: 'linear-gradient(145deg, rgba(30,60,120,0.4), rgba(20,40,80,0.4))', 
          padding: '20px', borderRadius: '12px', border: '1px solid var(--bg-glass)',
          display: 'flex', flexDirection: 'column', gap: '15px'
        }}>
          <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Alteração em Massa ({selecionados.size} selecionados)</h3>
          
          <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
            {/* Seletor de Grupo para Massa */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ fontSize: '0.85rem', color: '#ccc' }}>Grupo</label>
              <select 
                value={grupoPainelMassa} 
                onChange={(e) => {
                  setGrupoPainelMassa(e.target.value);
                  setSubgrupoPainelMassa('');
                }}
                style={{ padding: '8px', borderRadius: '6px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--bg-glass)', minWidth: '200px' }}
              >
                <option value="">-- Selecione --</option>
                {todosOsGrupos.map(g => <option key={g} value={g}>{g}</option>)}
                <option value={OPCAO_PERSONALIZADO}>+ Criar Personalizado</option>
              </select>
              {grupoPainelMassa === OPCAO_PERSONALIZADO && (
                <input 
                  type="text" placeholder="Nome do novo grupo" value={grupoPersonalizadoMassa}
                  onChange={(e) => setGrupoPersonalizadoMassa(e.target.value)}
                  style={{ marginTop: '5px', padding: '8px', borderRadius: '6px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--bg-glass)' }}
                />
              )}
            </div>

            {/* Seletor de Subgrupo para Massa */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <label style={{ fontSize: '0.85rem', color: '#ccc' }}>Subgrupo</label>
              <select 
                value={subgrupoPainelMassa} 
                onChange={(e) => setSubgrupoPainelMassa(e.target.value)}
                disabled={!grupoPainelMassa}
                style={{ padding: '8px', borderRadius: '6px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--bg-glass)', minWidth: '200px' }}
              >
                <option value="">-- Selecione --</option>
                {grupoPainelMassa && grupoPainelMassa !== OPCAO_PERSONALIZADO && (taxonomiaCompleta[grupoPainelMassa] || []).map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
                {grupoPainelMassa && <option value={OPCAO_PERSONALIZADO}>+ Criar Personalizado</option>}
              </select>
              {(subgrupoPainelMassa === OPCAO_PERSONALIZADO || grupoPainelMassa === OPCAO_PERSONALIZADO) && (
                <input 
                  type="text" placeholder="Nome do novo subgrupo" value={subgrupoPersonalizadoMassa}
                  onChange={(e) => setSubgrupoPersonalizadoMassa(e.target.value)}
                  style={{ marginTop: '5px', padding: '8px', borderRadius: '6px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--bg-glass)' }}
                />
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: '2px' }}>
              <button 
                onClick={aplicarEdicaoEmMassa}
                style={{ 
                  padding: '10px 20px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                  background: '#2196f3', color: 'white', fontWeight: 'bold'
                }}
              >
                Aplicar aos Selecionados
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabela de Resultados */}
      <div style={{ overflowX: 'auto', background: 'var(--bg-card)', borderRadius: '12px', border: '1px solid var(--bg-glass)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--bg-glass)' }}>
              <th style={{ padding: '15px', width: '40px' }}>
                <input 
                  type="checkbox" 
                  checked={itensFiltrados.length > 0 && selecionados.size === itensFiltrados.length}
                  onChange={alternarSelecaoTodos}
                  style={{ cursor: 'pointer', width: '16px', height: '16px' }}
                />
              </th>
              <th style={{ padding: '15px' }}>Descrição Original</th>
              <th style={{ padding: '15px' }}>EAN / NCM</th>
              <th style={{ padding: '15px' }}>Grupo</th>
              <th style={{ padding: '15px' }}>Subgrupo</th>
            </tr>
          </thead>
          <tbody>
            {itensFiltrados.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ padding: '30px', textAlign: 'center', color: '#aaa' }}>
                  Nenhum item encontrado.
                </td>
              </tr>
            ) : (
              itensFiltrados.map(item => {
                const grupoAtual = obterGrupo(item);
                const subgrupoAtual = obterSubgrupo(item);
                const editado = !!edicoes[item.row_index];

                return (
                  <tr key={item.row_index} style={{ 
                    borderBottom: '1px solid var(--bg-glass)', 
                    background: selecionados.has(item.row_index) ? 'rgba(33, 150, 243, 0.1)' : (editado ? 'rgba(76, 175, 80, 0.05)' : 'transparent')
                  }}>
                    <td style={{ padding: '15px' }}>
                      <input 
                        type="checkbox" 
                        checked={selecionados.has(item.row_index)}
                        onChange={() => alternarSelecaoItem(item.row_index)}
                        style={{ cursor: 'pointer', width: '16px', height: '16px' }}
                      />
                    </td>
                    <td style={{ padding: '15px', maxWidth: '300px' }}>
                      <div style={{ fontWeight: '500', marginBottom: '4px' }}>{item.descricao}</div>
                      <div style={{ fontSize: '0.8rem', color: '#888' }}>Origem: {item.origem} | Status: {item.status}</div>
                    </td>
                    <td style={{ padding: '15px', color: '#aaa', fontSize: '0.85rem' }}>
                      EAN: {item.ean || '-'}<br />
                      NCM: {item.ncm || '-'}
                    </td>
                    <td style={{ padding: '15px' }}>
                      <select 
                        value={todosOsGrupos.includes(grupoAtual) ? grupoAtual : ''}
                        onChange={(e) => {
                          const v = e.target.value;
                          if (v === OPCAO_PERSONALIZADO) {
                            const novoG = prompt('Digite o nome do novo Grupo:');
                            if (novoG) {
                              criarGrupoPersonalizado(novoG, 'Geral');
                              editarCampo(item.row_index, 'grupo', novoG);
                              editarCampo(item.row_index, 'subgrupo', 'Geral');
                            }
                          } else {
                            editarCampo(item.row_index, 'grupo', v);
                          }
                        }}
                        style={{ padding: '6px', borderRadius: '4px', background: 'var(--bg-primary)', color: 'white', border: '1px solid #444', width: '100%' }}
                      >
                        <option value="">-- Selecione --</option>
                        {todosOsGrupos.map(g => <option key={g} value={g}>{g}</option>)}
                        {!todosOsGrupos.includes(grupoAtual) && grupoAtual && <option value={grupoAtual}>{grupoAtual}</option>}
                        <option value={OPCAO_PERSONALIZADO}>+ Personalizado</option>
                      </select>
                    </td>
                    <td style={{ padding: '15px' }}>
                      <select 
                        value={(taxonomiaCompleta[grupoAtual] || []).includes(subgrupoAtual) ? subgrupoAtual : ''}
                        onChange={(e) => {
                          const v = e.target.value;
                          if (v === OPCAO_PERSONALIZADO) {
                            const novoS = prompt('Digite o nome do novo Subgrupo:');
                            if (novoS && grupoAtual) {
                              criarGrupoPersonalizado(grupoAtual, novoS);
                              editarCampo(item.row_index, 'subgrupo', novoS);
                            }
                          } else {
                            editarCampo(item.row_index, 'subgrupo', v);
                          }
                        }}
                        disabled={!grupoAtual}
                        style={{ padding: '6px', borderRadius: '4px', background: 'var(--bg-primary)', color: 'white', border: '1px solid #444', width: '100%' }}
                      >
                        <option value="">-- Selecione --</option>
                        {(taxonomiaCompleta[grupoAtual] || []).map(s => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                        {!(taxonomiaCompleta[grupoAtual] || []).includes(subgrupoAtual) && subgrupoAtual && <option value={subgrupoAtual}>{subgrupoAtual}</option>}
                        {grupoAtual && <option value={OPCAO_PERSONALIZADO}>+ Personalizado</option>}
                      </select>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Rodapé: Ações Finais */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '15px', padding: '10px 0' }}>
        <button 
          onClick={() => salvarAlteracoes(false)}
          disabled={salvando || finalizando || Object.keys(edicoes).length === 0}
          style={{ 
            padding: '12px 25px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.2)', cursor: 'pointer',
            background: 'transparent', color: 'white', fontWeight: 'bold',
            opacity: (salvando || finalizando || Object.keys(edicoes).length === 0) ? 0.5 : 1
          }}
        >
          {salvando && !finalizando ? 'Salvando...' : 'Salvar Progresso'}
        </button>
        
        <button 
          onClick={() => salvarAlteracoes(true)}
          disabled={salvando || finalizando || totalPendentes > Object.keys(edicoes).length}
          title={totalPendentes > Object.keys(edicoes).length ? 'Você precisa categorizar todos os itens pendentes antes de finalizar.' : ''}
          style={{ 
            padding: '12px 25px', borderRadius: '8px', border: 'none', cursor: 'pointer',
            background: 'linear-gradient(90deg, #4caf50, #2e7d32)', color: 'white', fontWeight: 'bold',
            opacity: (salvando || finalizando || totalPendentes > Object.keys(edicoes).length) ? 0.5 : 1
          }}
        >
          {finalizando ? 'Finalizando...' : 'Finalizar Revisão'}
        </button>
      </div>

    </div>
  );
}
