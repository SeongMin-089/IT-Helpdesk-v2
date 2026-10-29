import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Archive, ArchiveRestore, Eye, EyeOff, FilePlus2, Save, Tags } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { EmptyState, ErrorState, PageLoader } from '../components/common/PageState'
import { ApiError, apiRequest } from '../services/api'
import { formatDate } from '../services/format'
import type { Faq, FaqListResponse, FaqMutationResponse, FaqTag, FaqTagListResponse } from '../types/api'

type FaqAction = 'publish' | 'unpublish' | 'archive' | 'restore'
type EditorTarget = { type: 'new' } | { type: 'faq'; faq: Faq }

const actionLabels: Record<FaqAction, string> = {
  publish: '공개',
  unpublish: '비공개 전환',
  archive: '보관',
  restore: '복원',
}

function adminError(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) return fallback
  if (error.status === 403) return error.message
  if (error.status === 404) return 'FAQ를 찾을 수 없습니다.'
  if (error.status === 409 || error.status === 422) return error.message
  if (error.status >= 500) return `서버 오류가 발생했습니다. ${fallback}`
  return error.message
}

function faqState(faq: Faq) {
  if (!faq.active) return { key: 'archived', label: '보관' }
  return faq.visibility === 'public'
    ? { key: 'public', label: '공개' }
    : { key: 'draft', label: '비공개 초안' }
}

function sameTagIds(left: number[], right: number[]) {
  if (left.length !== right.length) return false
  const rightIds = new Set(right)
  return left.every((tagId) => rightIds.has(tagId))
}

export function FaqAdminPage() {
  const [searchParams] = useSearchParams()
  const requestedFaqId = Number(searchParams.get('faq'))
  const [faqs, setFaqs] = useState<Faq[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const [filter, setFilter] = useState<'all' | 'public' | 'draft' | 'archived'>('all')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [tags, setTags] = useState<FaqTag[]>([])
  const [tagsLoaded, setTagsLoaded] = useState(false)
  const [tagsLoading, setTagsLoading] = useState(true)
  const [tagsError, setTagsError] = useState('')
  const [tagsRetryKey, setTagsRetryKey] = useState(0)
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([])
  const [originalName, setOriginalName] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [originalTagIds, setOriginalTagIds] = useState<number[]>([])
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pendingAction, setPendingAction] = useState<{ faq: Faq; action: FaqAction } | null>(null)
  const [pendingEditorTarget, setPendingEditorTarget] = useState<EditorTarget | null>(null)
  const [actionError, setActionError] = useState('')
  const requestIdRef = useRef(0)
  const tagRequestIdRef = useRef(0)
  const writeLockRef = useRef<symbol | null>(null)
  const mountedRef = useRef(true)
  const editingIdRef = useRef<number | null>(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++requestIdRef.current
    void apiRequest<FaqListResponse>('/api/oca/faqs/admin/all', { signal: controller.signal })
      .then((response) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setFaqs(response.faqs)
        const initial = response.faqs.find((faq) => faq.id === requestedFaqId) ?? response.faqs[0]
        if (initial) {
          const initialTagIds = initial.tags.map((tag) => tag.id)
          editingIdRef.current = initial.id
          setEditingId(initial.id)
          setName(initial.name)
          setContent(initial.content)
          setOriginalName(initial.name)
          setOriginalContent(initial.content)
          setSelectedTagIds(initialTagIds)
          setOriginalTagIds(initialTagIds)
        }
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setLoadError(adminError(caught, 'FAQ 관리 데이터를 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setLoading(false)
      })
    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [requestedFaqId, retryKey])

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++tagRequestIdRef.current
    void apiRequest<FaqTagListResponse>('/api/oca/faqs/admin/tags', { signal: controller.signal })
      .then((response) => {
        if (controller.signal.aborted || requestId !== tagRequestIdRef.current) return
        setTags(response.tags)
        setTagsLoaded(true)
        setTagsError('')
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || requestId !== tagRequestIdRef.current) return
        setTagsLoaded(false)
        setTagsError(adminError(caught, 'FAQ 태그 목록을 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === tagRequestIdRef.current) setTagsLoading(false)
      })
    return () => {
      controller.abort()
      tagRequestIdRef.current += 1
    }
  }, [tagsRetryKey])

  const filteredFaqs = useMemo(() => faqs.filter((faq) => {
    if (filter === 'all') return true
    return faqState(faq).key === filter
  }), [faqs, filter])
  const selectedFaq = editingId === null ? null : faqs.find((faq) => faq.id === editingId) ?? null
  const activeTagIds = useMemo(() => new Set(tags.map((tag) => tag.id)), [tags])
  const editorTags = useMemo(() => {
    const tagsById = new Map(tags.map((tag) => [tag.id, tag]))
    selectedFaq?.tags.forEach((tag) => tagsById.set(tag.id, tag))
    return [...tagsById.values()]
  }, [selectedFaq, tags])
  const inactiveExistingTags = useMemo(
    () => selectedFaq?.tags.filter((tag) => !activeTagIds.has(tag.id)) ?? [],
    [activeTagIds, selectedFaq],
  )
  const hasUnsavedChanges = editingId === null
    ? Boolean(name.trim() || content.trim() || (tagsLoaded && selectedTagIds.length))
    : name.trim() !== originalName || content.trim() !== originalContent || (tagsLoaded && !sameTagIds(selectedTagIds, originalTagIds))

  const applyEditorTarget = (target: EditorTarget) => {
    const faq = target.type === 'faq' ? target.faq : null
    editingIdRef.current = faq?.id ?? null
    setEditingId(faq?.id ?? null)
    setName(faq?.name ?? '')
    setContent(faq?.content ?? '')
    setOriginalName(faq?.name ?? '')
    setOriginalContent(faq?.content ?? '')
    const nextTagIds = faq?.tags.map((tag) => tag.id) ?? []
    setSelectedTagIds(nextTagIds)
    setOriginalTagIds(nextTagIds)
    setFormError('')
    setActionError('')
    setPendingAction(null)
  }

  const requestEditorTarget = (target: EditorTarget) => {
    if (writeLockRef.current) return
    if (target.type === 'new' && editingId === null) return
    if (target.type === 'faq' && target.faq.id === editingId) return
    if (hasUnsavedChanges) {
      setPendingEditorTarget(target)
      return
    }
    applyEditorTarget(target)
  }

  const startNew = () => requestEditorTarget({ type: 'new' })

  const editFaq = (faq: Faq) => {
    requestEditorTarget({ type: 'faq', faq })
  }

  const replaceFaq = (updated: Faq) => {
    setFaqs((current) => current.some((faq) => faq.id === updated.id)
      ? current.map((faq) => faq.id === updated.id ? updated : faq)
      : [updated, ...current])
  }

  const saveFaq = async (event: FormEvent) => {
    event.preventDefault()
    if (writeLockRef.current) return
    const normalizedName = name.trim()
    const normalizedContent = content.trim()
    if (!normalizedName || !normalizedContent) {
      setFormError('FAQ 제목과 내용을 모두 입력해 주세요.')
      return
    }
    if (normalizedName.length > 200 || normalizedContent.length > 20000) {
      setFormError('제목 또는 내용의 최대 길이를 확인해 주세요.')
      return
    }
    const targetId = editingId
    const payload: { name?: string; content?: string; tag_ids?: number[] } = {}
    if (targetId === null || normalizedName !== originalName) payload.name = normalizedName
    if (targetId === null || normalizedContent !== originalContent) payload.content = normalizedContent
    const tagsChanged = tagsLoaded && (targetId === null || !sameTagIds(selectedTagIds, originalTagIds))
    if (tagsChanged) payload.tag_ids = selectedTagIds.filter((tagId) => activeTagIds.has(tagId))
    if (Object.keys(payload).length === 0) {
      setFormError('변경된 내용이 없습니다.')
      return
    }
    const token = Symbol('faq-save')
    writeLockRef.current = token
    setSaving(true)
    setFormError('')
    try {
      const response = await apiRequest<FaqMutationResponse>(targetId === null ? '/api/oca/faqs/drafts' : `/api/oca/faqs/${targetId}`, {
        method: targetId === null ? 'POST' : 'PATCH',
        body: JSON.stringify(payload),
      })
      if (!mountedRef.current || writeLockRef.current !== token) return
      replaceFaq(response.faq)
      if (editingIdRef.current === targetId) {
        editingIdRef.current = response.faq.id
        setEditingId(response.faq.id)
        setName(response.faq.name)
        setContent(response.faq.content)
        setOriginalName(response.faq.name)
        setOriginalContent(response.faq.content)
        const savedTagIds = response.faq.tags.map((tag) => tag.id)
        setSelectedTagIds(savedTagIds)
        setOriginalTagIds(savedTagIds)
      }
    } catch (caught) {
      if (mountedRef.current && writeLockRef.current === token) setFormError(adminError(caught, 'FAQ를 저장하지 못했습니다.'))
    } finally {
      if (writeLockRef.current === token) {
        writeLockRef.current = null
        if (mountedRef.current) setSaving(false)
      }
    }
  }

  const runAction = async () => {
    if (!pendingAction || writeLockRef.current) return
    const { faq, action } = pendingAction
    const token = Symbol(`faq-${action}`)
    writeLockRef.current = token
    setSaving(true)
    setActionError('')
    try {
      const response = await apiRequest<FaqMutationResponse>(`/api/oca/faqs/${faq.id}/${action}`, { method: 'POST' })
      if (!mountedRef.current || writeLockRef.current !== token) return
      replaceFaq(response.faq)
      setPendingAction(null)
      if (editingIdRef.current === faq.id) {
        setName(response.faq.name)
        setContent(response.faq.content)
        setOriginalName(response.faq.name)
        setOriginalContent(response.faq.content)
        const savedTagIds = response.faq.tags.map((tag) => tag.id)
        setSelectedTagIds(savedTagIds)
        setOriginalTagIds(savedTagIds)
      }
    } catch (caught) {
      if (mountedRef.current && writeLockRef.current === token) setActionError(adminError(caught, `FAQ를 ${actionLabels[action]}하지 못했습니다.`))
    } finally {
      if (writeLockRef.current === token) {
        writeLockRef.current = null
        if (mountedRef.current) setSaving(false)
      }
    }
  }

  if (loading) return <PageLoader label="FAQ 관리 데이터를 불러오는 중입니다." />
  if (loadError) return <section className="card"><ErrorState message={loadError} onRetry={() => { setLoading(true); setLoadError(''); setRetryKey((value) => value + 1) }} /></section>

  return <div className="page-stack">
    <header className="page-heading page-heading--inline"><div><p className="eyebrow">FAQ ADMIN</p><h1>FAQ 관리</h1><p>FAQ 초안을 검토하고 공개 상태를 관리합니다.</p></div><button className="button button--primary" type="button" onClick={startNew} disabled={saving}><FilePlus2 size={17} />새 FAQ 초안</button></header>
    <section className="faq-admin-layout">
      <aside className="card faq-admin-list">
        <div className="faq-admin-filters" aria-label="FAQ 상태 필터">
          {(['all', 'public', 'draft', 'archived'] as const).map((value) => <button className={filter === value ? 'is-active' : ''} type="button" key={value} onClick={() => setFilter(value)}>{value === 'all' ? '전체' : value === 'public' ? '공개' : value === 'draft' ? '초안' : '보관'}</button>)}
        </div>
        {filteredFaqs.length === 0 ? <EmptyState message="해당 상태의 FAQ가 없습니다." /> : <div className="faq-admin-items">{filteredFaqs.map((faq) => { const state = faqState(faq); return <button className={editingId === faq.id ? 'faq-admin-item is-active' : 'faq-admin-item'} type="button" onClick={() => editFaq(faq)} disabled={saving} key={faq.id}><span className={`faq-state faq-state--${state.key}`}>{state.label}</span><strong>{faq.name}</strong><small>수정 {formatDate(faq.updated_at)}</small></button> })}</div>}
      </aside>

      <article className="card faq-editor">
        <div className="faq-editor__heading"><div><h2>{editingId === null ? '새 FAQ 초안' : 'FAQ 편집'}</h2><p>{editingId === null ? '비공개 초안으로 생성됩니다.' : '제목, 내용과 태그를 검토하고 저장합니다.'}</p></div>{selectedFaq?.active && selectedFaq.visibility === 'public' && <Link className="button button--secondary" to={`/faqs/${selectedFaq.id}`}><Eye size={15} />공개 화면</Link>}</div>
        {selectedFaq && <div className="faq-editor__meta"><span className={`faq-state faq-state--${faqState(selectedFaq).key}`}>{faqState(selectedFaq).label}</span>{selectedFaq.tags.length > 0 && <div className="faq-tags"><Tags size={13} />{selectedFaq.tags.map((tag) => <span key={tag.id}>{tag.name}</span>)}</div>}</div>}
        {pendingEditorTarget && <div className="workflow-confirm faq-confirm faq-switch-confirm" role="alert"><p>저장하지 않은 편집 내용이 있습니다. 변경사항을 버리고 {pendingEditorTarget.type === 'new' ? '새 FAQ 초안을 작성' : `“${pendingEditorTarget.faq.name}” FAQ로 이동`}하시겠습니까?</p><div><button className="button button--secondary" type="button" onClick={() => setPendingEditorTarget(null)}>취소</button><button className="button button--primary" type="button" onClick={() => { const target = pendingEditorTarget; setPendingEditorTarget(null); applyEditorTarget(target) }}>변경사항 버리기</button></div></div>}
        <form className="faq-editor__form" onSubmit={saveFaq} noValidate>
          <label className="form-field"><span>제목 <strong>*</strong></span><input value={name} onChange={(event) => { setName(event.target.value); setFormError('') }} maxLength={200} disabled={saving || Boolean(pendingAction) || Boolean(pendingEditorTarget)} /><small>{name.length} / 200</small></label>
          <label className="form-field"><span>내용 <strong>*</strong></span><textarea value={content} onChange={(event) => { setContent(event.target.value); setFormError('') }} maxLength={20000} rows={14} disabled={saving || Boolean(pendingAction) || Boolean(pendingEditorTarget)} /><small>{content.length.toLocaleString()} / 20,000</small></label>
          {tagsLoading ? <div className="faq-tag-load-state">FAQ 태그를 불러오는 중입니다.</div> : tagsError ? <div className="detail-load-error" role="alert"><span>{tagsError}</span><span>{editingId === null ? '태그 없이 FAQ 초안을 생성할 수 있습니다.' : '기존 FAQ 태그는 변경하지 않고 제목과 내용만 저장할 수 있습니다.'}</span><button className="button button--secondary" type="button" onClick={() => { setTagsLoading(true); setTagsError(''); setTagsRetryKey((value) => value + 1) }}>태그 다시 시도</button></div> : <fieldset className="faq-tag-selector" disabled={saving || Boolean(pendingAction) || Boolean(pendingEditorTarget)}><legend>태그</legend>{editorTags.length === 0 ? <p>선택할 수 있는 활성 태그가 없습니다.</p> : <div>{editorTags.map((tag) => { const active = activeTagIds.has(tag.id); const checked = selectedTagIds.includes(tag.id); return <label key={tag.id}><input type="checkbox" checked={checked} disabled={!active && !checked} onChange={(event) => { const nextChecked = event.target.checked; setSelectedTagIds((current) => nextChecked ? [...current, tag.id] : current.filter((tagId) => tagId !== tag.id)); setFormError('') }} /><span>{tag.name}{!active ? ' (비활성)' : ''}</span></label> })}</div>}{inactiveExistingTags.length > 0 && <p className="faq-tag-selector__notice">비활성 태그는 기존 상태로 표시됩니다. 태그 구성을 변경해 저장하면 비활성 태그는 제거됩니다.</p>}</fieldset>}
          {formError && <div className="form-error detail-form-error" role="alert">{formError}</div>}
          <div className="faq-editor__actions"><button className="button button--primary" type="submit" disabled={saving || Boolean(pendingAction) || Boolean(pendingEditorTarget)}><Save size={16} />{saving ? '처리 중...' : editingId === null ? '초안 생성' : '변경 저장'}</button></div>
        </form>

        {selectedFaq && <div className="faq-lifecycle-actions">
          {hasUnsavedChanges && <p>공개 상태를 변경하기 전에 편집 내용을 저장해 주세요.</p>}
          {selectedFaq.active && selectedFaq.visibility === 'draft' && <button className="button button--primary" type="button" onClick={() => { setPendingAction({ faq: selectedFaq, action: 'publish' }); setActionError('') }} disabled={saving || hasUnsavedChanges}><Eye size={16} />공개</button>}
          {selectedFaq.active && selectedFaq.visibility === 'public' && <button className="button button--secondary" type="button" onClick={() => { setPendingAction({ faq: selectedFaq, action: 'unpublish' }); setActionError('') }} disabled={saving || hasUnsavedChanges}><EyeOff size={16} />비공개 전환</button>}
          {selectedFaq.active && <button className="button button--secondary" type="button" onClick={() => { setPendingAction({ faq: selectedFaq, action: 'archive' }); setActionError('') }} disabled={saving || hasUnsavedChanges}><Archive size={16} />보관</button>}
          {!selectedFaq.active && <button className="button button--primary" type="button" onClick={() => { setPendingAction({ faq: selectedFaq, action: 'restore' }); setActionError('') }} disabled={saving || hasUnsavedChanges}><ArchiveRestore size={16} />복원</button>}
        </div>}
        {pendingAction && <div className="workflow-confirm faq-confirm" role="alert"><p>“{pendingAction.faq.name}” FAQ를 {actionLabels[pendingAction.action]}하시겠습니까?</p><div><button className="button button--secondary" type="button" onClick={() => { setPendingAction(null); setActionError('') }} disabled={saving}>취소</button><button className="button button--primary" type="button" onClick={() => void runAction()} disabled={saving}>{saving ? '처리 중...' : '확인'}</button></div></div>}
        {actionError && <div className="form-error detail-form-error" role="alert">{actionError}</div>}
      </article>
    </section>
  </div>
}
