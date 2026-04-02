'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { fetchCurrentUser, loginWithPassword } from '@/lib/mcap/api';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const checkExistingSession = async () => {
      try {
        await fetchCurrentUser();
        router.replace('/');
      } catch {
        // no active session; stay on login
      }
    };
    void checkExistingSession();
  }, [router]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await loginWithPassword(username.trim(), password);
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="skeuo-card w-full max-w-md">
        <div className="skeuo-card-header">
          <h1 className="font-serif text-3xl" style={{ color: 'var(--charcoal)' }}>Sign In</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--sienna)' }}>
            Enter your team account credentials.
          </p>
        </div>
        <form className="skeuo-card-content space-y-4" onSubmit={onSubmit}>
          <div className="space-y-1">
            <label htmlFor="username" className="text-sm font-medium">Username</label>
            <input
              id="username"
              className="skeuo-input w-full"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="text-sm font-medium">Password</label>
            <input
              id="password"
              type="password"
              className="skeuo-input w-full"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>

          {error && (
            <div
              className="rounded-md px-3 py-2 text-sm"
              style={{ background: 'rgba(179,58,46,0.08)', color: 'var(--danger)', border: '1px solid rgba(179,58,46,0.24)' }}
            >
              {error}
            </div>
          )}

          <button type="submit" className="skeuo-btn-primary w-full justify-center" disabled={submitting}>
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}
