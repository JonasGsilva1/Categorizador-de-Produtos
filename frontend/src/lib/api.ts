/**
 * URL base da API.
 *
 * Em produção (Vercel): usa o proxy do Next.js (/api/*) que redireciona para o Railway.
 * Em desenvolvimento local: usa NEXT_PUBLIC_API_URL (ex: http://127.0.0.1:8000/api).
 *
 * NUNCA use uma URL absoluta do Vercel aqui — o browser faria a chamada para o
 * frontend, não para o backend, causando 308 redirect.
 */
const rawBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');

// Em dev, NEXT_PUBLIC_API_URL aponta direto para o backend (ex: http://127.0.0.1:8000)
// Em prod, não definimos a var → usa /api (proxy para o Railway via next.config.js)
export const API_BASE = rawBase ? `${rawBase}/api` : '/api';
