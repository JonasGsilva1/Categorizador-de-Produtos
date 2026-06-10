'use client';

import React, { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabaseClient';
import { useRouter } from 'next/navigation';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    // Redireciona se já estiver logado
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) router.push('/');
    });
  }, [router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      setError(error.message);
      setIsLoading(false);
    } else {
      router.push('/');
    }
  };

  return (
    <main className="app-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="glass-card" style={{ maxWidth: '400px', width: '100%', marginTop: '10vh' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div className="hero-badge">
            <span className="hero-badge-dot"></span>
            Acesso Restrito
          </div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#e8e8f0' }}>Categorizador IA</h2>
          <p style={{ color: '#a0a0c0', fontSize: '0.875rem', marginTop: '0.5rem' }}>Entre com suas credenciais para acessar o motor.</p>
        </div>

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: '#a0a0c0' }}>E-mail</label>
            <input 
              type="email" 
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: '100%', padding: '0.75rem', borderRadius: '8px',
                background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                color: '#fff', fontSize: '1rem', outline: 'none'
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: '#a0a0c0' }}>Senha</label>
            <input 
              type="password" 
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: '100%', padding: '0.75rem', borderRadius: '8px',
                background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                color: '#fff', fontSize: '1rem', outline: 'none'
              }}
            />
          </div>

          {error && <div className="error-banner" style={{ marginTop: '0' }}>{error}</div>}

          <button type="submit" className="btn btn-primary" style={{ marginTop: '1rem' }} disabled={isLoading}>
            {isLoading ? 'Autenticando...' : 'Entrar'}
          </button>
        </form>
      </div>
    </main>
  );
}
