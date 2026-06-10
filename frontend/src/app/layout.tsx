import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Categorizador Inteligente de Produtos',
  description:
    'Sistema de categorização inteligente de produtos em lote com IA. Arquitetura híbrida de funil: EAN/NCM → Busca Vetorial → LLM → Revisão Humana.',
  keywords: [
    'categorizador',
    'produtos',
    'inteligência artificial',
    'categorização',
    'EAN',
    'NCM',
    'machine learning',
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
