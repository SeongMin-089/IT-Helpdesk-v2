import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Tags } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { ErrorState, PageLoader } from '../components/common/PageState'
import { ApiError, apiRequest } from '../services/api'
import { formatDate } from '../services/format'
import type { FaqDetailResponse } from '../types/api'

function faqDetailError(error: unknown) {
  if (!(error instanceof ApiError)) return 'FAQ를 불러오지 못했습니다.'
  if (error.status === 400) return '올바르지 않은 FAQ 번호입니다.'
  if (error.status === 403) return '이 FAQ를 조회할 권한이 없습니다.'
  if (error.status === 404) return '공개된 FAQ를 찾을 수 없습니다.'
  if (error.status >= 500) return '서버 오류로 FAQ를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'
  return error.message
}

export function FaqDetailPage() {
  const { faqId } = useParams()
  const numericId = Number(faqId)
  const validId = Number.isInteger(numericId) && numericId > 0
  const [result, setResult] = useState<{ id: number; data?: FaqDetailResponse; error?: string } | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const requestIdRef = useRef(0)

  useEffect(() => {
    if (!validId) return
    const controller = new AbortController()
    const requestId = ++requestIdRef.current
    void apiRequest<FaqDetailResponse>(`/api/oca/faqs/${numericId}`, { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setResult({ id: numericId, data: response })
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setResult({ id: numericId, error: faqDetailError(caught) })
      })
    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [numericId, retryKey, validId])

  const current = result?.id === numericId ? result : null
  const error = validId ? current?.error : '올바르지 않은 FAQ 번호입니다.'
  if (error) return <div className="page-stack"><Link className="button button--secondary back-button" to="/faqs"><ArrowLeft size={17} />FAQ 목록으로</Link><section className="card"><ErrorState message={error} onRetry={validId ? () => { setResult(null); setRetryKey((value) => value + 1) } : undefined} /></section></div>
  if (!current?.data) return <PageLoader label="FAQ를 불러오는 중입니다." />

  const { faq } = current.data
  return <div className="page-stack">
    <header className="page-heading page-heading--inline"><div><p className="eyebrow">FAQ DETAIL</p><h1>{faq.name}</h1><p>자주 묻는 질문의 해결 방법입니다.</p></div><Link className="button button--secondary" to="/faqs"><ArrowLeft size={17} />FAQ 목록으로</Link></header>
    <article className="card faq-detail-card">
      {faq.tags.length > 0 && <div className="faq-tags"><Tags size={14} />{faq.tags.map((tag) => <span key={tag.id}>{tag.name}</span>)}</div>}
      <p className="faq-detail-content">{faq.content}</p>
      <footer><span>등록 {formatDate(faq.created_at)}</span><span>수정 {formatDate(faq.updated_at)}</span></footer>
    </article>
  </div>
}
