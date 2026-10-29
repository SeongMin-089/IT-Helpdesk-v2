import { useEffect, useRef, useState } from 'react'
import { CircleCheckBig, CircleDot, Inbox, TicketCheck } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { EmptyState, ErrorState, PageLoader } from '../components/common/PageState'
import { useAuth } from '../contexts/AuthContext'
import { ApiError, apiRequest } from '../services/api'
import { formatDate, stageLabel } from '../services/format'
import type { DashboardResponse } from '../types/api'

const summaryCards = [
  { key: 'total', label: '전체 문의', helper: '활성 문의 전체', icon: TicketCheck },
  { key: 'open', label: '진행 중 문의', helper: '종료 전 문의', icon: CircleDot },
  { key: 'closed', label: '종료 문의', helper: '처리가 완료된 문의', icon: CircleCheckBig },
  { key: 'unassigned', label: '미배정 문의', helper: '담당자 확인 필요', icon: Inbox },
] as const

export function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const requestIdRef = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++requestIdRef.current
    void apiRequest<DashboardResponse>('/api/oca/dashboard', { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setData(response)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setError(caught instanceof ApiError ? caught.message : '대시보드를 불러오지 못했습니다.')
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setLoading(false)
      })
    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [retryKey])

  if (loading) return <PageLoader label="대시보드를 불러오는 중입니다." />
  if (error) return <ErrorState message={error} onRetry={() => { setLoading(true); setError(''); setRetryKey((value) => value + 1) }} />
  if (!data) return null

  const maxStage = Math.max(1, ...data.by_stage.map((item) => item.count))
  const maxPriority = Math.max(1, ...data.by_priority.map((item) => item.count))

  return (
    <div className="page-stack">
      <header className="page-heading">
        <div><p className="eyebrow">OVERVIEW</p><h1>안녕하세요, {user?.name}님</h1><p>현재 IT 문의 처리 현황을 확인하세요.</p></div>
      </header>

      <section className="summary-grid" aria-label="문의 요약">
        {summaryCards.map(({ key, label, helper, icon: Icon }) => (
          <article className="summary-card" key={key}>
            <span className={`summary-card__icon summary-card__icon--${key}`}><Icon size={21} /></span>
            <div><span>{label}</span><strong>{data.summary[key].toLocaleString()}</strong><small>{helper}</small></div>
          </article>
        ))}
      </section>

      <section className="dashboard-grid">
        <article className="card">
          <div className="card__heading"><div><h2>상태별 문의 현황</h2><p>현재 단계별 문의 분포입니다.</p></div></div>
          <div className="bar-list">
            {data.by_stage.map((stage) => (
              <div className="bar-row" key={stage.id}>
                <div className="bar-row__label"><span>{stageLabel(stage.name)}</span><strong>{stage.count}</strong></div>
                <div className="bar-track"><span style={{ width: `${(stage.count / maxStage) * 100}%` }} /></div>
              </div>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="card__heading"><div><h2>긴급도별 문의 현황</h2><p>문의 우선순위 분포입니다.</p></div></div>
          <div className="bar-list">
            {data.by_priority.map((priority) => (
              <div className="bar-row" key={priority.priority}>
                <div className="bar-row__label"><span className={`priority-dot priority-dot--${priority.priority}`} /> <span>{priority.label}</span><strong>{priority.count}</strong></div>
                <div className="bar-track"><span style={{ width: `${(priority.count / maxPriority) * 100}%` }} /></div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="card">
        <div className="card__heading"><div><h2>최근 등록 문의</h2><p>가장 최근에 등록된 문의 5건입니다.</p></div></div>
        {data.recent_tickets.length === 0 ? <EmptyState message="최근 등록된 문의가 없습니다." /> : (
          <div className="table-wrap">
            <table><thead><tr><th>문의 번호</th><th>제목</th><th>상태</th><th>긴급도</th><th>담당자</th><th>등록일</th></tr></thead>
              <tbody>{data.recent_tickets.map((ticket) => <tr className="clickable-row" key={ticket.id} tabIndex={0} onClick={() => navigate(`/tickets/${ticket.id}`)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') navigate(`/tickets/${ticket.id}`) }}><td className="reference">{ticket.reference || `#${ticket.id}`}</td><td className="title-cell"><Link to={`/tickets/${ticket.id}`} onClick={(event) => event.stopPropagation()}>{ticket.title}</Link></td><td><span className="status-badge">{stageLabel(ticket.status?.name)}</span></td><td><span className={`priority-badge priority-badge--${ticket.priority_code}`}>{ticket.priority}</span></td><td>{ticket.assignee?.name ?? '미배정'}</td><td>{formatDate(ticket.created_at)}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
