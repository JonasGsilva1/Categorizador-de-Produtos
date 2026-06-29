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
  viaIA?: boolean;
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

const OPCOES_POR_PAGINA = [25, 50, 100];

// ─────────────────────────────────────────────────────────────────────────────
// Motor de sugestões por similaridade de palavras
// ─────────────────────────────────────────────────────────────────────────────

const STOPWORDS = new Set([
  'de','do','da','dos','das','em','no','na','nos','nas','um','uma','uns','umas',
  'o','a','os','as','e','ou','com','para','por','que','se','ao','à','pelo','pela',
  'mais','menos','muito','pouco','bem','mal','já','ainda','aqui','ali','lá',
  'este','esta','esse','essa','isso','isto','aquilo','meu','minha','seu','sua',
  'ele','ela','nós','eles','elas','todo','toda','todos','todas','cada','outro',
  'outra','outros','outras','mesmo','mesma','qual','quais','como','quando',
  'onde','porque','pois','mas','porém','entre','sobre','sob','até','após',
  'ante','contra','desde','sem','tipo','kit','pct','cx','un','und','pc','pç',
  'c','p','s','x','ml','lt','gr','kg','cm','mm','mt','und','unid','pacote',
]);

function tokenizar(texto: string): Set<string> {
  const tokens = new Set<string>();
  const palavras = texto
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // remove acentos
    .replace(/[^a-z0-9\s]/g, ' ')   // remove pontuação
    .split(/\s+/);
  
  palavras.forEach(p => {
    if (p.length >= 2 && !STOPWORDS.has(p)) {
      tokens.add(p);
    }
  });
  return tokens;
}

function calcularSimilaridade(tokensA: Set<string>, tokensB: Set<string>): number {
  if (tokensA.size === 0 || tokensB.size === 0) return 0;
  let intersecao = 0;
  Array.from(tokensA).forEach(t => {
    if (tokensB.has(t)) intersecao++;
  });
  const uniao = tokensA.size + tokensB.size - intersecao;
  return uniao > 0 ? intersecao / uniao : 0;
}

interface Sugestao {
  grupo: string;
  subgrupo: string;
  similaridade: number;
  descricaoRef: string;
}

const SIMILARIDADE_MINIMA = 0.25;

// ─────────────────────────────────────────────────────────────────────────────
// Componente principal de revisão
// ─────────────────────────────────────────────────────────────────────────────

export default function ReviewPanel({ jobId, session, aoFinalizar, aoVoltar }: PropsPainelRevisao) {

  // ── Estado dos resultados vindos do backend ──────────────────────────────
  const [resultados, setResultados]     = useState<ItemResultado[]>([]);
  const [carregando, setCarregando]     = useState(true);
  const [salvando, setSalvando]         = useState(false);
  const [finalizando, setFinalizando]   = useState(false);
  const [isAiLoading, setIsAiLoading]   = useState(false);
  const [erro, setErro]                 = useState<string | null>(null);

  // ── Filtro e busca da tabela ─────────────────────────────────────────────
  const [filtro, setFiltro]   = useState<'pendentes' | 'todos'>('pendentes');
  const [busca, setBusca]     = useState('');

  // ── Paginação ───────────────────────────────────────────────────────────
  const [paginaAtual, setPaginaAtual]       = useState(1);
  const [itensPorPagina, setItensPorPagina] = useState(25);

  // ── Edições individuais: row_index → {grupo, subgrupo} ──────────────────
  const [edicoes, setEdicoes] = useState<Record<number, EdicaoItem>>({});

  // ── Seleção múltipla para alteração em massa ─────────────────────────────
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());

  // ── Painel de alteração em massa ─────────────────────────────────────────
  const [grupoPainelMassa, setGrupoPainelMassa] = useState('');
  const [subgrupoPainelMassa, setSubgrupoPainelMassa] = useState('');
  const [grupoPersonalizadoMassa, setGrupoPersonalizadoMassa]       = useState('');
  const [subgrupoPersonalizadoMassa, setSubgrupoPersonalizadoMassa] = useState('');

  // ── Grupos personalizados persistidos no localStorage ──────────────────
  const [gruposPersonalizados, setGruposPersonalizados] = useState<Record<string, string[]>>(() => {
    if (typeof window === 'undefined') return {};
    try {
      const salvo = localStorage.getItem('categorizador-grupos-personalizados');
      return salvo ? JSON.parse(salvo) : {};
    } catch {
      return {};
    }
  });

  // ── Renomeações de grupos/subgrupos persistidas ───────────────────────
  const [renomeacoes, setRenomeacoes] = useState<{
    grupos: Record<string, string>;
    subgrupos: Record<string, Record<string, string>>;
  }>(() => {
    if (typeof window === 'undefined') return { grupos: {}, subgrupos: {} };
    try {
      const salvo = localStorage.getItem('categorizador-renomeacoes');
      return salvo ? JSON.parse(salvo) : { grupos: {}, subgrupos: {} };
    } catch {
      return { grupos: {}, subgrupos: {} };
    }
  });

  // ── Editor de taxonomia ───────────────────────────────────────────────
  const [mostrarEditor, setMostrarEditor] = useState(false);

  // Persistir dados no localStorage
  useEffect(() => {
    try {
      localStorage.setItem('categorizador-grupos-personalizados', JSON.stringify(gruposPersonalizados));
    } catch { /* ignore */ }
  }, [gruposPersonalizados]);

  useEffect(() => {
    try {
      localStorage.setItem('categorizador-renomeacoes', JSON.stringify(renomeacoes));
    } catch { /* ignore */ }
  }, [renomeacoes]);

  // Taxonomia completa = pré-definida + personalizados + renomeações aplicadas
  const taxonomiaCompleta = useMemo<Record<string, string[]>>(() => {
    // 1. Merge pré-definidos + personalizados
    const base: Record<string, string[]> = { ...TAXONOMIA };
    Object.entries(gruposPersonalizados).forEach(([grupo, subgrupos]) => {
      const existentes = base[grupo] ?? [];
      const combinados = [...existentes];
      subgrupos.forEach(s => {
        if (!combinados.includes(s)) combinados.push(s);
      });
      base[grupo] = combinados;
    });

    // 2. Aplicar renomeações de subgrupos
    const comSubRenomeados: Record<string, string[]> = {};
    Object.entries(base).forEach(([grupo, subs]) => {
      const mapaSub = renomeacoes.subgrupos[grupo] ?? {};
      comSubRenomeados[grupo] = subs.map(s => mapaSub[s] ?? s);
    });

    // 3. Aplicar renomeações de grupos
    const final: Record<string, string[]> = {};
    Object.entries(comSubRenomeados).forEach(([grupo, subs]) => {
      const novoNome = renomeacoes.grupos[grupo] ?? grupo;
      if (final[novoNome]) {
        // Merge se o novo nome já existe
        subs.forEach(s => {
          if (!final[novoNome].includes(s)) final[novoNome].push(s);
        });
      } else {
        final[novoNome] = subs;
      }
    });

    return final;
  }, [gruposPersonalizados, renomeacoes]);

  const todosOsGrupos = useMemo(() => Object.keys(taxonomiaCompleta), [taxonomiaCompleta]);

  // ── Funções de renomear ──────────────────────────────────────────────
  const renomearGrupo = useCallback((nomeAtual: string) => {
    const novoNome = prompt(`Renomear grupo "${nomeAtual}" para:`, nomeAtual);
    if (!novoNome || novoNome.trim() === '' || novoNome.trim() === nomeAtual) return;
    const limpo = novoNome.trim();

    // Encontrar o nome original (pode já ter sido renomeado antes)
    let nomeOriginal = nomeAtual;
    Object.entries(renomeacoes.grupos).forEach(([orig, ren]) => {
      if (ren === nomeAtual) nomeOriginal = orig;
    });

    setRenomeacoes(ant => ({
      ...ant,
      grupos: { ...ant.grupos, [nomeOriginal]: limpo },
    }));

    // Atualizar edições existentes que usam o nome antigo
    setEdicoes(ant => {
      const novas: Record<number, EdicaoItem> = {};
      Object.entries(ant).forEach(([idx, ed]) => {
        novas[parseInt(idx)] = {
          grupo: ed.grupo === nomeAtual ? limpo : ed.grupo,
          subgrupo: ed.subgrupo,
        };
      });
      return novas;
    });
  }, [renomeacoes]);

  const renomearSubgrupo = useCallback((nomeGrupo: string, subAtual: string) => {
    const novoNome = prompt(`Renomear subgrupo "${subAtual}" para:`, subAtual);
    if (!novoNome || novoNome.trim() === '' || novoNome.trim() === subAtual) return;
    const limpo = novoNome.trim();

    // Encontrar grupo original
    let grupoOriginal = nomeGrupo;
    Object.entries(renomeacoes.grupos).forEach(([orig, ren]) => {
      if (ren === nomeGrupo) grupoOriginal = orig;
    });

    // Encontrar subgrupo original
    let subOriginal = subAtual;
    const mapaSub = renomeacoes.subgrupos[grupoOriginal] ?? {};
    Object.entries(mapaSub).forEach(([orig, ren]) => {
      if (ren === subAtual) subOriginal = orig;
    });

    setRenomeacoes(ant => ({
      ...ant,
      subgrupos: {
        ...ant.subgrupos,
        [grupoOriginal]: {
          ...(ant.subgrupos[grupoOriginal] ?? {}),
          [subOriginal]: limpo,
        },
      },
    }));

    // Atualizar edições existentes
    setEdicoes(ant => {
      const novas: Record<number, EdicaoItem> = {};
      Object.entries(ant).forEach(([idx, ed]) => {
        novas[parseInt(idx)] = {
          grupo: ed.grupo,
          subgrupo: (ed.grupo === nomeGrupo && ed.subgrupo === subAtual) ? limpo : ed.subgrupo,
        };
      });
      return novas;
    });
  }, [renomeacoes]);

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

  // Itens filtrados (sem paginação)
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

  // ── Paginação calculada ──────────────────────────────────────────────────
  const totalPaginas = Math.max(1, Math.ceil(itensFiltrados.length / itensPorPagina));

  // Reseta para página 1 quando filtro/busca/itensPorPagina mudam
  useEffect(() => {
    setPaginaAtual(1);
  }, [filtro, busca, itensPorPagina]);

  // Itens da página atual
  const itensPaginados = useMemo(() => {
    const inicio = (paginaAtual - 1) * itensPorPagina;
    const fim = inicio + itensPorPagina;
    return itensFiltrados.slice(inicio, fim);
  }, [itensFiltrados, paginaAtual, itensPorPagina]);

  const totalPendentes  = resultados.filter(r => r.status === 'Pendente de Revisão').length;
  const totalAprovados  = resultados.filter(r => r.status === 'Aprovado').length;

  const obterGrupo = (item: ItemResultado) => edicoes[item.row_index]?.grupo ?? item.grupo;
  const obterSubgrupo = (item: ItemResultado) => edicoes[item.row_index]?.subgrupo ?? item.subgrupo;

  // ── Motor de sugestões ──────────────────────────────────────────────────
  // Pré-computa tokens dos itens aprovados (originais + editados pelo usuário)
  const sugestoes = useMemo<Record<number, Sugestao>>(() => {
    // Itens de referência = aprovados originais + itens com edição do usuário
    const itensReferencia: Array<{ descricao: string; tokens: Set<string>; grupo: string; subgrupo: string }> = [];

    for (const item of resultados) {
      const edicao = edicoes[item.row_index];
      const grupo = edicao?.grupo ?? item.grupo;
      const subgrupo = edicao?.subgrupo ?? item.subgrupo;

      // Se é aprovado OU tem edição com grupo/subgrupo definido, é referência
      const ehReferencia = item.status === 'Aprovado' || (edicao && grupo && subgrupo);
      if (ehReferencia && grupo && subgrupo) {
        itensReferencia.push({
          descricao: item.descricao,
          tokens: tokenizar(item.descricao),
          grupo,
          subgrupo,
        });
      }
    }

    if (itensReferencia.length === 0) return {};

    const mapa: Record<number, Sugestao> = {};

    for (const item of resultados) {
      // Só sugerir para pendentes que ainda não foram editados
      if (item.status !== 'Pendente de Revisão') continue;
      if (edicoes[item.row_index]) continue;

      const tokensPendente = tokenizar(item.descricao);
      let melhorSim = 0;
      let melhorRef: typeof itensReferencia[0] | null = null;

      for (const ref of itensReferencia) {
        const sim = calcularSimilaridade(tokensPendente, ref.tokens);
        if (sim > melhorSim) {
          melhorSim = sim;
          melhorRef = ref;
        }
      }

      if (melhorRef && melhorSim >= SIMILARIDADE_MINIMA) {
        mapa[item.row_index] = {
          grupo: melhorRef.grupo,
          subgrupo: melhorRef.subgrupo,
          similaridade: melhorSim,
          descricaoRef: melhorRef.descricao,
        };
      }
    }

    return mapa;
  }, [resultados, edicoes]);

  const aplicarSugestao = useCallback((rowIndex: number) => {
    const sug = sugestoes[rowIndex];
    if (!sug) return;
    setEdicoes(anterior => ({
      ...anterior,
      [rowIndex]: { grupo: sug.grupo, subgrupo: sug.subgrupo },
    }));
  }, [sugestoes]);

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
    const indicesVisiveis = itensPaginados.map(i => i.row_index);
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
  }, [itensPaginados, selecionados]);

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

  // ── Estado de progresso da IA ─────────────────────────────────────────────
  const [aiProgress, setAiProgress] = useState<{
    sublote: number;
    totalSublotes: number;
    totalAcumulado: number;
    totalItens: number;
  } | null>(null);

  const categorizarComIA = async () => {
    let itensParaProcessar = resultados.filter(
      r => r.status === 'Pendente de Revisão' && !edicoes[r.row_index]
    );

    if (itensParaProcessar.length === 0) {
      alert('Não há itens pendentes para classificar (ou todos já estão editados).');
      return;
    }

    setIsAiLoading(true);
    setAiProgress(null);
    let itemsProcessadosNestaSessao = 0;

    try {
      while (itensParaProcessar.length > 0) {
        const payload = {
          items: itensParaProcessar.map(p => ({
            row_index: p.row_index,
            grupo: '',
            subgrupo: ''
          }))
        };

        const res = await fetch(`${API_BASE}/jobs/${jobId}/categorize_ai`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${session.access_token}`,
          },
          body: JSON.stringify(payload),
        });

        if (!res.ok) {
          throw new Error('Falha ao processar IA. Verifique se a API Key está configurada.');
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error('Stream não disponível.');

        const decoder = new TextDecoder();
        let buffer = '';
        let recebeuResultadosNesteCiclo = false;
        let idLinhasRecebidas = new Set<number>();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';

          for (const eventStr of parts) {
            if (!eventStr.trim()) continue;

            const lines = eventStr.split('\n');
            let tipoEvento = '';
            let dataStr = '';

            for (const line of lines) {
              if (line.startsWith('event: ')) {
                tipoEvento = line.slice(7).trim();
              } else if (line.startsWith('data: ')) {
                dataStr += line.slice(6).trim();
              }
            }

            if (tipoEvento && dataStr) {
              try {
                const data = JSON.parse(dataStr);
                
                if (tipoEvento === 'start' || tipoEvento === 'progress') {
                  setAiProgress({
                    sublote: data.sublote || 0,
                    totalSublotes: data.total_sublotes,
                    totalAcumulado: (data.total_acumulado || 0) + itemsProcessadosNestaSessao,
                    // O total original é itensParaProcessar.length + itemsProcessadosNestaSessao
                    totalItens: data.total_itens + itemsProcessadosNestaSessao, 
                  });
                  
                  if (data.new_items && data.new_items.length > 0) {
                    recebeuResultadosNesteCiclo = true;
                    itemsProcessadosNestaSessao += data.new_items.length;
                    
                    data.new_items.forEach((sug: any) => idLinhasRecebidas.add(sug.row_index));

                    setEdicoes(anteriores => {
                      const novas = { ...anteriores };
                      data.new_items.forEach((sug: any) => {
                        if (sug.grupo && sug.subgrupo) {
                          novas[sug.row_index] = {
                            grupo: sug.grupo,
                            subgrupo: sug.subgrupo,
                            viaIA: true
                          };
                        }
                      });
                      return novas;
                    });
                  }
                } else if (tipoEvento === 'result') {
                  // Fallback se n tiver vindo no progress
                  if (!recebeuResultadosNesteCiclo && data.suggested && data.suggested.length > 0) {
                    recebeuResultadosNesteCiclo = true;
                    itemsProcessadosNestaSessao += data.suggested.length;
                    data.suggested.forEach((sug: any) => idLinhasRecebidas.add(sug.row_index));

                    setEdicoes(anteriores => {
                      const novas = { ...anteriores };
                      data.suggested.forEach((sug: any) => {
                        if (sug.grupo && sug.subgrupo) {
                          novas[sug.row_index] = { grupo: sug.grupo, subgrupo: sug.subgrupo, viaIA: true };
                        }
                      });
                      return novas;
                    });
                  }
                }
              } catch (err) {
                console.error('Erro ao parsear JSON SSE:', err);
              }
            }
          }
        }

        // Conexão terminou (seja por sucesso ou porque a Vercel derrubou por tempo limite)
        if (!recebeuResultadosNesteCiclo) {
          // Se a conexão fechou sem receber NADA útil, provável erro de proxy persistente. Para evitar loop infinito:
          console.warn('Conexão fechada sem progresso.');
          break;
        }

        // Filtra os itens para a próxima iteração, caso a conexão tenha caído antes de terminar
        itensParaProcessar = itensParaProcessar.filter(item => !idLinhasRecebidas.has(item.row_index));

        if (itensParaProcessar.length > 0) {
          console.log(`Conexão caiu, auto-retomando para os ${itensParaProcessar.length} itens restantes...`);
          // Pequena pausa antes de reconectar para dar fôlego ao servidor
          await new Promise(r => setTimeout(r, 2000));
        }
      }

      if (itemsProcessadosNestaSessao > 0) {
        alert(`${itemsProcessadosNestaSessao} itens classificados pela IA!\nPor favor, revise a lista e clique em "Salvar Progresso".`);
      } else {
        alert('A IA não retornou sugestões. Tente novamente mais tarde.');
      }

    } catch (err: any) {
      alert(err.message || 'Erro ao chamar a IA.');
    } finally {
      setIsAiLoading(false);
      setAiProgress(null);
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

  // ── Gera números de página para exibir (com elipses) ──────────────────
  const gerarNumerosPagina = (): (number | '...')[] => {
    if (totalPaginas <= 7) {
      return Array.from({ length: totalPaginas }, (_, i) => i + 1);
    }

    const paginas: (number | '...')[] = [1];

    if (paginaAtual > 3) paginas.push('...');

    const inicio = Math.max(2, paginaAtual - 1);
    const fim = Math.min(totalPaginas - 1, paginaAtual + 1);

    for (let i = inicio; i <= fim; i++) {
      paginas.push(i);
    }

    if (paginaAtual < totalPaginas - 2) paginas.push('...');

    paginas.push(totalPaginas);
    return paginas;
  };

  if (carregando) {
    return (
      <div className="review-loading">
        <div className="review-loading-spinner"></div>
        <h2>Carregando resultados da revisão...</h2>
      </div>
    );
  }

  const indiceInicio = (paginaAtual - 1) * itensPorPagina + 1;
  const indiceFim = Math.min(paginaAtual * itensPorPagina, itensFiltrados.length);

  // ── Renderização da Interface ────────────────────────────────────────────

  return (
    <div className="review-panel">
      
      {/* ═══ Cabeçalho com Métricas ═══ */}
      <div className="review-header">
        <div className="review-metrics">
          <div className="review-metric">
            <span className="review-metric-label">Pendentes</span>
            <span className="review-metric-value warning">{totalPendentes}</span>
          </div>
          <div className="review-metric">
            <span className="review-metric-label">Aprovados</span>
            <span className="review-metric-value success">{totalAprovados}</span>
          </div>
          <div className="review-metric">
            <span className="review-metric-label">Total</span>
            <span className="review-metric-value">{resultados.length}</span>
          </div>
        </div>

        <div className="review-controls">
          <input 
            type="text" 
            placeholder="🔍 Buscar por descrição..." 
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            className="review-search"
          />
          <select 
            value={filtro} 
            onChange={(e) => setFiltro(e.target.value as any)}
            className="review-select"
          >
            <option value="pendentes">Mostrar Pendentes</option>
            <option value="todos">Mostrar Todos</option>
          </select>
          {totalPendentes > 0 && (
            <button 
              onClick={categorizarComIA} 
              disabled={isAiLoading}
              className="review-btn-back" 
              title="Mandar itens pendentes para a Inteligência Artificial (OpenRouter)"
              style={{ background: 'rgba(167, 139, 250, 0.1)', color: '#a78bfa', borderColor: 'rgba(167, 139, 250, 0.3)' }}
            >
              {isAiLoading ? '🪄 Pensando...' : '🪄 Classificar com IA'}
            </button>
          )}
          <button onClick={() => setMostrarEditor(true)} className="review-btn-back" title="Editar nomes de grupos e subgrupos">
            ⚙️ Taxonomia
          </button>
          <button onClick={aoVoltar} className="review-btn-back">
            ← Voltar
          </button>
        </div>
      </div>

      {aiProgress && (
        <div style={{ margin: '0 24px 16px', background: 'var(--surface)', padding: '16px', borderRadius: '12px', border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px', color: 'var(--text-secondary)' }}>
            <strong>🪄 IA Trabalhando...</strong>
            <span>Lote {aiProgress.sublote} / {aiProgress.totalSublotes}</span>
          </div>
          <div style={{ width: '100%', height: '8px', background: 'var(--background)', borderRadius: '4px', overflow: 'hidden' }}>
            <div 
              style={{ 
                width: `${(aiProgress.sublote / aiProgress.totalSublotes) * 100}%`, 
                height: '100%', 
                background: 'linear-gradient(90deg, #a78bfa, #8b5cf6)',
                transition: 'width 0.3s ease'
              }} 
            />
          </div>
          <div style={{ marginTop: '8px', fontSize: '13px', color: 'var(--text-tertiary)', textAlign: 'right' }}>
            {aiProgress.totalAcumulado} de {aiProgress.totalItens} classificados
          </div>
        </div>
      )}

      {erro && (
        <div className="review-error">
          ⚠️ {erro}
        </div>
      )}

      {/* ═══ Barra de Paginação Superior ═══ */}
      <div className="review-pagination-bar">
        <div className="review-pagination-info">
          <span className="review-pagination-showing">
            Exibindo <strong>{itensFiltrados.length > 0 ? indiceInicio : 0}</strong>–<strong>{indiceFim}</strong> de <strong>{itensFiltrados.length}</strong> itens
          </span>
          {selecionados.size > 0 && (
            <span className="review-pagination-selected">
              ({selecionados.size} selecionado{selecionados.size > 1 ? 's' : ''})
            </span>
          )}
        </div>

        <div className="review-pagination-controls">
          <label className="review-per-page-label">
            Por página:
            <select
              value={itensPorPagina}
              onChange={(e) => setItensPorPagina(Number(e.target.value))}
              className="review-per-page-select"
            >
              {OPCOES_POR_PAGINA.map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>

          <div className="review-page-tabs">
            <button
              className="review-page-btn"
              disabled={paginaAtual === 1}
              onClick={() => setPaginaAtual(p => Math.max(1, p - 1))}
              aria-label="Página anterior"
            >
              ‹
            </button>

            {gerarNumerosPagina().map((num, idx) =>
              num === '...' ? (
                <span key={`dots-${idx}`} className="review-page-dots">…</span>
              ) : (
                <button
                  key={num}
                  className={`review-page-btn ${paginaAtual === num ? 'active' : ''}`}
                  onClick={() => setPaginaAtual(num)}
                >
                  {num}
                </button>
              )
            )}

            <button
              className="review-page-btn"
              disabled={paginaAtual === totalPaginas}
              onClick={() => setPaginaAtual(p => Math.min(totalPaginas, p + 1))}
              aria-label="Próxima página"
            >
              ›
            </button>
          </div>
        </div>
      </div>

      {/* ═══ Painel de Alteração em Massa ═══ */}
      {selecionados.size > 0 && (
        <div className="review-bulk-panel">
          <h3 className="review-bulk-title">
            ✏️ Alteração em Massa ({selecionados.size} selecionado{selecionados.size > 1 ? 's' : ''})
          </h3>
          
          <div className="review-bulk-fields">
            <div className="review-bulk-field">
              <label>Grupo</label>
              <select 
                value={grupoPainelMassa} 
                onChange={(e) => {
                  setGrupoPainelMassa(e.target.value);
                  setSubgrupoPainelMassa('');
                }}
                className="review-select"
              >
                <option value="">-- Selecione --</option>
                {todosOsGrupos.map(g => <option key={g} value={g}>{g}</option>)}
                <option value={OPCAO_PERSONALIZADO}>+ Criar Personalizado</option>
              </select>
              {grupoPainelMassa === OPCAO_PERSONALIZADO && (
                <input 
                  type="text" placeholder="Nome do novo grupo" value={grupoPersonalizadoMassa}
                  onChange={(e) => setGrupoPersonalizadoMassa(e.target.value)}
                  className="review-input"
                />
              )}
            </div>

            <div className="review-bulk-field">
              <label>Subgrupo</label>
              <select 
                value={subgrupoPainelMassa} 
                onChange={(e) => setSubgrupoPainelMassa(e.target.value)}
                disabled={!grupoPainelMassa}
                className="review-select"
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
                  className="review-input"
                />
              )}
            </div>

            <div className="review-bulk-action">
              <button onClick={aplicarEdicaoEmMassa} className="review-btn-apply">
                Aplicar aos Selecionados
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══ Tabela de Resultados (desktop) / Cards (mobile) ═══ */}
      <div className="review-table-wrapper">
        <table className="review-table">
          <thead>
            <tr>
              <th className="review-th-check">
                <input 
                  type="checkbox" 
                  checked={itensPaginados.length > 0 && itensPaginados.every(i => selecionados.has(i.row_index))}
                  onChange={alternarSelecaoTodos}
                />
              </th>
              <th>Descrição Original</th>
              <th className="review-th-ean">EAN / NCM</th>
              <th>Grupo</th>
              <th>Subgrupo</th>
            </tr>
          </thead>
          <tbody>
            {itensPaginados.length === 0 ? (
              <tr>
                <td colSpan={5} className="review-empty">
                  Nenhum item encontrado.
                </td>
              </tr>
            ) : (
              itensPaginados.map(item => {
                const grupoAtual = obterGrupo(item);
                const subgrupoAtual = obterSubgrupo(item);
                const editado = !!edicoes[item.row_index];
                const selecionado = selecionados.has(item.row_index);
                const sugestao = sugestoes[item.row_index];

                return (
                  <tr 
                    key={item.row_index} 
                    className={`review-row ${selecionado ? 'selected' : ''} ${editado ? 'edited' : ''}`}
                  >
                    <td className="review-td-check">
                      <input 
                        type="checkbox" 
                        checked={selecionado}
                        onChange={() => alternarSelecaoItem(item.row_index)}
                      />
                    </td>
                    <td className="review-td-desc">
                      <div className="review-desc-text">{item.descricao}</div>
                      <div className="review-desc-meta">
                        Origem: {item.origem} | Status: {item.status}
                      </div>
                      {/* EAN/NCM inline on mobile */}
                      <div className="review-desc-ean-mobile">
                        EAN: {item.ean || '-'} · NCM: {item.ncm || '-'}
                      </div>
                      {/* Sugestão baseada em similaridade */}
                      {sugestao && (
                        <button
                          className="review-suggestion-pill"
                          onClick={() => aplicarSugestao(item.row_index)}
                          title={`Similar a: "${sugestao.descricaoRef}" (${Math.round(sugestao.similaridade * 100)}% similar)`}
                        >
                          <span className="review-suggestion-icon">💡</span>
                          <span className="review-suggestion-text">
                            {sugestao.grupo} › {sugestao.subgrupo}
                          </span>
                          <span className="review-suggestion-score">
                            {Math.round(sugestao.similaridade * 100)}%
                          </span>
                        </button>
                      )}
                    </td>
                    <td className="review-td-ean">
                      EAN: {item.ean || '-'}<br />
                      NCM: {item.ncm || '-'}
                    </td>
                    <td className="review-td-select">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {edicoes[item.row_index]?.viaIA && <span title="Classificado pela IA" style={{ fontSize: '16px' }}>🤖</span>}
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
                        className="review-inline-select"
                      >
                        <option value="">-- Selecione --</option>
                        {todosOsGrupos.map(g => <option key={g} value={g}>{g}</option>)}
                        {!todosOsGrupos.includes(grupoAtual) && grupoAtual && <option value={grupoAtual}>{grupoAtual}</option>}
                        <option value={OPCAO_PERSONALIZADO}>+ Personalizado</option>
                        </select>
                      </div>
                    </td>
                    <td className="review-td-select">
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
                        className="review-inline-select"
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

      {/* ═══ Cards layout (mobile only) ═══ */}
      <div className="review-cards-mobile">
        {itensPaginados.length === 0 ? (
          <div className="review-empty-card">Nenhum item encontrado.</div>
        ) : (
          <>
            <div className="review-cards-select-all">
              <label>
                <input
                  type="checkbox"
                  checked={itensPaginados.length > 0 && itensPaginados.every(i => selecionados.has(i.row_index))}
                  onChange={alternarSelecaoTodos}
                />
                Selecionar todos desta página
              </label>
            </div>
            {itensPaginados.map(item => {
              const grupoAtual = obterGrupo(item);
              const subgrupoAtual = obterSubgrupo(item);
              const editado = !!edicoes[item.row_index];
              const selecionado = selecionados.has(item.row_index);
              const sugestao = sugestoes[item.row_index];

              return (
                <div 
                  key={item.row_index} 
                  className={`review-card ${selecionado ? 'selected' : ''} ${editado ? 'edited' : ''}`}
                >
                  <div className="review-card-header">
                    <input 
                      type="checkbox" 
                      checked={selecionado}
                      onChange={() => alternarSelecaoItem(item.row_index)}
                    />
                    <div className="review-card-desc">
                      <strong>{item.descricao}</strong>
                      <span className="review-card-meta">
                        {item.origem} · {item.status}
                      </span>
                    </div>
                  </div>

                  {/* Sugestão no card mobile */}
                  {sugestao && (
                    <button
                      className="review-suggestion-pill"
                      onClick={() => aplicarSugestao(item.row_index)}
                      title={`Similar a: "${sugestao.descricaoRef}"`}
                    >
                      <span className="review-suggestion-icon">💡</span>
                      <span className="review-suggestion-text">
                        {sugestao.grupo} › {sugestao.subgrupo}
                      </span>
                      <span className="review-suggestion-score">
                        {Math.round(sugestao.similaridade * 100)}%
                      </span>
                    </button>
                  )}

                  <div className="review-card-codes">
                    <span>EAN: {item.ean || '-'}</span>
                    <span>NCM: {item.ncm || '-'}</span>
                  </div>

                  <div className="review-card-selects">
                    <div className="review-card-field">
                      <label style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        Grupo {edicoes[item.row_index]?.viaIA && <span title="Classificado pela IA">🤖</span>}
                      </label>
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
                        className="review-inline-select"
                      >
                        <option value="">-- Selecione --</option>
                        {todosOsGrupos.map(g => <option key={g} value={g}>{g}</option>)}
                        {!todosOsGrupos.includes(grupoAtual) && grupoAtual && <option value={grupoAtual}>{grupoAtual}</option>}
                        <option value={OPCAO_PERSONALIZADO}>+ Personalizado</option>
                      </select>
                    </div>
                    <div className="review-card-field">
                      <label>Subgrupo</label>
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
                        className="review-inline-select"
                      >
                        <option value="">-- Selecione --</option>
                        {(taxonomiaCompleta[grupoAtual] || []).map(s => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                        {!(taxonomiaCompleta[grupoAtual] || []).includes(subgrupoAtual) && subgrupoAtual && <option value={subgrupoAtual}>{subgrupoAtual}</option>}
                        {grupoAtual && <option value={OPCAO_PERSONALIZADO}>+ Personalizado</option>}
                      </select>
                    </div>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>

      {/* ═══ Barra de Paginação Inferior ═══ */}
      {itensFiltrados.length > 0 && (
        <div className="review-pagination-bar bottom">
          <div className="review-pagination-info">
            <span className="review-pagination-showing">
              Página <strong>{paginaAtual}</strong> de <strong>{totalPaginas}</strong>
            </span>
          </div>

          <div className="review-page-tabs">
            <button
              className="review-page-btn"
              disabled={paginaAtual === 1}
              onClick={() => setPaginaAtual(p => Math.max(1, p - 1))}
              aria-label="Página anterior"
            >
              ‹ Anterior
            </button>
            <button
              className="review-page-btn"
              disabled={paginaAtual === totalPaginas}
              onClick={() => setPaginaAtual(p => Math.min(totalPaginas, p + 1))}
              aria-label="Próxima página"
            >
              Próxima ›
            </button>
          </div>
        </div>
      )}

      {/* ═══ Editor de Taxonomia (Modal) ═══ */}
      {mostrarEditor && (
        <div className="review-editor-overlay" onClick={() => setMostrarEditor(false)}>
          <div className="review-editor-modal" onClick={(e) => e.stopPropagation()}>
            <div className="review-editor-header">
              <h3>⚙️ Editor de Taxonomia</h3>
              <p>Clique no ✏️ para renomear grupos ou subgrupos</p>
              <button className="review-editor-close" onClick={() => setMostrarEditor(false)}>✕</button>
            </div>
            <div className="review-editor-body">
              {todosOsGrupos.map(grupo => (
                <div key={grupo} className="review-editor-group">
                  <div className="review-editor-group-header">
                    <span className="review-editor-group-name">{grupo}</span>
                    <button
                      className="review-editor-rename-btn"
                      onClick={() => renomearGrupo(grupo)}
                      title={`Renomear grupo "${grupo}"`}
                    >
                      ✏️
                    </button>
                  </div>
                  <div className="review-editor-subgroups">
                    {(taxonomiaCompleta[grupo] || []).map(sub => (
                      <div key={sub} className="review-editor-subgroup">
                        <span>{sub}</span>
                        <button
                          className="review-editor-rename-btn small"
                          onClick={() => renomearSubgrupo(grupo, sub)}
                          title={`Renomear subgrupo "${sub}"`}
                        >
                          ✏️
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ═══ Rodapé: Ações Finais ═══ */}
      <div className="review-footer">
        <button 
          onClick={() => salvarAlteracoes(false)}
          disabled={salvando || finalizando || Object.keys(edicoes).length === 0}
          className="review-btn-save"
        >
          {salvando && !finalizando ? 'Salvando...' : `💾 Salvar Progresso${Object.keys(edicoes).length > 0 ? ` (${Object.keys(edicoes).length})` : ''}`}
        </button>
        
        <button 
          onClick={() => salvarAlteracoes(true)}
          disabled={salvando || finalizando || totalPendentes > Object.keys(edicoes).length}
          title={totalPendentes > Object.keys(edicoes).length ? 'Você precisa categorizar todos os itens pendentes antes de finalizar.' : ''}
          className="review-btn-finalize"
        >
          {finalizando ? 'Finalizando...' : '✅ Finalizar Revisão'}
        </button>
      </div>

    </div>
  );
}
