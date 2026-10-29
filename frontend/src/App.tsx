import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'
import { ErrorState, PageLoader } from './components/common/PageState'
import { AppLayout } from './components/layout/AppLayout'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { NewTicketPage } from './pages/NewTicketPage'
import { TicketDetailPage } from './pages/TicketDetailPage'
import { TicketsPage } from './pages/TicketsPage'

function ProtectedRoute() {
  const { user, checkingSession, sessionError, retrySession } = useAuth()
  const location = useLocation()
  if (checkingSession) return <PageLoader label="로그인 상태를 확인하는 중입니다." />
  if (sessionError) return <ErrorState message={sessionError} onRetry={retrySession} />
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
              <Route path="/tickets/new" element={<NewTicketPage />} />
              <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
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
