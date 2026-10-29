import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Archive, CircleCheckBig } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { ErrorState, PageLoader } from '../components/common/PageState'
import { ApiError, apiRequest } from '../services/api'
import { formatDate } from '../services/format'
import type { TicketDetailResponse } from '../types/api'

function detailError(error: unknown) {
  if (!(error instanceof ApiError)) return '문의 상세 정보를 불러오지 못했습니다.'
  if (error.status === 400) return '올바르지 않은 문의 번호입니다.'
  if (error.status === 403) return '이 문의를 조회할 권한이 없습니다.'
  if (error.status === 404) return '요청한 문의를 찾을 수 없습니다.'
  if (error.status >= 500) return '서버 오류로 문의를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'
  return error.message
}

export function TicketDetailPage() {
  const { ticketId } = useParams()
  const numericId = Number(ticketId)
  const validId = Number.isInteger(numericId) && numericId > 0
  const [result, setResult] = useState<{ id: number; data?: TicketDetailResponse; error?: string } | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const requestIdRef = useRef(0)

  useEffect(() => {
    if (!validId) return
    const controller = new AbortController()
    const requestId = ++requestIdRef.current
    void apiRequest<TicketDetailResponse>(`/api/oca/tickets/${numericId}`, { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setResult({ id: numericId, data: response })
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

  const currentResult = result?.id === numericId ? result : null
  const error = validId ? currentResult?.error : '올바르지 않은 문의 번호입니다.'
  if (error) return <div className="page-stack"><Link className="button button--secondary back-button" to="/tickets"><ArrowLeft size={17} />목록으로</Link><section className="card"><ErrorState message={error} onRetry={validId ? () => { setResult(null); setRetryKey((value) => value + 1) } : undefined} /></section></div>
  if (!currentResult?.data) return <PageLoader label="문의 상세 정보를 불러오는 중입니다." />

  const { ticket } = currentResult.data
  return (
    <div className="page-stack">
      <header className="page-heading page-heading--inline">
        <div><p className="eyebrow">TICKET DETAIL</p><h1>{ticket.title}</h1><p className="detail-reference">{ticket.reference || `#${ticket.id}`}</p></div>
        <Link className="button button--secondary" to="/tickets"><ArrowLeft size={17} />목록으로</Link>
      </header>

      <section className="detail-grid">
        <article className="card detail-main">
          <div className="detail-section"><h2>문의 내용</h2><p className="ticket-description">{ticket.description || '등록된 내용이 없습니다.'}</p></div>
        </article>
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
      </section>
    </div>
  )
}
