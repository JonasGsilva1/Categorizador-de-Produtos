/**
 * URL base da API.
 *
 * Todas as chamadas usam o path relativo /api, que é interceptado pela
 * Route Handler em src/app/api/[...path]/route.ts.
 * Essa route handler faz proxy server-side para o Railway, garantindo
 * que o header Authorization seja encaminhado corretamente.
 */
export const API_BASE = '/api';
