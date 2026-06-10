/**
 * Em produção (Vercel): chama o Railway diretamente — evita limite de 4.5MB do proxy Vercel.
 * Em desenvolvimento local: usa /api com proxy do Next.js (next.config.js rewrites).
 */
function resolveApiBase(): string {
  const url = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (url) return `${url}/api`;
  return '/api';
}

export const API_BASE = resolveApiBase();
