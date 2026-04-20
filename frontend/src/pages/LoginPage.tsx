import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { isAxiosError } from 'axios'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

type LoginFormState = {
  email: string
  password: string
}

const initialForm: LoginFormState = {
  email: '',
  password: '',
}

function extractErrorMessage(error: unknown): string {
  if (!isAxiosError(error)) {
    return 'Login failed. Please try again.'
  }

  const detail = error.response?.data?.detail
  if (typeof detail === 'string' && detail.trim().length > 0) {
    return detail
  }

  return 'Login failed. Please check your credentials.'
}

export default function LoginPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { login, isAuthenticated } = useAuth()
  const redirectTo = (location.state as { from?: string } | undefined)?.from ?? '/dashboard'

  const [form, setForm] = useState<LoginFormState>(initialForm)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    if (isAuthenticated) {
      navigate(redirectTo, { replace: true })
    }
  }, [isAuthenticated, navigate, redirectTo])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (isSubmitting) return

    setErrorMessage(null)
    setIsSubmitting(true)

    try {
      await login(form)
      navigate(redirectTo, { replace: true })
    } catch (error) {
      setErrorMessage(extractErrorMessage(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_15%_20%,rgba(20,184,166,0.15),transparent_35%),radial-gradient(circle_at_80%_10%,rgba(251,146,60,0.15),transparent_30%),linear-gradient(180deg,#0b1020_0%,#111827_100%)] px-4 py-10">
      <div className="pointer-events-none absolute inset-0 opacity-60 [background:linear-gradient(115deg,transparent_0%,rgba(148,163,184,0.08)_30%,transparent_65%)]" />
      <section className="relative z-10 w-full max-w-md animate-fade-in">
        <Card className="border border-white/10 bg-slate-950/70 text-slate-100 shadow-2xl shadow-black/30 backdrop-blur-xl">
          <CardHeader className="space-y-2">
            <p className="text-xs font-semibold tracking-[0.24em] uppercase text-teal-300/90">
              OrderHub CRM
            </p>
            <CardTitle className="font-heading text-3xl leading-tight">
              Welcome back
            </CardTitle>
            <CardDescription className="text-slate-300">
              Sign in to manage orders, customers, and production flow.
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <label className="block text-xs font-medium tracking-wide text-slate-300 uppercase" htmlFor="email">
                  Email
                </label>
                <Input
                  id="email"
                  autoComplete="email"
                  className="h-10 border-slate-700/80 bg-slate-900/70 text-slate-100 placeholder:text-slate-400"
                  disabled={isSubmitting}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  placeholder="owner@orderhub.dev"
                  required
                  type="email"
                  value={form.email}
                />
              </div>

              <div className="space-y-2">
                <label className="block text-xs font-medium tracking-wide text-slate-300 uppercase" htmlFor="password">
                  Password
                </label>
                <Input
                  id="password"
                  autoComplete="current-password"
                  className="h-10 border-slate-700/80 bg-slate-900/70 text-slate-100 placeholder:text-slate-400"
                  disabled={isSubmitting}
                  onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                  placeholder="Enter your password"
                  required
                  type="password"
                  value={form.password}
                />
              </div>

              {errorMessage ? (
                <p className="rounded-md border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-200">
                  {errorMessage}
                </p>
              ) : null}

              <Button className="h-10 w-full bg-teal-500 text-slate-950 hover:bg-teal-400" disabled={isSubmitting} type="submit">
                {isSubmitting ? 'Signing in...' : 'Sign in'}
              </Button>
            </form>

            <div className="mt-6 flex items-center justify-between text-xs text-slate-400">
              <span>Need access from owner?</span>
              <Link className="text-teal-300 hover:text-teal-200" to="/dashboard">
                Open preview
              </Link>
            </div>
          </CardContent>
        </Card>
      </section>
    </main>
  )
}
