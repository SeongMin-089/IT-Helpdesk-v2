import { useEffect, useRef, useState } from 'react'
import { BookOpenText, Search, Tags } from 'lucide-react'
import { Link } from 'react-router'
import { EmptyState, ErrorState, PageLoader } from '../components/common/PageState'
import { ApiError, apiRequest } from '../services/api'
import { formatDate } from '../services/format'
import type { FaqListResponse } from '../types/api'

function faqListError(error: unknown) {
  if (!(error instanceof ApiError)) return 'FAQ를 불러오지 못했습니다.'
  if (error.status === 403) return 'FAQ를 조회할 권한이 없습니다.'
  if (error.status >= 500) return '서버 오류로 FAQ를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'
  return error.message
}

export function FaqsPage() {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [data, setData] = useState<FaqListResponse | null>(null)
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
      setDebouncedSearch(nextSearch)
    }, 350)
    return () => window.clearTimeout(timer)
  }, [debouncedSearch, search])

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++requestIdRef.current
    const path = debouncedSearch
      ? `/api/oca/faqs/suggestions?${new URLSearchParams({ q: debouncedSearch })}`
      : '/api/oca/faqs?limit=100'
    void apiRequest<FaqListResponse>(path, { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setData(response)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setError(faqListError(caught))
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setLoading(false)
      })
    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [debouncedSearch, retryKey])

  return <div className="page-stack">
    <header className="page-heading page-heading--inline">
      <div><p className="eyebrow">KNOWLEDGE BASE</p><h1>FAQ</h1><p>자주 묻는 질문과 해결 방법을 확인합니다.</p></div>
      {data && <span className="result-count">{debouncedSearch ? '추천' : '표시'} <strong>{data.count.toLocaleString()}</strong>건</span>}
    </header>

    <section className="card faq-search-card">
      <label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value.slice(0, 200))} maxLength={200} placeholder="FAQ 제목 또는 내용 검색" aria-label="FAQ 검색" /></label>
      <p>{debouncedSearch ? '전체 공개 FAQ에서 관련도가 높은 결과를 최대 3건 추천합니다.' : '공개 FAQ를 최대 100건까지 표시합니다. 전체 데이터 건수와 다를 수 있습니다.'}</p>
    </section>

    {loading ? <section className="card"><PageLoader label="FAQ를 불러오는 중입니다." /></section> : error ? <section className="card"><ErrorState message={error} onRetry={() => { setLoading(true); setError(''); setRetryKey((value) => value + 1) }} /></section> : !data || data.faqs.length === 0 ? <section className="card"><EmptyState message={debouncedSearch ? '검색어와 관련된 공개 FAQ가 없습니다.' : '등록된 공개 FAQ가 없습니다.'} /></section> : (
      <section className="faq-card-grid" aria-label="공개 FAQ 목록">
        {data.faqs.map((faq) => <Link className="card faq-card" to={`/faqs/${faq.id}`} key={faq.id}><div className="faq-card__icon"><BookOpenText size={19} /></div><div><h2>{faq.name}</h2><p>{faq.content}</p></div>{faq.tags.length > 0 && <div className="faq-tags"><Tags size={13} />{faq.tags.map((tag) => <span key={tag.id}>{tag.name}</span>)}</div>}<time>수정 {formatDate(faq.updated_at)}</time></Link>)}
      </section>
    )}
  </div>
}
