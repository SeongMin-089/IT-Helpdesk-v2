import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Archive, ArchiveRestore, FolderPlus, Save, Search } from 'lucide-react'
import { EmptyState, ErrorState, PageLoader } from '../components/common/PageState'
import { ApiError, apiRequest } from '../services/api'
import type {
  AssigneeListResponse,
  Relation,
  TicketCategory,
  TicketCategoryListResponse,
  TicketCategoryMutationResponse,
} from '../types/api'

type EditorTarget = { type: 'new' } | { type: 'category'; category: TicketCategory }
type CategoryAction = 'archive' | 'restore'

interface CategoryFormValues {
  name: string
  parentId: string
  assigneeId: string
  showInPortal: boolean
}

const emptyForm: CategoryFormValues = {
  name: '',
  parentId: '',
  assigneeId: '',
  showInPortal: true,
}

function categoryError(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) return fallback
  if (error.status === 403) return '문의 유형을 관리할 권한이 없습니다.'
  if (error.status === 404) return '문의 유형을 찾을 수 없습니다.'
  if (error.status === 409 || error.status === 422) return error.message
  if (error.status >= 500) return `서버 오류가 발생했습니다. ${fallback}`
  return error.message
}

function formValues(category: TicketCategory): CategoryFormValues {
  return {
    name: category.name,
    parentId: category.parent ? String(category.parent.id) : '',
    assigneeId: category.default_assignee ? String(category.default_assignee.id) : '',
    showInPortal: category.show_in_portal,
  }
}

function blockedParentIds(categories: TicketCategory[], rootId: number | null) {
  const blocked = new Set<number>()
  if (rootId === null) return blocked
  blocked.add(rootId)
  let changed = true
  while (changed) {
    changed = false
    categories.forEach((category) => {
      if (category.parent && blocked.has(category.parent.id) && !blocked.has(category.id)) {
        blocked.add(category.id)
        changed = true
      }
    })
  }
  return blocked
}

export function CategoryAdminPage() {
  const [categories, setCategories] = useState<TicketCategory[]>([])
  const [assignees, setAssignees] = useState<Relation[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<CategoryFormValues>(emptyForm)
  const [originalForm, setOriginalForm] = useState<CategoryFormValues>(emptyForm)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pendingEditorTarget, setPendingEditorTarget] = useState<EditorTarget | null>(null)
  const [pendingAction, setPendingAction] = useState<{ category: TicketCategory; action: CategoryAction } | null>(null)
  const [actionError, setActionError] = useState('')
  const requestIdRef = useRef(0)
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
    void Promise.all([
      apiRequest<TicketCategoryListResponse>('/api/oca/categories/all', { signal: controller.signal }),
      apiRequest<AssigneeListResponse>('/api/oca/assignees', { signal: controller.signal }),
    ])
      .then(([categoryResponse, assigneeResponse]) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setCategories(categoryResponse.categories)
        setAssignees(assigneeResponse.assignees)
        const initial = categoryResponse.categories[0]
        if (initial) {
          const values = formValues(initial)
          editingIdRef.current = initial.id
          setEditingId(initial.id)
          setForm(values)
          setOriginalForm(values)
        }
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setLoadError(categoryError(caught, '문의 유형 관리 데이터를 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) setLoading(false)
      })
    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [retryKey])

  const selectedCategory = editingId === null
    ? null
    : categories.find((category) => category.id === editingId) ?? null
  const hasUnsavedChanges = JSON.stringify(form) !== JSON.stringify(originalForm)
  const blockedIds = useMemo(
    () => blockedParentIds(categories, editingId),
    [categories, editingId],
  )
  const parentCandidates = useMemo(
    () => categories.filter((category) => category.active && !blockedIds.has(category.id)),
    [blockedIds, categories],
  )
  const currentInactiveParent = selectedCategory?.parent
    ? categories.find((category) => category.id === selectedCategory.parent?.id && !category.active) ?? null
    : null
  const currentMissingAssignee = selectedCategory?.default_assignee
    && !assignees.some((assignee) => assignee.id === selectedCategory.default_assignee?.id)
    ? selectedCategory.default_assignee
    : null
  const filteredCategories = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    return categories.filter((category) => {
      if (statusFilter === 'active' && !category.active) return false
      if (statusFilter === 'inactive' && category.active) return false
      return !query
        || category.name.toLocaleLowerCase().includes(query)
        || category.complete_name.toLocaleLowerCase().includes(query)
    })
  }, [categories, search, statusFilter])

  const applyEditorTarget = (target: EditorTarget) => {
    const category = target.type === 'category' ? target.category : null
    const values = category ? formValues(category) : emptyForm
    editingIdRef.current = category?.id ?? null
    setEditingId(category?.id ?? null)
    setForm(values)
    setOriginalForm(values)
    setFormError('')
    setActionError('')
    setPendingAction(null)
  }

  const requestEditorTarget = (target: EditorTarget) => {
    if (writeLockRef.current) return
    if (target.type === 'new' && editingId === null) return
    if (target.type === 'category' && target.category.id === editingId) return
    if (hasUnsavedChanges) {
      setPendingEditorTarget(target)
      return
    }
    applyEditorTarget(target)
  }

  const replaceCategory = (updated: TicketCategory) => {
    setCategories((current) => current.some((category) => category.id === updated.id)
      ? current.map((category) => category.id === updated.id ? updated : category)
      : [...current, updated])
  }

  const refreshCategories = async () => {
    try {
      return await apiRequest<TicketCategoryListResponse>('/api/oca/categories/all')
    } catch {
      return null
    }
  }

  const saveCategory = async (event: FormEvent) => {
    event.preventDefault()
    if (writeLockRef.current) return
    const name = form.name.trim()
    if (!name) {
      setFormError('문의 유형명을 입력해 주세요.')
      return
    }
    if (name.length > 200) {
      setFormError('문의 유형명은 최대 200자까지 입력할 수 있습니다.')
      return
    }
    const parentId = form.parentId ? Number(form.parentId) : null
    if (parentId !== null && blockedIds.has(parentId)) {
      setFormError('자기 자신 또는 하위 유형을 상위 유형으로 선택할 수 없습니다.')
      return
    }
    const assigneeId = form.assigneeId ? Number(form.assigneeId) : null
    const targetId = editingId
    const payload: { name?: string; parent_id?: number | null; show_in_portal?: boolean; default_assignee_id?: number | null } = {}
    if (targetId === null || name !== originalForm.name) payload.name = name
    if (targetId === null || form.parentId !== originalForm.parentId) payload.parent_id = parentId
    if (targetId === null || form.showInPortal !== originalForm.showInPortal) payload.show_in_portal = form.showInPortal
    if (targetId === null || form.assigneeId !== originalForm.assigneeId) payload.default_assignee_id = assigneeId
    if (Object.keys(payload).length === 0) {
      setFormError('변경된 내용이 없습니다.')
      return
    }

    const token = Symbol('category-save')
    writeLockRef.current = token
    setSaving(true)
    setFormError('')
    try {
      const response = await apiRequest<TicketCategoryMutationResponse>(targetId === null ? '/api/oca/categories' : `/api/oca/categories/${targetId}`, {
        method: targetId === null ? 'POST' : 'PATCH',
        body: JSON.stringify(payload),
      })
      const latest = await refreshCategories()
      if (!mountedRef.current || writeLockRef.current !== token) return
      if (latest) setCategories(latest.categories)
      else replaceCategory(response.category)
      if (editingIdRef.current === targetId) {
        const values = formValues(response.category)
        editingIdRef.current = response.category.id
        setEditingId(response.category.id)
        setForm(values)
        setOriginalForm(values)
      }
    } catch (caught) {
      if (mountedRef.current && writeLockRef.current === token) {
        setFormError(categoryError(caught, '문의 유형을 저장하지 못했습니다.'))
      }
    } finally {
      if (writeLockRef.current === token) {
        writeLockRef.current = null
        if (mountedRef.current) setSaving(false)
      }
    }
  }

  const runAction = async () => {
    if (!pendingAction || writeLockRef.current) return
    const { category, action } = pendingAction
    const token = Symbol(`category-${action}`)
    writeLockRef.current = token
    setSaving(true)
    setActionError('')
    try {
      const response = await apiRequest<TicketCategoryMutationResponse>(`/api/oca/categories/${category.id}/${action}`, { method: 'PATCH' })
      const latest = await refreshCategories()
      if (!mountedRef.current || writeLockRef.current !== token) return
      if (latest) setCategories(latest.categories)
      else replaceCategory(response.category)
      setPendingAction(null)
      if (editingIdRef.current === category.id) {
        const values = formValues(response.category)
        setForm(values)
        setOriginalForm(values)
      }
    } catch (caught) {
      if (mountedRef.current && writeLockRef.current === token) {
        setActionError(categoryError(caught, `문의 유형을 ${action === 'archive' ? '비활성화' : '활성화'}하지 못했습니다.`))
      }
    } finally {
      if (writeLockRef.current === token) {
        writeLockRef.current = null
        if (mountedRef.current) setSaving(false)
      }
    }
  }

  if (loading) return <PageLoader label="문의 유형 관리 데이터를 불러오는 중입니다." />
  if (loadError) return <section className="card"><ErrorState message={loadError} onRetry={() => { setLoading(true); setLoadError(''); setRetryKey((value) => value + 1) }} /></section>

  const confirmationOpen = Boolean(pendingEditorTarget || pendingAction)

  return <div className="page-stack">
    <header className="page-heading page-heading--inline"><div><p className="eyebrow">CATEGORY ADMIN</p><h1>문의 유형 관리</h1><p>문의 유형과 포털 표시, 기본 담당자를 관리합니다.</p></div><button className="button button--primary" type="button" onClick={() => requestEditorTarget({ type: 'new' })} disabled={saving}><FolderPlus size={17} />새 문의 유형</button></header>
    <section className="category-admin-layout">
      <aside className="card category-admin-list">
        <div className="category-admin-toolbar">
          <label className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value.slice(0, 200))} maxLength={200} placeholder="유형명 검색" aria-label="문의 유형 검색" /></label>
          <div className="category-admin-filters" aria-label="문의 유형 상태 필터">{(['all', 'active', 'inactive'] as const).map((value) => <button className={statusFilter === value ? 'is-active' : ''} type="button" onClick={() => setStatusFilter(value)} key={value}>{value === 'all' ? '전체' : value === 'active' ? '활성' : '비활성'}</button>)}</div>
        </div>
        {filteredCategories.length === 0 ? <EmptyState message="조건에 맞는 문의 유형이 없습니다." /> : <div className="category-admin-items">{filteredCategories.map((category) => <button className={editingId === category.id ? 'category-admin-item is-active' : 'category-admin-item'} type="button" onClick={() => requestEditorTarget({ type: 'category', category })} disabled={saving} key={category.id}><span className={category.active ? 'category-state category-state--active' : 'category-state'}>{category.active ? '활성' : '비활성'}</span><strong>{category.complete_name || category.name}</strong><small>담당자 {category.default_assignee?.name ?? '미지정'} · 포털 {category.show_in_portal ? '표시' : '숨김'}</small></button>)}</div>}
      </aside>

      <article className="card category-editor">
        <div className="category-editor__heading"><div><h2>{editingId === null ? '새 문의 유형' : '문의 유형 편집'}</h2><p>문의 등록 시 서버의 기존 자동배정 설정이 사용됩니다.</p></div>{selectedCategory && <span className={selectedCategory.active ? 'category-state category-state--active' : 'category-state'}>{selectedCategory.active ? '활성' : '비활성'}</span>}</div>
        {pendingEditorTarget && <div className="workflow-confirm category-confirm" role="alert"><p>저장하지 않은 변경사항이 있습니다. 내용을 버리고 {pendingEditorTarget.type === 'new' ? '새 문의 유형을 작성' : `“${pendingEditorTarget.category.name}” 유형으로 이동`}하시겠습니까?</p><div><button className="button button--secondary" type="button" onClick={() => setPendingEditorTarget(null)}>취소</button><button className="button button--primary" type="button" onClick={() => { const target = pendingEditorTarget; setPendingEditorTarget(null); applyEditorTarget(target) }}>변경사항 버리기</button></div></div>}
        <form className="category-editor__form" onSubmit={saveCategory} noValidate>
          <label className="form-field"><span>유형명 <strong>*</strong></span><input value={form.name} onChange={(event) => { setForm((current) => ({ ...current, name: event.target.value })); setFormError('') }} maxLength={200} disabled={saving || confirmationOpen} /><small>{form.name.length} / 200</small></label>
          <label className="form-field"><span>상위 유형</span><select value={form.parentId} onChange={(event) => { setForm((current) => ({ ...current, parentId: event.target.value })); setFormError('') }} disabled={saving || confirmationOpen}><option value="">상위 유형 없음</option>{currentInactiveParent && <option value={currentInactiveParent.id} disabled>{currentInactiveParent.complete_name || currentInactiveParent.name} (현재·비활성)</option>}{parentCandidates.map((category) => <option value={category.id} key={category.id}>{category.complete_name || category.name}</option>)}</select></label>
          <label className="form-field"><span>기본 담당자</span><select value={form.assigneeId} onChange={(event) => { setForm((current) => ({ ...current, assigneeId: event.target.value })); setFormError('') }} disabled={saving || confirmationOpen}><option value="">미지정</option>{currentMissingAssignee && <option value={currentMissingAssignee.id} disabled>{currentMissingAssignee.name} (현재·선택 불가)</option>}{assignees.map((assignee) => <option value={assignee.id} key={assignee.id}>{assignee.name}</option>)}</select></label>
          <label className="category-checkbox"><input type="checkbox" checked={form.showInPortal} onChange={(event) => { setForm((current) => ({ ...current, showInPortal: event.target.checked })); setFormError('') }} disabled={saving || confirmationOpen} /><span><strong>포털에 표시</strong><small>일반 직원의 문의 등록 유형 선택 항목에 노출합니다.</small></span></label>
          {formError && <div className="form-error detail-form-error" role="alert">{formError}</div>}
          <div className="category-editor__actions"><button className="button button--primary" type="submit" disabled={saving || confirmationOpen}><Save size={16} />{saving ? '처리 중...' : editingId === null ? '유형 등록' : '변경 저장'}</button></div>
        </form>

        {selectedCategory && <div className="category-lifecycle-actions">
          {hasUnsavedChanges && <p>상태를 변경하기 전에 편집 내용을 저장해 주세요.</p>}
          {selectedCategory.active ? <button className="button button--secondary" type="button" onClick={() => { setPendingAction({ category: selectedCategory, action: 'archive' }); setActionError('') }} disabled={saving || hasUnsavedChanges}><Archive size={16} />비활성화</button> : <button className="button button--primary" type="button" onClick={() => { setPendingAction({ category: selectedCategory, action: 'restore' }); setActionError('') }} disabled={saving || hasUnsavedChanges}><ArchiveRestore size={16} />활성화</button>}
        </div>}
        {pendingAction && <div className="workflow-confirm category-confirm" role="alert"><p>“{pendingAction.category.name}” 문의 유형을 {pendingAction.action === 'archive' ? '비활성화' : '활성화'}하시겠습니까?</p><div><button className="button button--secondary" type="button" onClick={() => { setPendingAction(null); setActionError('') }} disabled={saving}>취소</button><button className="button button--primary" type="button" onClick={() => void runAction()} disabled={saving}>{saving ? '처리 중...' : '확인'}</button></div></div>}
        {actionError && <div className="form-error detail-form-error" role="alert">{actionError}</div>}
      </article>
    </section>
  </div>
}
