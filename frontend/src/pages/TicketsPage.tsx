import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUpDown, ChevronLeft, ChevronRight, Filter, RotateCcw, Search, SlidersHorizontal } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { EmptyState, ErrorState, PageLoader } from '../components/common/PageState'
import { useAuth } from '../contexts/AuthContext'
import { ApiError, apiRequest, toQuery } from '../services/api'
import { formatDate, stageLabel } from '../services/format'
import type { AssigneeListResponse, Stage, StageListResponse, TicketCategoryListResponse, TicketFilterOptionsResponse, TicketListResponse } from '../types/api'

const priorityOptions = [
  { value: '', label: '전체 긴급도' },
  { value: '0', label: '낮음' },
  { value: '1', label: '보통' },
  { value: '2', label: '높음' },
  { value: '3', label: '긴급' },
]

const sortOptions = [
  { value: 'priority', label: '긴급도순' },
  { value: 'newest', label: '최신 등록순' },
  { value: 'oldest', label: '오래된 등록순' },
  { value: 'updated', label: '최근 수정순' },
]

export function TicketsPage({ assignedOnly = false, archivedOnly = false }: { assignedOnly?: boolean; archivedOnly?: boolean }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedClosed = searchParams.get('closed')
  const closed = requestedClosed === 'true' || requestedClosed === 'false' ? requestedClosed : ''
  const unassigned = !assignedOnly && searchParams.get('unassigned') === 'true'
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [stageId, setStageId] = useState('')
  const [priority, setPriority] = useState('')
  const [sort, setSort] = useState('priority')
  const [categoryId, setCategoryId] = useState('')
  const [assigneeId, setAssigneeId] = useState('')
  const [requesterId, setRequesterId] = useState('')
  const [teamId, setTeamId] = useState('')
  const [tagId, setTagId] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(Boolean(closed || unassigned))
  const [page, setPage] = useState(1)
  const [stages, setStages] = useState<Stage[]>([])
  const [stagesLoading, setStagesLoading] = useState(true)
  const [stagesError, setStagesError] = useState('')
  const [stagesRetryKey, setStagesRetryKey] = useState(0)
  const [categories, setCategories] = useState<TicketCategoryListResponse['categories']>([])
  const [assignees, setAssignees] = useState<AssigneeListResponse['assignees']>([])
  const [filterOptions, setFilterOptions] = useState<TicketFilterOptionsResponse | null>(null)
  const [filterOptionsLoading, setFilterOptionsLoading] = useState(true)
  const [filterOptionsError, setFilterOptionsError] = useState('')
  const [filterOptionsRetryKey, setFilterOptionsRetryKey] = useState(0)
  const [data, setData] = useState<TicketListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const requestIdRef = useRef(0)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const nextSearch = search.trim()
      if (nextSearch === debouncedSearch) return
      setLoading(true)
      setError('')
      setPage(1)
      setDebouncedSearch(nextSearch)
    }, 350)
    return () => window.clearTimeout(timer)
  }, [debouncedSearch, search])

  useEffect(() => {
    const controller = new AbortController()
    apiRequest<StageListResponse>('/api/oca/stages', { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) setStages(response.stages)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setStagesError(caught instanceof ApiError ? caught.message : '상태 목록을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setStagesLoading(false)
      })
    return () => controller.abort()
  }, [stagesRetryKey])

  useEffect(() => {
    const controller = new AbortController()
    const requests: Promise<unknown>[] = [
      apiRequest<TicketCategoryListResponse>('/api/oca/categories', { signal: controller.signal })
        .then((response) => setCategories(response.categories)),
    ]
    if (user?.role === 'agent') {
      requests.push(
        apiRequest<AssigneeListResponse>('/api/oca/assignees', { signal: controller.signal })
          .then((response) => setAssignees(response.assignees)),
        apiRequest<TicketFilterOptionsResponse>('/api/oca/tickets/filter-options', { signal: controller.signal })
          .then(setFilterOptions),
      )
    }
    void Promise.all(requests).catch((caught: unknown) => {
      if (controller.signal.aborted) return
      setFilterOptionsError(caught instanceof ApiError ? caught.message : '상세 필터 선택 항목을 불러오지 못했습니다.')
    }).finally(() => {
      if (!controller.signal.aborted) setFilterOptionsLoading(false)
    })
    return () => controller.abort()
  }, [filterOptionsRetryKey, user?.role])

  const query = useMemo(
    () => toQuery({
      q: debouncedSearch,
      stage_id: stageId,
      priority,
      sort,
      category_id: categoryId,
      assignee_id: assignedOnly ? user?.id : user?.role === 'agent' ? assigneeId : undefined,
      partner_id: user?.role === 'agent' ? requesterId : undefined,
      team_id: user?.role === 'agent' ? teamId : undefined,
      tag_id: user?.role === 'agent' ? tagId : undefined,
      unassigned: !assignedOnly && unassigned ? 'true' : undefined,
      closed,
      page,
      page_size: 20,
    }),
    [assignedOnly, assigneeId, categoryId, closed, debouncedSearch, page, priority, requesterId, sort, stageId, tagId, teamId, unassigned, user?.id, user?.role],
  )
  const listPath = archivedOnly ? '/api/oca/tickets/archived' : '/api/oca/tickets'

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++requestIdRef.current
    void apiRequest<TicketListResponse>(`${listPath}${query}`, { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setData(response)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setError(caught instanceof ApiError ? caught.message : '문의 목록을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setLoading(false)
      })
    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [listPath, query, retryKey])

  const pageHeading = archivedOnly ? '보관함' : assignedOnly ? '내 담당 문의' : user?.role === 'agent' ? '전체 문의' : '내 문의'
  const pageDescription = archivedOnly
    ? '보관된 문의를 검색하고 필터링할 수 있습니다.'
    : assignedOnly
      ? '현재 나에게 배정된 문의를 확인합니다.'
      : '문의 현황을 검색하고 필터링할 수 있습니다.'

  const startFilterChange = () => {
    setLoading(true)
    setError('')
    setPage(1)
  }

  const updateUrlFilters = (updates: { closed?: string; unassigned?: boolean }) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (updates.closed !== undefined) {
        if (updates.closed) next.set('closed', updates.closed)
        else next.delete('closed')
      }
      if (updates.unassigned !== undefined) {
        if (updates.unassigned) next.set('unassigned', 'true')
        else next.delete('unassigned')
      }
      return next
    }, { replace: true })
  }

  const resetFilters = () => {
    startFilterChange()
    setSearch('')
    setDebouncedSearch('')
    setStageId('')
    setPriority('')
    setSort('priority')
    setCategoryId('')
    setAssigneeId('')
    setRequesterId('')
    setTeamId('')
    setTagId('')
    setSearchParams({}, { replace: true })
  }

  return (
    <div className="page-stack">
      <header className="page-heading page-heading--inline">
        <div><p className="eyebrow">{archivedOnly ? 'ARCHIVED TICKETS' : 'TICKETS'}</p><h1>{pageHeading}</h1><p>{pageDescription}</p></div>
        {data && <span className="result-count">총 <strong>{data.total.toLocaleString()}</strong>건</span>}
      </header>

      <section className="card filter-card" aria-label="문의 검색 필터">
        <label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="문의 번호, 제목, 내용 검색" aria-label="문의 검색" /></label>
        <div className="filter-select"><Filter size={17} /><select value={stageId} onChange={(event) => { setLoading(true); setError(''); setPage(1); setStageId(event.target.value) }} aria-label="상태 필터" disabled={stagesLoading || Boolean(stagesError)}><option value="">{stagesLoading ? '상태 불러오는 중' : stagesError ? '상태 로딩 실패' : '전체 상태'}</option>{stages.map((stage) => <option key={stage.id} value={stage.id}>{stageLabel(stage.name)}</option>)}</select></div>
        <div className="filter-select"><select value={priority} onChange={(event) => { setLoading(true); setError(''); setPage(1); setPriority(event.target.value) }} aria-label="긴급도 필터">{priorityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
        <div className="filter-select"><ArrowUpDown size={17} /><select value={sort} onChange={(event) => { setLoading(true); setError(''); setPage(1); setSort(event.target.value) }} aria-label="문의 정렬">{sortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
      </section>

      <section className="card advanced-filter-card" aria-label="문의 상세 필터">
        <div className="advanced-filter-card__heading"><div><SlidersHorizontal size={17} /><span>상세 필터</span></div><div><button className="button button--secondary" type="button" onClick={resetFilters}><RotateCcw size={15} />초기화</button><button className="button button--secondary" type="button" onClick={() => setAdvancedOpen((value) => !value)}>{advancedOpen ? '접기' : '펼치기'}</button></div></div>
        {advancedOpen && <div className="advanced-filter-grid">
          <label className="form-field"><span>문의 유형</span><select value={categoryId} onChange={(event) => { startFilterChange(); setCategoryId(event.target.value) }} disabled={filterOptionsLoading}><option value="">전체 유형</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.complete_name || category.name}</option>)}</select></label>
          <label className="form-field"><span>종료 여부</span><select value={closed} onChange={(event) => { startFilterChange(); updateUrlFilters({ closed: event.target.value }) }}><option value="">전체</option><option value="false">종료 전</option><option value="true">종료</option></select></label>
          {user?.role === 'agent' && !assignedOnly && <label className="form-field"><span>담당자</span><select value={assigneeId} onChange={(event) => { startFilterChange(); setAssigneeId(event.target.value); if (event.target.value) updateUrlFilters({ unassigned: false }) }} disabled={filterOptionsLoading}><option value="">전체 담당자</option>{assignees.map((assignee) => <option key={assignee.id} value={assignee.id}>{assignee.name}</option>)}</select></label>}
          {!assignedOnly && <label className="form-field"><span>배정 여부</span><select value={unassigned ? 'true' : ''} onChange={(event) => { startFilterChange(); const nextUnassigned = event.target.value === 'true'; updateUrlFilters({ unassigned: nextUnassigned }); if (nextUnassigned) setAssigneeId('') }}><option value="">전체</option><option value="true">미배정만</option></select></label>}
          {user?.role === 'agent' && <label className="form-field"><span>요청자</span><select value={requesterId} onChange={(event) => { startFilterChange(); setRequesterId(event.target.value) }} disabled={filterOptionsLoading}><option value="">전체 요청자</option>{filterOptions?.requesters.map((requester) => <option key={requester.id} value={requester.id}>{requester.name}</option>)}</select></label>}
          {user?.role === 'agent' && <label className="form-field"><span>팀</span><select value={teamId} onChange={(event) => { startFilterChange(); setTeamId(event.target.value) }} disabled={filterOptionsLoading}><option value="">전체 팀</option>{filterOptions?.teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>}
          {user?.role === 'agent' && <label className="form-field"><span>티켓 태그</span><select value={tagId} onChange={(event) => { startFilterChange(); setTagId(event.target.value) }} disabled={filterOptionsLoading}><option value="">전체 태그</option>{filterOptions?.tags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}</select></label>}
        </div>}
        {advancedOpen && filterOptionsLoading && <p className="advanced-filter-status">상세 필터 선택 항목을 불러오는 중입니다.</p>}
        {advancedOpen && filterOptionsError && <div className="detail-load-error" role="alert"><span>{filterOptionsError}</span><button className="button button--secondary" type="button" onClick={() => { setFilterOptionsLoading(true); setFilterOptionsError(''); setFilterOptionsRetryKey((value) => value + 1) }}>선택 항목 다시 시도</button></div>}
      </section>

      {stagesError && <div className="form-error" role="alert">{stagesError} <button className="button button--secondary" type="button" onClick={() => { setStagesLoading(true); setStagesError(''); setStagesRetryKey((value) => value + 1) }}>상태 목록 다시 시도</button></div>}

      <section className="card tickets-card">
        {loading ? <PageLoader label={archivedOnly ? '보관된 문의를 불러오는 중입니다.' : '문의 목록을 불러오는 중입니다.'} /> : error ? <ErrorState message={error} onRetry={() => { setLoading(true); setError(''); setRetryKey((value) => value + 1) }} /> : !data || data.tickets.length === 0 ? <EmptyState message={archivedOnly ? '조건에 맞는 보관 문의가 없습니다.' : '조건에 맞는 문의가 없습니다.'} /> : (
          <>
            <div className="table-wrap">
              <table><thead><tr><th>문의 번호</th><th>제목</th><th>유형</th><th>요청자</th><th>담당자</th><th>상태</th><th>긴급도</th><th>등록일</th></tr></thead>
                <tbody>{data.tickets.map((ticket) => <tr className="clickable-row" key={ticket.id} tabIndex={0} onClick={() => navigate(`/tickets/${ticket.id}`)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') navigate(`/tickets/${ticket.id}`) }}><td className="reference">{ticket.reference || `#${ticket.id}`}</td><td className="title-cell"><Link to={`/tickets/${ticket.id}`} onClick={(event) => event.stopPropagation()}><strong>{ticket.title}</strong></Link><span>{ticket.description || '내용 없음'}</span></td><td>{ticket.category?.name ?? '-'}</td><td>{ticket.requester?.name ?? '-'}</td><td>{ticket.assignee?.name ?? <span className="muted">미배정</span>}</td><td><span className="status-badge">{stageLabel(ticket.status?.name)}</span></td><td><span className={`priority-badge priority-badge--${ticket.priority_code}`}>{ticket.priority}</span></td><td>{formatDate(ticket.created_at)}</td></tr>)}</tbody>
              </table>
            </div>
            <div className="pagination"><span>{data.total_pages === 0 ? 0 : data.page} / {data.total_pages} 페이지</span><div><button className="icon-button" type="button" onClick={() => { setLoading(true); setError(''); setPage((value) => Math.max(1, value - 1)) }} disabled={data.page <= 1} aria-label="이전 페이지"><ChevronLeft size={19} /></button><button className="icon-button" type="button" onClick={() => { setLoading(true); setError(''); setPage((value) => value + 1) }} disabled={!data.has_next} aria-label="다음 페이지"><ChevronRight size={19} /></button></div></div>
          </>
        )}
      </section>
    </div>
  )
}
