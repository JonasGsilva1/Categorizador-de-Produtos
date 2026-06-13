/**
 * Em produção (Vercel): chama o Railway diretamente.
 * Em desenvolvimento local: usa /api com proxy do Next.js (next.config.js rewrites).
 *
 * Os routers do backend ja incluem o prefixo /api, entao aqui usamos
 * apenas a URL base do backend (sem duplicar /api).
 */
function resolveApiBase(): string {
  const url = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (url) return url;
  return '/api';
}

export const API_BASE = resolveApiBase();
