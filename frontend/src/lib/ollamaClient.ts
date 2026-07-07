/**
 * Cliente Ollama Local — chama o Ollama diretamente do navegador.
 *
 * Como o Ollama roda na mesma máquina que o navegador do usuário,
 * podemos chamar localhost:11434 diretamente, sem passar pelo Railway.
 *
 * Pré-requisito: Ollama deve estar rodando com OLLAMA_ORIGINS=*
 *   Windows:  set OLLAMA_ORIGINS=* && ollama serve
 *   Linux:    OLLAMA_ORIGINS=* ollama serve
 */

const OLLAMA_URL = 'http://localhost:11434/v1/chat/completions';
const OLLAMA_MODEL = 'qwen2.5:3b';

const TAXONOMIA_PROMPT = `OPÇÕES VÁLIDAS DE GRUPOS E SUBGRUPOS:
- Bazar e Utilidades: Utensílios de Cozinha, Recipientes de Plástico, Vidros e Taças, Panelas, Garrafas Térmicas, Talheres
- Móveis: Cadeiras e Poltronas, Mesas, Colchões e Camas, Armários e Roupeiros, Estantes e Racks
- Decoração: Espelhos, Relógios de Parede, Vasos, Quadros
- Lazer e Camping: Piscinas e Acessórios, Caixas Térmicas, Barracas, Cadeiras de Praia
- Ferramentas e Ferragens: Elétricas, Manuais, Medição, Ferragens e Cadeados
- Materiais de Construção: Pintura, Hidráulica, Elétrica
- Eletro e Eletrônicos: Eletroportáteis, Cabos e Carregadores, Áudio e Som, Acessórios de Celular, Pilhas e Baterias
- Limpeza: Utensílios de Limpeza (Vassouras/Rodos), Produtos Químicos, Lixeiras e Cestos, Organização
- Bebidas: Vinhos, Cervejas, Refrigerantes, Sucos e Chás, Água, Destilados e Ice, Energéticos
- Alimentos (Mercearia): Biscoitos e Salgadinhos, Doces e Sobremesas, Conservas e Molhos, Grãos e Massas, Óleos e Temperos, Pipoca
- Frios e Congelados: Carnes e Aves, Sorvetes e Picolés, Pratos Prontos
- Higiene e Cuidados Pessoais: Cabelo, Sabonetes, Desodorantes, Higiene Oral, Cosméticos, Absorventes
- Automotivo e Moto: Capacetes, Acessórios Moto, Acessórios Carro
- Brinquedos: Bonecas, Carrinhos e Pistas, Jogos de Tabuleiro, Pelúcias, Praia e Piscina Infantil
- Vestuário e Calçados: Chinelos e Sandálias, Peças Íntimas, Roupas, Capas de Chuva
- Tabacaria: Cigarros, Isqueiros e Fósforos, Acessórios
- Cama, Mesa e Banho: Toalhas, Tapetes, Cortinas e Varões
- Padaria e Lanchonete: Pães e Salgados, Bolos e Tortas, Refeições Prontas, Lanches Rápidos`;

export interface ItemParaClassificar {
  row_index: number;
  descricao: string;
  ncm?: string;
}

export interface ResultadoOllama {
  row_index: number;
  grupo: string;
  subgrupo: string;
  confianca: number;
}

/**
 * Verifica se o Ollama está acessível em localhost:11434.
 * Retorna true se o servidor responder, false caso contrário.
 */
export async function verificarOllamaDisponivel(): Promise<boolean> {
  try {
    const res = await fetch('http://localhost:11434/api/tags', {
      method: 'GET',
      signal: AbortSignal.timeout(3000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Classifica um lote de produtos chamando o Ollama local diretamente do browser.
 *
 * @param itens  Lista de produtos pendentes (max ~15 por lote para modelos 3B)
 * @returns      Lista de classificações retornadas pelo modelo
 */
export async function classificarViaOllamaLocal(
  itens: ItemParaClassificar[]
): Promise<ResultadoOllama[]> {
  // Montar prompt idêntico ao usado no backend
  const itensTexto = itens.map((p) => {
    let texto = `ID_LINHA: ${p.row_index} | Descrição: ${p.descricao}`;
    if (p.ncm) texto += ` | NCM: ${p.ncm}`;
    return texto;
  });

  const promptSistema = `Você é um classificador determinístico de dados de varejo.
Abaixo está uma lista de produtos para categorizar em lote.

REGRA 1: A Descrição é a ÚNICA fonte da verdade. Ignore o NCM se for industrial ou divergente.
REGRA 2: Você DEVE classificar escolhendo estritamente entre estas opções:
${TAXONOMIA_PROMPT}
REGRA 3: Responda APENAS com um objeto JSON válido, contendo uma chave "produtos" que é uma lista de objetos.
Cada objeto deve ter:
- "id_linha": número inteiro (deve ser exatamente o mesmo fornecido)
- "grupo": string exata de um dos grupos permitidos
- "subgrupo": string exata de um dos subgrupos permitidos
- "grau_de_confianca": inteiro de 0 a 100

Não inclua formatação markdown ou texto extra, apenas o JSON puro.`;

  const payload = {
    model: OLLAMA_MODEL,
    messages: [
      { role: 'system', content: promptSistema },
      { role: 'user', content: `PRODUTOS A CLASSIFICAR:\n${itensTexto.join('\n')}` },
    ],
    temperature: 0.1,
    response_format: { type: 'json_object' },
  };

  const response = await fetch(OLLAMA_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errText = await response.text().catch(() => 'sem detalhes');
    throw new Error(`Ollama respondeu ${response.status}: ${errText}`);
  }

  const data = await response.json();

  if (!data.choices || !data.choices[0]?.message?.content) {
    throw new Error('Resposta vazia do Ollama.');
  }

  let content = data.choices[0].message.content.trim();

  // Limpar markdown fences
  if (content.startsWith('```json')) content = content.slice(7);
  if (content.startsWith('```')) content = content.slice(3);
  if (content.endsWith('```')) content = content.slice(0, -3);
  content = content.trim();

  const parsed = JSON.parse(content);
  const produtosRaw: any[] = parsed.produtos ?? (Array.isArray(parsed) ? parsed : []);

  const resultados: ResultadoOllama[] = [];
  for (const item of produtosRaw) {
    const idLinha = item.id_linha ?? item.row_index;
    const grupo = String(item.grupo ?? '').trim();
    const subgrupo = String(item.subgrupo ?? '').trim();
    const confianca = Math.max(0, Math.min(100, Number(item.grau_de_confianca ?? 0)));

    if (idLinha != null && grupo && subgrupo) {
      resultados.push({
        row_index: Number(idLinha),
        grupo,
        subgrupo,
        confianca,
      });
    }
  }

  return resultados;
}
