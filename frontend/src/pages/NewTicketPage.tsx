import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, BookOpenText, Send } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { ErrorState, PageLoader } from '../components/common/PageState'
import { useAuth } from '../contexts/AuthContext'
import { ApiError, apiRequest } from '../services/api'
import type {
  Faq,
  FaqListResponse,
  TicketCategoryListResponse,
  TicketCreateResponse,
} from '../types/api'

const priorityOptions = [
  { value: '0', label: '낮음' },
  { value: '1', label: '보통' },
  { value: '2', label: '높음' },
  { value: '3', label: '긴급' },
]

export function NewTicketPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState('1')
  const [categoryId, setCategoryId] = useState('')
  const [categoryData, setCategoryData] = useState<TicketCategoryListResponse | null>(null)
  const [loadingCategories, setLoadingCategories] = useState(true)
  const [categoryError, setCategoryError] = useState('')
  const [categoryRetryKey, setCategoryRetryKey] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [suggestions, setSuggestions] = useState<Faq[]>([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const [suggestionError, setSuggestionError] = useState('')
  const submittingRef = useRef(false)
  const mountedRef = useRef(true)
  const suggestionRequestIdRef = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    void apiRequest<TicketCategoryListResponse>('/api/oca/categories', { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) setCategoryData(response)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setCategoryError(caught instanceof ApiError ? caught.message : '문의 유형을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingCategories(false)
      })
    return () => controller.abort()
  }, [categoryRetryKey])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    const query = title.trim()
    const requestId = ++suggestionRequestIdRef.current
    if (query.length < 2) return

    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void apiRequest<FaqListResponse>(`/api/oca/faqs/suggestions?${new URLSearchParams({ q: query })}`, { signal: controller.signal })
        .then((response) => {
          if (controller.signal.aborted || requestId !== suggestionRequestIdRef.current) return
          setSuggestions(response.faqs.slice(0, 3))
        })
        .catch(() => {
          if (controller.signal.aborted || requestId !== suggestionRequestIdRef.current) return
          setSuggestionError('FAQ 추천을 불러오지 못했습니다. 문의 등록은 계속할 수 있습니다.')
        })
        .finally(() => {
          if (!controller.signal.aborted && requestId === suggestionRequestIdRef.current) setSuggestionsLoading(false)
        })
    }, 400)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
      if (requestId === suggestionRequestIdRef.current) suggestionRequestIdRef.current += 1
    }
  }, [title])

  const categories = useMemo(
    () => categoryData?.categories.filter((category) =>
      category.active && (user?.role === 'agent' || category.show_in_portal),
    ) ?? [],
    [categoryData, user?.role],
  )

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (submittingRef.current) return
    const normalizedTitle = title.trim()
    const normalizedDescription = description.trim()
    if (!normalizedTitle) {
      setFormError('제목을 입력해 주세요.')
      return
    }
    if (!normalizedDescription) {
      setFormError('문의 내용을 입력해 주세요.')
      return
    }
    if (!categoryId) {
      setFormError('문의 유형을 선택해 주세요.')
      return
    }

    submittingRef.current = true
    setSubmitting(true)
    setFormError('')
    try {
      const response = await apiRequest<TicketCreateResponse>('/api/oca/tickets', {
        method: 'POST',
        body: JSON.stringify({
          title: normalizedTitle,
          description: normalizedDescription,
          priority,
          category_id: Number(categoryId),
        }),
      })
      if (mountedRef.current) navigate(`/tickets/${response.ticket_id}`, { replace: true })
    } catch (caught) {
      if (mountedRef.current) {
        setFormError(caught instanceof ApiError ? caught.message : '문의를 등록하지 못했습니다.')
      }
    } finally {
      submittingRef.current = false
      if (mountedRef.current) setSubmitting(false)
    }
  }

  const handleLeave = () => {
    if (!submittingRef.current) navigate('/tickets')
  }

  return (
    <div className="page-stack">
      <header className="page-heading page-heading--inline">
        <div><p className="eyebrow">NEW TICKET</p><h1>문의 등록</h1><p>지원이 필요한 내용을 자세히 작성해 주세요.</p></div>
        <button className="button button--secondary" type="button" onClick={handleLeave} disabled={submitting}><ArrowLeft size={17} />목록으로</button>
      </header>

      {loadingCategories ? <section className="card"><PageLoader label="문의 유형을 불러오는 중입니다." /></section> : categoryError ? <section className="card"><ErrorState message={categoryError} onRetry={() => { setLoadingCategories(true); setCategoryError(''); setCategoryRetryKey((value) => value + 1) }} /></section> : (
        <form className="card ticket-form" onSubmit={handleSubmit} noValidate>
          <div className="ticket-form__intro"><h2>문의 내용</h2><p>필수 항목을 모두 입력해 주세요.</p></div>
          <div className="ticket-form__fields">
            <label className="form-field"><span>제목 <strong>*</strong></span><input value={title} onChange={(event) => { const nextTitle = event.target.value; setTitle(nextTitle); setSuggestions([]); setSuggestionError(''); setSuggestionsLoading(nextTitle.trim().length >= 2) }} maxLength={200} required disabled={submitting} placeholder="문의 제목을 입력하세요" /><small>{title.length} / 200</small></label>
            {title.trim().length >= 2 && <section className="faq-suggestions" aria-label="제목 기반 FAQ 추천"><div className="faq-suggestions__heading"><BookOpenText size={17} /><div><strong>관련 FAQ</strong><span>입력한 제목과 관련된 공개 FAQ를 추천합니다.</span></div></div>{suggestionsLoading ? <p>FAQ를 찾는 중입니다.</p> : suggestionError ? <p className="faq-suggestions__error">{suggestionError}</p> : suggestions.length === 0 ? <p>관련 FAQ를 찾지 못했습니다.</p> : <div className="faq-suggestions__list">{suggestions.map((faq) => <Link to={`/faqs/${faq.id}`} target="_blank" rel="noreferrer" key={faq.id}><strong>{faq.name}</strong><span>{faq.content || '내용 없음'}</span><small>상세 보기</small></Link>)}</div>}</section>}
            <label className="form-field"><span>내용 <strong>*</strong></span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={10000} required disabled={submitting} placeholder="문제 상황과 필요한 지원 내용을 입력하세요" rows={10} /><small>{description.length.toLocaleString()} / 10,000</small></label>
            <div className="ticket-form__row">
              <label className="form-field"><span>문의 유형 <strong>*</strong></span><select value={categoryId} onChange={(event) => setCategoryId(event.target.value)} required disabled={submitting}><option value="">문의 유형 선택</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.complete_name || category.name}</option>)}</select></label>
              <label className="form-field"><span>긴급도</span><select value={priority} onChange={(event) => setPriority(event.target.value)} disabled={submitting}>{priorityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
            </div>
            {formError && <div className="form-error ticket-form__error" role="alert">{formError}</div>}
          </div>
          <div className="ticket-form__actions"><button className="button button--secondary" type="button" onClick={handleLeave} disabled={submitting}>취소</button><button className="button button--primary" type="submit" disabled={submitting || categories.length === 0}><Send size={17} />{submitting ? '등록 중...' : '문의 등록'}</button></div>
        </form>
      )}
    </div>
  )
}
