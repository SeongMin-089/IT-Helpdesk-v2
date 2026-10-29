import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Archive, ArchiveRestore, ArrowLeft, CircleCheckBig, FilePlus2, Pencil, RefreshCcw, Save } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { ErrorState, PageLoader } from '../components/common/PageState'
import { TicketActivitySections } from '../components/tickets/TicketActivitySections'
import { useAuth } from '../contexts/AuthContext'
import { ApiError, apiRequest } from '../services/api'
import { formatDate, stageLabel } from '../services/format'
import type {
  AssigneeListResponse,
  Relation,
  Stage,
  StageListResponse,
  TicketFaqDraftResponse,
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

function transitionRequestError(error: unknown) {
  if (!(error instanceof ApiError)) return '문의 상태를 변경하지 못했습니다.'
  if (error.status === 401) return '로그인 상태를 다시 확인해 주세요.'
  if (error.status === 403) return '이 상태 변경을 수행할 권한이 없습니다.'
  if (error.status === 404) return '상태를 변경할 문의를 찾을 수 없습니다.'
  if (error.status === 409 || error.status === 422) return error.message
  if (error.status >= 500) return '서버 오류로 상태를 변경하지 못했습니다. 기존 문의 정보는 유지됩니다.'
  return error.message
}

function archiveRequestError(error: unknown, action: '보관' | '복원') {
  if (!(error instanceof ApiError)) return `문의를 ${action}하지 못했습니다.`
  if (error.status === 401) return '로그인 상태를 다시 확인해 주세요.'
  if (error.status === 403) return `이 문의를 ${action}할 권한이 없습니다.`
  if (error.status === 404) return '문의 정보를 찾을 수 없습니다.'
  if (error.status === 409 || error.status === 422) return error.message
  if (error.status >= 500) return `서버 오류로 문의를 ${action}하지 못했습니다. 기존 문의 정보는 유지됩니다.`
  return error.message
}

function faqDraftRequestError(error: unknown) {
  if (!(error instanceof ApiError)) return 'FAQ 초안을 생성하지 못했습니다.'
  if (error.status === 401) return '로그인 상태를 다시 확인해 주세요.'
  if (error.status === 403 || error.status === 409 || error.status === 422) return error.message
  if (error.status === 404) return '문의를 찾을 수 없습니다.'
  if (error.status >= 500) return '서버 오류로 FAQ 초안을 생성하지 못했습니다.'
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
  const activeTicketIdRef = useRef(numericId)

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
  const originalSavingRef = useRef<symbol | null>(null)

  const [managementPriority, setManagementPriority] = useState<string | undefined>()
  const [managementAssigneeId, setManagementAssigneeId] = useState<string | undefined>()
  const [managementError, setManagementError] = useState('')
  const [managementSaving, setManagementSaving] = useState(false)
  const managementSavingRef = useRef<symbol | null>(null)

  const [transitionMode, setTransitionMode] = useState<'resolve' | 'reprocess' | null>(null)
  const [resolution, setResolution] = useState('')
  const [reprocessReason, setReprocessReason] = useState('')
  const [confirmingClose, setConfirmingClose] = useState(false)
  const [transitionError, setTransitionError] = useState('')
  const [transitionSaving, setTransitionSaving] = useState(false)
  const transitionSavingRef = useRef<symbol | null>(null)

  const [confirmingArchive, setConfirmingArchive] = useState(false)
  const [archiveSaving, setArchiveSaving] = useState(false)
  const [archiveError, setArchiveError] = useState('')
  const archiveSavingRef = useRef<symbol | null>(null)

  const [confirmingFaqDraft, setConfirmingFaqDraft] = useState(false)
  const [faqDraftSaving, setFaqDraftSaving] = useState(false)
  const [faqDraftError, setFaqDraftError] = useState('')
  const [createdFaqDraft, setCreatedFaqDraft] = useState<TicketFaqDraftResponse['faq'] | null>(null)
  const faqDraftSavingRef = useRef<symbol | null>(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    activeTicketIdRef.current = numericId
  }, [numericId])

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
          originalSavingRef.current = null
          managementSavingRef.current = null
          transitionSavingRef.current = null
          archiveSavingRef.current = null
          faqDraftSavingRef.current = null
          setOriginalSaving(false)
          setManagementSaving(false)
          setTransitionSaving(false)
          setTransitionMode(null)
          setResolution('')
          setReprocessReason('')
          setConfirmingClose(false)
          setTransitionError('')
          setConfirmingArchive(false)
          setArchiveSaving(false)
          setArchiveError('')
          setConfirmingFaqDraft(false)
          setFaqDraftSaving(false)
          setFaqDraftError('')
          setCreatedFaqDraft(null)
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

  const workflow = useMemo(() => {
    const sortedStages = [...stages]
      .sort((left, right) => left.sequence - right.sequence || left.id - right.id)
    const valid = sortedStages.length === 5
      && sortedStages.slice(0, 4).every((stage) => !stage.closed)
      && sortedStages[4]?.closed === true
    return {
      stages: sortedStages,
      error: valid ? '' : '활성 문의 단계가 5단계 업무 흐름과 일치하지 않습니다.',
    }
  }, [stages])

  const currentResult = result?.id === numericId ? result : null
  const error = validId ? currentResult?.error : '올바르지 않은 문의 번호입니다.'
  if (error) return <div className="page-stack"><Link className="button button--secondary back-button" to="/tickets"><ArrowLeft size={17} />목록으로</Link><section className="card"><ErrorState message={error} onRetry={validId ? () => { setResult(null); setRetryKey((value) => value + 1) } : undefined} /></section></div>
  if (!currentResult?.data) return <PageLoader label="문의 상세 정보를 불러오는 중입니다." />

  const { ticket } = currentResult.data
  const isOwner = ticket.requester?.id === user?.partner_id
  const workflowPosition = workflow.error || !ticket.status
    ? -1
    : workflow.stages.findIndex((stage) => stage.id === ticket.status?.id)
  const workflowStatusError = stagesError
    || workflow.error
    || (!stagesLoading && workflowPosition < 0 ? '현재 문의 단계가 5단계 업무 흐름에 포함되지 않습니다.' : '')
  const workflowReady = !stagesLoading && !workflowStatusError && workflowPosition >= 0
  const canEditOriginal = Boolean(
    isOwner
    && ticket.active
    && !ticket.closed
    && workflowReady
    && (workflowPosition === 0 || workflowPosition === 1),
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
    if (originalSavingRef.current || managementSavingRef.current || transitionSavingRef.current || archiveSavingRef.current || faqDraftSavingRef.current) return
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

    const requestToken = Symbol('original-save')
    originalSavingRef.current = requestToken
    const requestTicketId = ticket.id
    setOriginalSaving(true)
    setOriginalError('')
    try {
      const response = await apiRequest<TicketUpdateResponse>(`/api/oca/tickets/${ticket.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      if (!mountedRef.current || activeTicketIdRef.current !== requestTicketId || originalSavingRef.current !== requestToken) return
      setResult({ id: numericId, data: { success: true, ticket: response.ticket } })
      setEditingOriginal(false)
      setEditTitle('')
      setEditDescription('')
    } catch (caught) {
      if (mountedRef.current && activeTicketIdRef.current === requestTicketId && originalSavingRef.current === requestToken) setOriginalError(updateError(caught))
    } finally {
      if (originalSavingRef.current === requestToken) {
        originalSavingRef.current = null
        if (mountedRef.current && activeTicketIdRef.current === requestTicketId) setOriginalSaving(false)
      }
    }
  }

  const saveManagement = async (event: FormEvent) => {
    event.preventDefault()
    if (managementSavingRef.current || originalSavingRef.current || transitionSavingRef.current || archiveSavingRef.current || faqDraftSavingRef.current || managementReadOnly) return
    const nextAssigneeId = selectedAssigneeId ? Number(selectedAssigneeId) : null
    const payload: { priority?: string; assignee_id?: number | null } = {}
    if (selectedPriority !== ticket.priority_code) payload.priority = selectedPriority
    if (nextAssigneeId !== (ticket.assignee?.id ?? null)) payload.assignee_id = nextAssigneeId
    if (Object.keys(payload).length === 0) {
      setManagementError('변경된 내용이 없습니다.')
      return
    }

    const requestToken = Symbol('management-save')
    managementSavingRef.current = requestToken
    const requestTicketId = ticket.id
    setManagementSaving(true)
    setManagementError('')
    try {
      const response = await apiRequest<TicketUpdateResponse>(`/api/oca/tickets/${ticket.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      if (!mountedRef.current || activeTicketIdRef.current !== requestTicketId || managementSavingRef.current !== requestToken) return
      setResult({ id: numericId, data: { success: true, ticket: response.ticket } })
      setManagementPriority(undefined)
      setManagementAssigneeId(undefined)
    } catch (caught) {
      if (mountedRef.current && activeTicketIdRef.current === requestTicketId && managementSavingRef.current === requestToken) setManagementError(updateError(caught))
    } finally {
      if (managementSavingRef.current === requestToken) {
        managementSavingRef.current = null
        if (mountedRef.current && activeTicketIdRef.current === requestTicketId) setManagementSaving(false)
      }
    }
  }

  const performTransition = async (path: string, body?: Record<string, unknown>) => {
    if (
      transitionSavingRef.current
      || originalSavingRef.current
      || managementSavingRef.current
      || archiveSavingRef.current
      || faqDraftSavingRef.current
      || !workflowReady
      || !ticket.active
      || ticket.closed
    ) return

    const requestTicketId = ticket.id
    const requestToken = Symbol('transition-save')
    transitionSavingRef.current = requestToken
    setTransitionSaving(true)
    setTransitionError('')
    try {
      const response = await apiRequest<TicketUpdateResponse>(`/api/oca/tickets/${requestTicketId}${path}`, {
        method: path === '/stage' ? 'PATCH' : 'POST',
        ...(body ? { body: JSON.stringify(body) } : {}),
      })
      if (!mountedRef.current || activeTicketIdRef.current !== requestTicketId || transitionSavingRef.current !== requestToken) return
      setResult({ id: requestTicketId, data: { success: true, ticket: response.ticket } })
      setTransitionMode(null)
      setResolution('')
      setReprocessReason('')
      setConfirmingClose(false)
      setEditingOriginal(false)
      setEditTitle('')
      setEditDescription('')
      setOriginalError('')
      setManagementPriority(undefined)
      setManagementAssigneeId(undefined)
      setManagementError('')
    } catch (caught) {
      if (mountedRef.current && activeTicketIdRef.current === requestTicketId && transitionSavingRef.current === requestToken) {
        setTransitionError(transitionRequestError(caught))
      }
    } finally {
      if (transitionSavingRef.current === requestToken) {
        transitionSavingRef.current = null
        if (mountedRef.current && activeTicketIdRef.current === requestTicketId) setTransitionSaving(false)
      }
    }
  }

  const submitResolution = (event: FormEvent) => {
    event.preventDefault()
    const normalized = resolution.trim()
    if (!normalized) {
      setTransitionError('해결 내용을 입력해 주세요.')
      return
    }
    if (normalized.length > 10000) {
      setTransitionError('해결 내용은 최대 10,000자까지 입력할 수 있습니다.')
      return
    }
    void performTransition('/resolve', { resolution: normalized })
  }

  const submitReprocess = (event: FormEvent) => {
    event.preventDefault()
    const normalized = reprocessReason.trim()
    if (!normalized) {
      setTransitionError('재처리 사유를 입력해 주세요.')
      return
    }
    if (normalized.length > 10000) {
      setTransitionError('재처리 사유는 최대 10,000자까지 입력할 수 있습니다.')
      return
    }
    void performTransition('/reprocess', { reason: normalized })
  }

  const performArchiveAction = async (action: 'archive' | 'restore') => {
    if (
      archiveSavingRef.current
      || originalSavingRef.current
      || managementSavingRef.current
      || transitionSavingRef.current
      || faqDraftSavingRef.current
    ) return
    const requestTicketId = ticket.id
    const requestToken = Symbol(`ticket-${action}`)
    archiveSavingRef.current = requestToken
    setArchiveSaving(true)
    setArchiveError('')
    try {
      const response = await apiRequest<TicketUpdateResponse>(`/api/oca/tickets/${requestTicketId}/${action}`, { method: 'PATCH' })
      if (!mountedRef.current || activeTicketIdRef.current !== requestTicketId || archiveSavingRef.current !== requestToken) return
      setResult({ id: requestTicketId, data: { success: true, ticket: response.ticket } })
      setConfirmingArchive(false)
      setConfirmingFaqDraft(false)
      setEditingOriginal(false)
      setEditTitle('')
      setEditDescription('')
      setTransitionMode(null)
      setConfirmingClose(false)
      setManagementPriority(undefined)
      setManagementAssigneeId(undefined)
      setOriginalError('')
      setManagementError('')
      setTransitionError('')
    } catch (caught) {
      if (mountedRef.current && activeTicketIdRef.current === requestTicketId && archiveSavingRef.current === requestToken) {
        setArchiveError(archiveRequestError(caught, action === 'archive' ? '보관' : '복원'))
      }
    } finally {
      if (archiveSavingRef.current === requestToken) {
        archiveSavingRef.current = null
        if (mountedRef.current && activeTicketIdRef.current === requestTicketId) setArchiveSaving(false)
      }
    }
  }

  const createFaqDraft = async () => {
    if (
      faqDraftSavingRef.current
      || originalSavingRef.current
      || managementSavingRef.current
      || transitionSavingRef.current
      || archiveSavingRef.current
      || createdFaqDraft
    ) return
    const requestTicketId = ticket.id
    const requestToken = Symbol('ticket-faq-draft')
    faqDraftSavingRef.current = requestToken
    setFaqDraftSaving(true)
    setFaqDraftError('')
    try {
      const response = await apiRequest<TicketFaqDraftResponse>(`/api/oca/tickets/${requestTicketId}/faq-drafts`, { method: 'POST' })
      if (!mountedRef.current || activeTicketIdRef.current !== requestTicketId || faqDraftSavingRef.current !== requestToken) return
      setCreatedFaqDraft(response.faq)
      setConfirmingFaqDraft(false)
    } catch (caught) {
      if (mountedRef.current && activeTicketIdRef.current === requestTicketId && faqDraftSavingRef.current === requestToken) {
        setFaqDraftError(faqDraftRequestError(caught))
      }
    } finally {
      if (faqDraftSavingRef.current === requestToken) {
        faqDraftSavingRef.current = null
        if (mountedRef.current && activeTicketIdRef.current === requestTicketId) setFaqDraftSaving(false)
      }
    }
  }

  const transitionControlsDisabled = transitionSaving || originalSaving || managementSaving || archiveSaving || faqDraftSaving || editingOriginal
  const canUseTransitions = workflowReady && ticket.active && !ticket.closed
  const hasAvailableTransition = (
    user?.role === 'agent' && workflowPosition >= 0 && workflowPosition <= 2
  ) || (isOwner && workflowPosition === 3)
  const canArchiveOrRestore = user?.role === 'agent'
    || Boolean(isOwner && workflowReady && (workflowPosition === 0 || workflowPosition === 1))
  const listPath = ticket.active ? '/tickets' : '/archived'
  const canCreateFaqDraft = user?.role === 'agent' && ticket.active && workflowReady && (workflowPosition === 3 || workflowPosition === 4)

  return (
    <div className="page-stack">
      <header className="page-heading page-heading--inline">
        <div><p className="eyebrow">TICKET DETAIL</p><h1>{ticket.title}</h1><p className="detail-reference">{ticket.reference || `#${ticket.id}`}</p></div>
        <div className="detail-header-actions">
          {canArchiveOrRestore && (ticket.active ? <button className="button button--secondary" type="button" onClick={() => { setConfirmingArchive(true); setArchiveError('') }} disabled={archiveSaving || originalSaving || managementSaving || transitionSaving || faqDraftSaving || editingOriginal}><Archive size={17} />보관</button> : <button className="button button--primary" type="button" onClick={() => void performArchiveAction('restore')} disabled={archiveSaving || originalSaving || managementSaving || transitionSaving || faqDraftSaving}><ArchiveRestore size={17} />{archiveSaving ? '복원 중...' : '복원'}</button>)}
          <Link className="button button--secondary" to={listPath}><ArrowLeft size={17} />{ticket.active ? '목록으로' : '보관함으로'}</Link>
        </div>
      </header>

      {confirmingArchive && ticket.active && <div className="workflow-confirm archive-confirm" role="alert"><p>문의를 보관하면 수정과 상태 변경, 댓글·첨부파일 작성이 제한됩니다. 보관하시겠습니까?</p><div><button className="button button--secondary" type="button" onClick={() => { setConfirmingArchive(false); setArchiveError('') }} disabled={archiveSaving}>취소</button><button className="button button--primary" type="button" onClick={() => void performArchiveAction('archive')} disabled={archiveSaving}>{archiveSaving ? '보관 중...' : '보관 확인'}</button></div></div>}
      {archiveError && <div className="form-error detail-form-error" role="alert">{archiveError}</div>}

      <section className="card workflow-card">
        <div className="workflow-card__heading"><div><h2>업무 진행 상태</h2><p>현재 상태와 처리 단계를 확인합니다.</p></div><span className="status-badge">{stageLabel(ticket.status?.name)}</span></div>
        {stagesLoading ? <div className="workflow-message"><span className="spinner" /><p>5단계 업무 흐름을 확인하는 중입니다.</p></div> : workflowStatusError ? (
          <div className="workflow-error" role="alert"><span>{workflowStatusError}</span><button className="button button--secondary" type="button" onClick={() => { setStagesLoading(true); setStagesError(''); setStagesRetryKey((value) => value + 1) }}><RefreshCcw size={15} />다시 시도</button></div>
        ) : (
          <>
            <ol className="workflow-progress" aria-label="문의 처리 단계">
              {workflow.stages.map((stage, index) => <li className={index < workflowPosition ? 'is-complete' : index === workflowPosition ? 'is-current' : ''} key={stage.id}><span>{index + 1}</span><strong>{stageLabel(stage.name)}</strong></li>)}
            </ol>

            {canUseTransitions && hasAvailableTransition && <div className="workflow-actions">
              {user?.role === 'agent' && workflowPosition === 0 && <button className="button button--primary" type="button" onClick={() => void performTransition('/stage', { stage_id: workflow.stages[1].id })} disabled={transitionControlsDisabled}>{transitionSaving ? '변경 중...' : '배정 단계로 변경'}</button>}
              {user?.role === 'agent' && workflowPosition === 1 && <button className="button button--primary" type="button" onClick={() => void performTransition('/stage', { stage_id: workflow.stages[2].id })} disabled={transitionControlsDisabled}>{transitionSaving ? '변경 중...' : '처리 시작'}</button>}
              {user?.role === 'agent' && workflowPosition === 2 && transitionMode !== 'resolve' && <button className="button button--primary" type="button" onClick={() => { setTransitionMode('resolve'); setConfirmingClose(false); setTransitionError('') }} disabled={transitionControlsDisabled}>해결 처리</button>}
              {isOwner && workflowPosition === 3 && transitionMode !== 'reprocess' && !confirmingClose && <><button className="button button--primary" type="button" onClick={() => { setConfirmingClose(true); setTransitionMode(null); setTransitionError('') }} disabled={transitionControlsDisabled}>문의 종료</button><button className="button button--secondary" type="button" onClick={() => { setTransitionMode('reprocess'); setConfirmingClose(false); setTransitionError('') }} disabled={transitionControlsDisabled}>재처리 요청</button></>}

              {transitionMode === 'resolve' && user?.role === 'agent' && workflowPosition === 2 && <form className="workflow-action-form" onSubmit={submitResolution} noValidate><label className="form-field"><span>해결 내용 <strong>*</strong></span><textarea value={resolution} onChange={(event) => { setResolution(event.target.value); setTransitionError('') }} maxLength={10000} rows={5} disabled={transitionSaving} /><small>{resolution.length.toLocaleString()} / 10,000</small></label><div className="detail-actions"><button className="button button--secondary" type="button" onClick={() => { setTransitionMode(null); setResolution(''); setTransitionError('') }} disabled={transitionSaving}>취소</button><button className="button button--primary" type="submit" disabled={transitionSaving}>{transitionSaving ? '처리 중...' : '해결 저장'}</button></div></form>}
              {transitionMode === 'reprocess' && isOwner && workflowPosition === 3 && <form className="workflow-action-form" onSubmit={submitReprocess} noValidate><label className="form-field"><span>재처리 사유 <strong>*</strong></span><textarea value={reprocessReason} onChange={(event) => { setReprocessReason(event.target.value); setTransitionError('') }} maxLength={10000} rows={5} disabled={transitionSaving} /><small>{reprocessReason.length.toLocaleString()} / 10,000</small></label><div className="detail-actions"><button className="button button--secondary" type="button" onClick={() => { setTransitionMode(null); setReprocessReason(''); setTransitionError('') }} disabled={transitionSaving}>취소</button><button className="button button--primary" type="submit" disabled={transitionSaving}>{transitionSaving ? '요청 중...' : '재처리 요청'}</button></div></form>}
              {confirmingClose && isOwner && workflowPosition === 3 && <div className="workflow-confirm" role="alert"><p>문의를 종료하면 추가 상태 변경을 할 수 없습니다. 종료하시겠습니까?</p><div><button className="button button--secondary" type="button" onClick={() => { setConfirmingClose(false); setTransitionError('') }} disabled={transitionSaving}>취소</button><button className="button button--primary" type="button" onClick={() => void performTransition('/close')} disabled={transitionSaving}>{transitionSaving ? '종료 중...' : '종료 확인'}</button></div></div>}
            </div>}
            {transitionError && <div className="form-error workflow-action-error" role="alert">{transitionError}</div>}
          </>
        )}
      </section>

      {user && <TicketActivitySections
        key={ticket.id}
        ticket={ticket}
        user={user}
        refreshKey={`${ticket.updated_at ?? ''}:${ticket.status?.id ?? ''}:${ticket.assignee?.id ?? ''}:${ticket.active}`}
        mainContent={<article className="card detail-main">
          <div className="detail-section">
            <div className="detail-section__heading"><h2>문의 내용</h2>{canEditOriginal && !editingOriginal && <button className="button button--secondary" type="button" onClick={startOriginalEdit} disabled={managementSaving || transitionSaving || archiveSaving || faqDraftSaving}><Pencil size={16} />수정</button>}</div>
            {editingOriginal ? (
              <form className="detail-edit-form" onSubmit={saveOriginal} noValidate>
                <label className="form-field"><span>제목 <strong>*</strong></span><input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} maxLength={200} required disabled={originalSaving} /><small>{editTitle.length} / 200</small></label>
                <label className="form-field"><span>내용 <strong>*</strong></span><textarea value={editDescription} onChange={(event) => setEditDescription(event.target.value)} maxLength={10000} required disabled={originalSaving} rows={10} /><small>{editDescription.length.toLocaleString()} / 10,000</small></label>
                {originalError && <div className="form-error detail-form-error" role="alert">{originalError}</div>}
                <div className="detail-actions"><button className="button button--secondary" type="button" onClick={cancelOriginalEdit} disabled={originalSaving}>취소</button><button className="button button--primary" type="submit" disabled={originalSaving}><Save size={16} />{originalSaving ? '저장 중...' : '저장'}</button></div>
              </form>
            ) : <p className="ticket-description">{ticket.description || '등록된 내용이 없습니다.'}</p>}
          </div>
        </article>}
        sidebarContent={<>
          <aside className="card detail-sidebar">
            <div className="detail-badges"><span className="status-badge">{stageLabel(ticket.status?.name)}</span><span className={`priority-badge priority-badge--${ticket.priority_code}`}>{ticket.priority}</span>{!ticket.active && <span className="state-badge state-badge--archived"><Archive size={13} />보관됨</span>}{ticket.closed && <span className="state-badge state-badge--closed"><CircleCheckBig size={13} />종료됨</span>}</div>
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
              <label className="form-field"><span>긴급도</span><select value={selectedPriority} onChange={(event) => { setManagementPriority(event.target.value); setManagementError('') }} disabled={managementReadOnly || managementSaving || transitionSaving || archiveSaving || faqDraftSaving}>{priorityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
              <label className="form-field"><span>담당자</span><select value={selectedAssigneeId} onChange={(event) => { setManagementAssigneeId(event.target.value); setManagementError('') }} disabled={managementReadOnly || managementSaving || transitionSaving || archiveSaving || faqDraftSaving || assigneesLoading || Boolean(assigneesError)}><option value="">미배정</option>{currentAssigneeMissing && ticket.assignee && <option value={ticket.assignee.id}>{ticket.assignee.name} (현재 담당자)</option>}{assignees.map((assignee) => <option key={assignee.id} value={assignee.id}>{assignee.name}</option>)}</select></label>
              {assigneesLoading && <p className="detail-helper">담당자 목록을 불러오는 중입니다.</p>}
              {assigneesError && <div className="detail-load-error" role="alert"><span>{assigneesError}</span><button className="button button--secondary" type="button" onClick={() => { setAssigneesLoading(true); setAssigneesError(''); setAssigneesRetryKey((value) => value + 1) }}>다시 시도</button></div>}
              {managementError && <div className="form-error detail-form-error" role="alert">{managementError}</div>}
              <button className="button button--primary" type="submit" disabled={managementReadOnly || managementSaving || originalSaving || transitionSaving || archiveSaving || faqDraftSaving}><Save size={16} />{managementSaving ? '저장 중...' : '관리 정보 저장'}</button>
            </form>
          </section>}

          {canCreateFaqDraft && <section className="card detail-management faq-ticket-card">
            <div className="detail-management__heading"><h2>FAQ 초안</h2><p>문의 해결 내용을 비공개 FAQ 초안으로 생성합니다.</p></div>
            <div className="faq-ticket-card__body">
              {createdFaqDraft ? <div className="faq-draft-success"><strong>{createdFaqDraft.name}</strong><span>비공개 초안이 생성되었습니다. 검토 후 공개해 주세요.</span><Link className="button button--primary" to={`/faq-admin?faq=${createdFaqDraft.id}`}>FAQ 관리로 이동</Link></div> : <button className="button button--secondary" type="button" onClick={() => { setConfirmingFaqDraft(true); setFaqDraftError('') }} disabled={faqDraftSaving || originalSaving || managementSaving || transitionSaving || archiveSaving}><FilePlus2 size={16} />FAQ 초안 생성</button>}
              {confirmingFaqDraft && !createdFaqDraft && <div className="workflow-confirm faq-confirm" role="alert"><p>이 문의의 해결 내용으로 비공개 FAQ 초안을 생성하시겠습니까?</p><div><button className="button button--secondary" type="button" onClick={() => { setConfirmingFaqDraft(false); setFaqDraftError('') }} disabled={faqDraftSaving}>취소</button><button className="button button--primary" type="button" onClick={() => void createFaqDraft()} disabled={faqDraftSaving}>{faqDraftSaving ? '생성 중...' : '생성 확인'}</button></div></div>}
              {faqDraftError && <div className="form-error detail-form-error" role="alert">{faqDraftError}</div>}
            </div>
          </section>}
        </>}
      />}
    </div>
  )
}
