import { Routes, Route, Navigate } from 'react-router-dom'

function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="glass rounded-xl p-8 w-full max-w-md animate-fade-in">
        <h1 className="text-2xl font-bold text-center mb-2">OrderHub</h1>
        <p className="text-center mb-6" style={{ color: 'var(--color-text-secondary)' }}>
          Order Management CRM
        </p>
        <p className="text-center" style={{ color: 'var(--color-text-muted)' }}>
          Login page — coming in Sprint 3
        </p>
      </div>
    </div>
  )
}

function DashboardPlaceholder() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="glass rounded-xl p-8 animate-fade-in text-center">
        <h1 className="text-3xl font-bold mb-2">🚀 OrderHub CRM</h1>
        <p style={{ color: 'var(--color-text-secondary)' }}>
          Backend is running. Frontend shell ready.
        </p>
        <p className="mt-4 text-sm" style={{ color: 'var(--color-text-muted)' }}>
          Sprint 1 — Foundation complete
        </p>
      </div>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/dashboard" element={<DashboardPlaceholder />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default App
