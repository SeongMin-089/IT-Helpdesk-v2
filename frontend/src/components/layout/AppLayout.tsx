import { useEffect, useRef, useState } from 'react'
import {
  CircleUserRound,
  ClipboardList,
  Gauge,
  Headphones,
  LogOut,
  Menu,
  MessageSquarePlus,
  UserRoundCheck,
  X,
} from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../../contexts/AuthContext'
import { roleLabel } from '../../services/format'

const pageTitles: Record<string, string> = {
  '/dashboard': '대시보드',
  '/tickets': '문의 관리',
  '/tickets/new': '문의 등록',
  '/assigned': '내 담당 문의',
}

function getPageTitle(pathname: string) {
  if (/^\/tickets\/\d+$/.test(pathname)) return '문의 상세'
  return pageTitles[pathname] ?? 'IT Helpdesk'
}

export function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const handleLogout = async () => {
    if (loggingOut) return
    setLoggingOut(true)
    setLogoutError('')
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch {
      if (mountedRef.current) setLogoutError('로그아웃하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      if (mountedRef.current) setLoggingOut(false)
    }
  }

  const closeMenu = () => setMenuOpen(false)

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar--open' : ''}`}>
        <div className="brand">
          <span className="brand__mark"><Headphones size={22} /></span>
          <span><strong>IT Helpdesk</strong><small>Service Portal</small></span>
          <button className="icon-button sidebar__close" type="button" onClick={closeMenu} aria-label="메뉴 닫기">
            <X size={20} />
          </button>
        </div>

        <nav className="sidebar__nav" aria-label="주 메뉴">
          <NavLink to="/dashboard" onClick={closeMenu}><Gauge size={19} />대시보드</NavLink>
          <NavLink to="/tickets" end onClick={closeMenu}><ClipboardList size={19} />{user?.role === 'agent' ? '문의 관리' : '내 문의'}</NavLink>
          <NavLink to="/tickets/new" onClick={closeMenu}><MessageSquarePlus size={19} />문의 등록</NavLink>
          {user?.role === 'agent' && (
            <NavLink to="/assigned" onClick={closeMenu}><UserRoundCheck size={19} />내 담당 문의</NavLink>
          )}
        </nav>

        <div className="sidebar__profile">
          <CircleUserRound size={34} aria-hidden="true" />
          <div><strong>{user?.name}</strong><span>{user ? roleLabel(user.role) : ''}</span></div>
        </div>
      </aside>

      {menuOpen && <button className="sidebar-backdrop" type="button" onClick={closeMenu} aria-label="메뉴 닫기" />}

      <div className="app-main">
        <header className="topbar">
          <div className="topbar__title">
            <button className="icon-button topbar__menu" type="button" onClick={() => setMenuOpen(true)} aria-label="메뉴 열기">
              <Menu size={21} />
            </button>
            <div><span>IT 지원 센터</span><strong>{getPageTitle(location.pathname)}</strong></div>
          </div>
          <div className="topbar__actions">
            <div className="topbar__user"><span>{user?.name}</span><small>{user ? roleLabel(user.role) : ''}</small></div>
            <button className="button button--ghost" type="button" onClick={handleLogout} disabled={loggingOut}>
              <LogOut size={17} />{loggingOut ? '로그아웃 중' : '로그아웃'}
            </button>
          </div>
        </header>
        <main className="content"><Outlet /></main>
        {logoutError && <div className="toast-error" role="alert">{logoutError}<button type="button" onClick={() => setLogoutError('')} aria-label="오류 닫기"><X size={16} /></button></div>}
      </div>
    </div>
  )
}
