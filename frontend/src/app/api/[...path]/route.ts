/**
 * Proxy Route Handler — encaminha /api/* para o backend no Railway.
 *
 * O Vercel NÃO faz proxy real para domínios externos via next.config.js rewrites
 * (ele faz redirect, o que quebra o header Authorization).
 * Esta route handler resolve isso fazendo fetch server-side com todos os headers.
 */

import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ||
  'https://categorizador-production.up.railway.app';

async function proxyRequest(request: NextRequest, params: { path: string[] }) {
  const path = params.path.join('/');
  const targetUrl = `${BACKEND_URL}/api/${path}`;

  // Copiar headers relevantes do request original
  const headers = new Headers();

  const forwardHeaders = [
    'authorization',
    'content-type',
    'accept',
    'accept-encoding',
    'accept-language',
  ];

  for (const key of forwardHeaders) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }

  // Encaminhar o body para métodos que o suportam
  const hasBody = request.method !== 'GET' && request.method !== 'HEAD';
  const body = hasBody ? await request.arrayBuffer() : undefined;

  try {
    const backendResponse = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: body ? Buffer.from(body) : undefined,
      // Não seguir redirects — retornar direto ao cliente
      redirect: 'follow',
    });

    // Copiar headers da resposta do backend
    const responseHeaders = new Headers();
    const copyResponseHeaders = [
      'content-type',
      'content-disposition',
      'x-metrics-total',
      'x-metrics-aprovados',
      'x-metrics-pendentes',
      'x-processing-time',
    ];

    for (const key of copyResponseHeaders) {
      const value = backendResponse.headers.get(key);
      if (value) responseHeaders.set(key, value);
    }

    const responseBody = await backendResponse.arrayBuffer();

    return new NextResponse(responseBody, {
      status: backendResponse.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error('[Proxy] Erro ao contactar backend:', error);
    return NextResponse.json(
      { detail: 'Erro ao contactar o backend. Tente novamente.' },
      { status: 502 }
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}
