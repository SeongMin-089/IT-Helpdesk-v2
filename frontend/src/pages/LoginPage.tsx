import { useState, type FormEvent } from 'react'
import { Eye, EyeOff, Headphones, LockKeyhole, UserRound } from 'lucide-react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../contexts/AuthContext'
import { ApiError } from '../services/api'

export function LoginPage() {
  const { user, checkingSession, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [loginId, setLoginId] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  if (!checkingSession && user) return <Navigate to="/dashboard" replace />

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setError('')
    try {
      await login(loginId.trim(), password)
      const destination = (location.state as { from?: string } | null)?.from
      navigate(destination?.startsWith('/') ? destination : '/dashboard', { replace: true })
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.status === 401 ? '아이디 또는 비밀번호를 확인해 주세요.' : caught.message)
      } else {
        setError('로그인 서버에 연결할 수 없습니다.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-brand" aria-label="IT Helpdesk 소개">
        <div className="login-brand__content">
          <span className="login-brand__icon"><Headphones size={32} /></span>
          <p className="eyebrow">INTERNAL SERVICE PORTAL</p>
          <h1>업무의 흐름을<br />더 빠르고 명확하게.</h1>
          <p>문의 등록부터 처리 현황 확인까지 한곳에서 관리하는 사내 IT 지원 포털입니다.</p>
          <div className="login-brand__metrics"><span><strong>빠른 접수</strong>실시간 문의 현황</span><span><strong>안전한 접근</strong>Odoo 세션 인증</span></div>
        </div>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={handleSubmit}>
          <div className="login-card__mobile-brand"><Headphones size={24} /><strong>IT Helpdesk</strong></div>
          <p className="eyebrow">WELCOME BACK</p>
          <h2>로그인</h2>
          <p className="login-card__intro">사내 Odoo 계정으로 로그인해 주세요.</p>

          <label className="field">
            <span>로그인 ID</span>
            <div className="input-with-icon"><UserRound size={18} /><input value={loginId} onChange={(event) => setLoginId(event.target.value)} autoComplete="username" placeholder="employee@company.com" required disabled={submitting} /></div>
          </label>
          <label className="field">
            <span>비밀번호</span>
            <div className="input-with-icon"><LockKeyhole size={18} /><input type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" placeholder="비밀번호 입력" required disabled={submitting} /><button type="button" className="password-toggle" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>
          </label>

          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="button button--primary button--large" type="submit" disabled={submitting || checkingSession}>
            {submitting ? <><span className="spinner spinner--small" />로그인 중...</> : '로그인'}
          </button>
          <p className="login-card__help">계정 관련 문의는 IT 담당자에게 연락해 주세요.</p>
        </form>
      </section>
    </main>
  )
}
