/** @type {import('next').NextConfig} */
const RAILWAY_BACKEND_URL = "https://categorizador-production.up.railway.app";

// BACKEND_URL é server-only (sem NEXT_PUBLIC_) — usada pela Route Handler de proxy.
// NEXT_PUBLIC_API_URL ainda é suportada para compatibilidade com dev local.
const backendUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ||
  RAILWAY_BACKEND_URL;

const connectSrc = [
  "'self'",
  'https://*.supabase.co',
  'https://*.supabase.com',
  'https://categorizador-de-produtos.vercel.app',
  backendUrl,
  'http://localhost:8000',
  'http://127.0.0.1:8000',
]
  .filter(Boolean)
  .join(' ');

const nextConfig = {
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: `default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src ${connectSrc}; frame-ancestors 'none';`,
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains; preload',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
