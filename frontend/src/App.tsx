import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'
import { PageLoader } from './components/common/PageState'
import { AppLayout } from './components/layout/AppLayout'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { TicketsPage } from './pages/TicketsPage'

function ProtectedRoute() {
  const { user, checkingSession } = useAuth()
  const location = useLocation()
  if (checkingSession) return <PageLoader label="로그인 상태를 확인하는 중입니다." />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <Outlet />
}

function AgentRoute() {
  const { user } = useAuth()
  return user?.role === 'agent' ? <Outlet /> : <Navigate to="/dashboard" replace />
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/tickets" element={<TicketsPage />} />
              <Route element={<AgentRoute />}>
                <Route path="/assigned" element={<TicketsPage assignedOnly />} />
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
