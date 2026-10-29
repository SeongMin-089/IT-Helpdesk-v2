import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, Archive, CircleCheckBig, Pencil, Save } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { ErrorState, PageLoader } from '../components/common/PageState'
import { useAuth } from '../contexts/AuthContext'
import { ApiError, apiRequest } from '../services/api'
import { formatDate } from '../services/format'
import type {
  AssigneeListResponse,
  Relation,
  Stage,
  StageListResponse,
  TicketDetailResponse,
  TicketUpdateResponse,
} from '../types/api'

const priorityOptions = [
  { value: '0', label: '낮음' },
  { value: '1', label: '보통' },
  { value: '2', label: '높음' },
  { value: '3', label: '긴급' },
]

function detailError(error: unknown) {
  if (!(error instanceof ApiError)) return '문의 상세 정보를 불러오지 못했습니다.'
  if (error.status === 400) return '올바르지 않은 문의 번호입니다.'
  if (error.status === 403) return '이 문의를 조회할 권한이 없습니다.'
  if (error.status === 404) return '요청한 문의를 찾을 수 없습니다.'
  if (error.status >= 500) return '서버 오류로 문의를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'
  return error.message
}

function updateError(error: unknown) {
  if (!(error instanceof ApiError)) return '변경 내용을 저장하지 못했습니다.'
  if (error.status === 403) return '이 문의를 수정할 권한이 없습니다.'
  if (error.status === 404) return '수정할 문의를 찾을 수 없습니다.'
  if (error.status === 409 || error.status === 422) return error.message
  if (error.status >= 500) return '서버 오류로 저장하지 못했습니다. 기존 문의 정보는 유지됩니다.'
  return error.message
}

export function TicketDetailPage() {
  const { user } = useAuth()
  const { ticketId } = useParams()
  const numericId = Number(ticketId)
  const validId = Number.isInteger(numericId) && numericId > 0
  const [result, setResult] = useState<{ id: number; data?: TicketDetailResponse; error?: string } | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const requestIdRef = useRef(0)
  const mountedRef = useRef(true)

  const [stages, setStages] = useState<Stage[]>([])
  const [stagesLoading, setStagesLoading] = useState(true)
  const [stagesError, setStagesError] = useState('')
  const [stagesRetryKey, setStagesRetryKey] = useState(0)

  const [assignees, setAssignees] = useState<Relation[]>([])
  const [assigneesLoading, setAssigneesLoading] = useState(user?.role === 'agent')
  const [assigneesError, setAssigneesError] = useState('')
  const [assigneesRetryKey, setAssigneesRetryKey] = useState(0)

  const [editingOriginal, setEditingOriginal] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [originalError, setOriginalError] = useState('')
  const [originalSaving, setOriginalSaving] = useState(false)
  const originalSavingRef = useRef(false)

  const [managementPriority, setManagementPriority] = useState<string | undefined>()
  const [managementAssigneeId, setManagementAssigneeId] = useState<string | undefined>()
  const [managementError, setManagementError] = useState('')
  const [managementSaving, setManagementSaving] = useState(false)
  const managementSavingRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    if (!validId) return
    const controller = new AbortController()
    const requestId = ++requestIdRef.current
    void apiRequest<TicketDetailResponse>(`/api/oca/tickets/${numericId}`, { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) {
          setResult({ id: numericId, data: response })
          setEditingOriginal(false)
          setEditTitle('')
          setEditDescription('')
          setOriginalError('')
          setManagementPriority(undefined)
          setManagementAssigneeId(undefined)
          setManagementError('')
        }
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setResult({ id: numericId, error: detailError(caught) })
      })
    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [numericId, retryKey, validId])

  useEffect(() => {
    const controller = new AbortController()
    void apiRequest<StageListResponse>('/api/oca/stages', { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) setStages(response.stages)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setStagesError(caught instanceof ApiError ? caught.message : '수정 가능 단계를 확인하지 못했습니다.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setStagesLoading(false)
      })
    return () => controller.abort()
  }, [stagesRetryKey])

  useEffect(() => {
    if (user?.role !== 'agent') return
    const controller = new AbortController()
    void apiRequest<AssigneeListResponse>('/api/oca/assignees', { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) setAssignees(response.assignees)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setAssigneesError(caught instanceof ApiError ? caught.message : '담당자 목록을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setAssigneesLoading(false)
      })
    return () => controller.abort()
  }, [assigneesRetryKey, user?.role])

  const editableStageIds = useMemo(
    () => [...stages]
      .sort((left, right) => left.sequence - right.sequence || left.id - right.id)
      .slice(0, 2)
      .map((stage) => stage.id),
    [stages],
  )

  const currentResult = result?.id === numericId ? result : null
  const error = validId ? currentResult?.error : '올바르지 않은 문의 번호입니다.'
  if (error) return <div className="page-stack"><Link className="button button--secondary back-button" to="/tickets"><ArrowLeft size={17} />목록으로</Link><section className="card"><ErrorState message={error} onRetry={validId ? () => { setResult(null); setRetryKey((value) => value + 1) } : undefined} /></section></div>
  if (!currentResult?.data) return <PageLoader label="문의 상세 정보를 불러오는 중입니다." />

  const { ticket } = currentResult.data
  const isOwner = ticket.requester?.id === user?.partner_id
  const canEditOriginal = Boolean(
    isOwner
    && ticket.active
    && !ticket.closed
    && editableStageIds.length === 2
    && ticket.status
    && editableStageIds.includes(ticket.status.id),
  )
  const managementReadOnly = !ticket.active || ticket.closed
  const selectedPriority = managementPriority ?? ticket.priority_code
  const selectedAssigneeId = managementAssigneeId ?? (ticket.assignee ? String(ticket.assignee.id) : '')
  const currentAssigneeMissing = Boolean(
    ticket.assignee && !assignees.some((assignee) => assignee.id === ticket.assignee?.id),
  )

  const startOriginalEdit = () => {
    setEditTitle(ticket.title)
    setEditDescription(ticket.description)
    setOriginalError('')
    setEditingOriginal(true)
  }

  const cancelOriginalEdit = () => {
    if (originalSavingRef.current) return
    setEditTitle('')
    setEditDescription('')
    setOriginalError('')
    setEditingOriginal(false)
  }

  const saveOriginal = async (event: FormEvent) => {
    event.preventDefault()
    if (originalSavingRef.current || managementSavingRef.current) return
    const normalizedTitle = editTitle.trim()
    const normalizedDescription = editDescription.trim()
    if (!normalizedTitle) {
      setOriginalError('제목을 입력해 주세요.')
      return
    }
    if (!normalizedDescription) {
      setOriginalError('문의 내용을 입력해 주세요.')
      return
    }
    if (normalizedTitle.length > 200 || normalizedDescription.length > 10000) {
      setOriginalError('제목 또는 문의 내용의 최대 길이를 확인해 주세요.')
      return
    }

    const payload: { title?: string; description?: string } = {}
    if (normalizedTitle !== ticket.title) payload.title = normalizedTitle
    if (normalizedDescription !== ticket.description) payload.description = normalizedDescription
    if (Object.keys(payload).length === 0) {
      setOriginalError('변경된 내용이 없습니다.')
      return
    }

    originalSavingRef.current = true
    setOriginalSaving(true)
    setOriginalError('')
    try {
      const response = await apiRequest<TicketUpdateResponse>(`/api/oca/tickets/${ticket.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      if (!mountedRef.current) return
      setResult({ id: numericId, data: { success: true, ticket: response.ticket } })
      setEditingOriginal(false)
      setEditTitle('')
      setEditDescription('')
    } catch (caught) {
      if (mountedRef.current) setOriginalError(updateError(caught))
    } finally {
      originalSavingRef.current = false
      if (mountedRef.current) setOriginalSaving(false)
    }
  }

  const saveManagement = async (event: FormEvent) => {
    event.preventDefault()
    if (managementSavingRef.current || originalSavingRef.current || managementReadOnly) return
    const nextAssigneeId = selectedAssigneeId ? Number(selectedAssigneeId) : null
    const payload: { priority?: string; assignee_id?: number | null } = {}
    if (selectedPriority !== ticket.priority_code) payload.priority = selectedPriority
    if (nextAssigneeId !== (ticket.assignee?.id ?? null)) payload.assignee_id = nextAssigneeId
    if (Object.keys(payload).length === 0) {
      setManagementError('변경된 내용이 없습니다.')
      return
    }

    managementSavingRef.current = true
    setManagementSaving(true)
    setManagementError('')
    try {
      const response = await apiRequest<TicketUpdateResponse>(`/api/oca/tickets/${ticket.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      if (!mountedRef.current) return
      setResult({ id: numericId, data: { success: true, ticket: response.ticket } })
      setManagementPriority(undefined)
      setManagementAssigneeId(undefined)
    } catch (caught) {
      if (mountedRef.current) setManagementError(updateError(caught))
    } finally {
      managementSavingRef.current = false
      if (mountedRef.current) setManagementSaving(false)
    }
  }

  return (
    <div className="page-stack">
      <header className="page-heading page-heading--inline">
        <div><p className="eyebrow">TICKET DETAIL</p><h1>{ticket.title}</h1><p className="detail-reference">{ticket.reference || `#${ticket.id}`}</p></div>
        <Link className="button button--secondary" to="/tickets"><ArrowLeft size={17} />목록으로</Link>
      </header>

      <section className="detail-grid">
        <article className="card detail-main">
          <div className="detail-section">
            <div className="detail-section__heading"><h2>문의 내용</h2>{canEditOriginal && !editingOriginal && <button className="button button--secondary" type="button" onClick={startOriginalEdit} disabled={managementSaving}><Pencil size={16} />수정</button>}</div>
            {editingOriginal ? (
              <form className="detail-edit-form" onSubmit={saveOriginal} noValidate>
                <label className="form-field"><span>제목 <strong>*</strong></span><input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} maxLength={200} required disabled={originalSaving} /><small>{editTitle.length} / 200</small></label>
                <label className="form-field"><span>내용 <strong>*</strong></span><textarea value={editDescription} onChange={(event) => setEditDescription(event.target.value)} maxLength={10000} required disabled={originalSaving} rows={10} /><small>{editDescription.length.toLocaleString()} / 10,000</small></label>
                {originalError && <div className="form-error detail-form-error" role="alert">{originalError}</div>}
                <div className="detail-actions"><button className="button button--secondary" type="button" onClick={cancelOriginalEdit} disabled={originalSaving}>취소</button><button className="button button--primary" type="submit" disabled={originalSaving}><Save size={16} />{originalSaving ? '저장 중...' : '저장'}</button></div>
              </form>
            ) : <p className="ticket-description">{ticket.description || '등록된 내용이 없습니다.'}</p>}
            {isOwner && ticket.active && !ticket.closed && stagesError && <div className="detail-load-error" role="alert"><span>{stagesError}</span><button className="button button--secondary" type="button" onClick={() => { setStagesLoading(true); setStagesError(''); setStagesRetryKey((value) => value + 1) }}>단계 다시 확인</button></div>}
            {isOwner && ticket.active && !ticket.closed && stagesLoading && <p className="detail-helper">수정 가능 단계를 확인하는 중입니다.</p>}
          </div>
        </article>

        <div className="detail-side-column">
          <aside className="card detail-sidebar">
            <div className="detail-badges"><span className="status-badge">{ticket.status?.name ?? '미지정'}</span><span className={`priority-badge priority-badge--${ticket.priority_code}`}>{ticket.priority}</span>{!ticket.active && <span className="state-badge state-badge--archived"><Archive size={13} />보관됨</span>}{ticket.closed && <span className="state-badge state-badge--closed"><CircleCheckBig size={13} />종료됨</span>}</div>
            <dl className="detail-list">
              <div><dt>문의 유형</dt><dd>{ticket.category?.name ?? '-'}</dd></div>
              <div><dt>요청자</dt><dd>{ticket.requester?.name ?? '-'}</dd></div>
              <div><dt>담당자</dt><dd>{ticket.assignee?.name ?? '미배정'}</dd></div>
              <div><dt>등록일</dt><dd>{formatDate(ticket.created_at)}</dd></div>
              <div><dt>수정일</dt><dd>{formatDate(ticket.updated_at)}</dd></div>
              <div><dt>보관 여부</dt><dd>{ticket.active ? '아니요' : '예'}</dd></div>
              <div><dt>종료 여부</dt><dd>{ticket.closed ? '예' : '아니요'}</dd></div>
            </dl>
          </aside>

          {user?.role === 'agent' && <section className="card detail-management">
            <div className="detail-management__heading"><h2>문의 관리</h2><p>{managementReadOnly ? '종료·보관 문의는 변경할 수 없습니다.' : '긴급도와 담당자를 변경합니다.'}</p></div>
            <form className="detail-management__form" onSubmit={saveManagement}>
              <label className="form-field"><span>긴급도</span><select value={selectedPriority} onChange={(event) => { setManagementPriority(event.target.value); setManagementError('') }} disabled={managementReadOnly || managementSaving}>{priorityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
              <label className="form-field"><span>담당자</span><select value={selectedAssigneeId} onChange={(event) => { setManagementAssigneeId(event.target.value); setManagementError('') }} disabled={managementReadOnly || managementSaving || assigneesLoading || Boolean(assigneesError)}><option value="">미배정</option>{currentAssigneeMissing && ticket.assignee && <option value={ticket.assignee.id}>{ticket.assignee.name} (현재 담당자)</option>}{assignees.map((assignee) => <option key={assignee.id} value={assignee.id}>{assignee.name}</option>)}</select></label>
              {assigneesLoading && <p className="detail-helper">담당자 목록을 불러오는 중입니다.</p>}
              {assigneesError && <div className="detail-load-error" role="alert"><span>{assigneesError}</span><button className="button button--secondary" type="button" onClick={() => { setAssigneesLoading(true); setAssigneesError(''); setAssigneesRetryKey((value) => value + 1) }}>다시 시도</button></div>}
              {managementError && <div className="form-error detail-form-error" role="alert">{managementError}</div>}
              <button className="button button--primary" type="submit" disabled={managementReadOnly || managementSaving || originalSaving}><Save size={16} />{managementSaving ? '저장 중...' : '관리 정보 저장'}</button>
            </form>
          </section>}
        </div>
      </section>
    </div>
  )
}
