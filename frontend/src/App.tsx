import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router'
import { ErrorState, PageLoader } from './components/common/PageState'
import { AppLayout } from './components/layout/AppLayout'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { CategoryAdminPage } from './pages/CategoryAdminPage'
import { DashboardPage } from './pages/DashboardPage'
import { FaqAdminPage } from './pages/FaqAdminPage'
import { FaqDetailPage } from './pages/FaqDetailPage'
import { FaqsPage } from './pages/FaqsPage'
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
              <Route path="/faqs" element={<FaqsPage />} />
              <Route path="/faqs/:faqId" element={<FaqDetailPage />} />
              <Route path="/tickets" element={<TicketsPage />} />
              <Route path="/archived" element={<TicketsPage archivedOnly />} />
              <Route path="/tickets/new" element={<NewTicketPage />} />
              <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
              <Route element={<AgentRoute />}>
                <Route path="/assigned" element={<TicketsPage assignedOnly />} />
                <Route path="/faq-admin" element={<FaqAdminPage />} />
                <Route path="/category-admin" element={<CategoryAdminPage />} />
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
