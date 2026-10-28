import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Filter, Search } from 'lucide-react'
import { EmptyState, ErrorState, PageLoader } from '../components/common/PageState'
import { useAuth } from '../contexts/AuthContext'
import { ApiError, apiRequest, toQuery } from '../services/api'
import { formatDate } from '../services/format'
import type { Stage, StageListResponse, TicketListResponse } from '../types/api'

const priorityOptions = [
  { value: '', label: '전체 긴급도' },
  { value: '0', label: '낮음' },
  { value: '1', label: '보통' },
  { value: '2', label: '높음' },
  { value: '3', label: '긴급' },
]

export function TicketsPage({ assignedOnly = false }: { assignedOnly?: boolean }) {
  const { user, clearSession } = useAuth()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [stageId, setStageId] = useState('')
  const [priority, setPriority] = useState('')
  const [page, setPage] = useState(1)
  const [stages, setStages] = useState<Stage[]>([])
  const [data, setData] = useState<TicketListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 350)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => { setPage(1) }, [debouncedSearch, stageId, priority, assignedOnly])

  useEffect(() => {
    apiRequest<StageListResponse>('/api/oca/stages')
      .then((response) => setStages(response.stages))
      .catch((caught: unknown) => {
        if (caught instanceof ApiError && caught.status === 401) clearSession()
      })
  }, [clearSession])

  const query = useMemo(
    () => toQuery({ q: debouncedSearch, stage_id: stageId, priority, page, page_size: 20, assignee_id: assignedOnly ? user?.id : undefined }),
    [assignedOnly, debouncedSearch, page, priority, stageId, user?.id],
  )

  const loadTickets = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await apiRequest<TicketListResponse>(`/api/oca/tickets${query}`))
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) clearSession()
      setError(caught instanceof ApiError ? caught.message : '문의 목록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }, [clearSession, query])

  useEffect(() => { void loadTickets() }, [loadTickets])

  return (
    <div className="page-stack">
      <header className="page-heading page-heading--inline">
        <div><p className="eyebrow">TICKETS</p><h1>{assignedOnly ? '내 담당 문의' : user?.role === 'agent' ? '전체 문의' : '내 문의'}</h1><p>{assignedOnly ? '현재 나에게 배정된 문의를 확인합니다.' : '문의 현황을 검색하고 필터링할 수 있습니다.'}</p></div>
        {data && <span className="result-count">총 <strong>{data.total.toLocaleString()}</strong>건</span>}
      </header>

      <section className="card filter-card" aria-label="문의 검색 필터">
        <label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="문의 번호, 제목, 내용 검색" aria-label="문의 검색" /></label>
        <div className="filter-select"><Filter size={17} /><select value={stageId} onChange={(event) => setStageId(event.target.value)} aria-label="상태 필터"><option value="">전체 상태</option>{stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></div>
        <div className="filter-select"><select value={priority} onChange={(event) => setPriority(event.target.value)} aria-label="긴급도 필터">{priorityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
      </section>

      <section className="card tickets-card">
        {loading ? <PageLoader label="문의 목록을 불러오는 중입니다." /> : error ? <ErrorState message={error} onRetry={() => void loadTickets()} /> : !data || data.tickets.length === 0 ? <EmptyState message="조건에 맞는 문의가 없습니다." /> : (
          <>
            <div className="table-wrap">
              <table><thead><tr><th>문의 번호</th><th>제목</th><th>유형</th><th>요청자</th><th>담당자</th><th>상태</th><th>긴급도</th><th>등록일</th></tr></thead>
                <tbody>{data.tickets.map((ticket) => <tr key={ticket.id}><td className="reference">{ticket.reference || `#${ticket.id}`}</td><td className="title-cell"><strong>{ticket.title}</strong><span>{ticket.description || '내용 없음'}</span></td><td>{ticket.category?.name ?? '-'}</td><td>{ticket.requester?.name ?? '-'}</td><td>{ticket.assignee?.name ?? <span className="muted">미배정</span>}</td><td><span className="status-badge">{ticket.status?.name ?? '미지정'}</span></td><td><span className={`priority-badge priority-badge--${ticket.priority_code}`}>{ticket.priority}</span></td><td>{formatDate(ticket.created_at)}</td></tr>)}</tbody>
              </table>
            </div>
            <div className="pagination"><span>{data.total_pages === 0 ? 0 : data.page} / {data.total_pages} 페이지</span><div><button className="icon-button" type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={data.page <= 1} aria-label="이전 페이지"><ChevronLeft size={19} /></button><button className="icon-button" type="button" onClick={() => setPage((value) => value + 1)} disabled={!data.has_next} aria-label="다음 페이지"><ChevronRight size={19} /></button></div></div>
          </>
        )}
      </section>
    </div>
  )
}
