import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react'
import { Download, MessageSquareText, Paperclip, RefreshCcw, Send, Upload } from 'lucide-react'
import { ApiError, apiBlobRequest, apiRequest } from '../../services/api'
import { formatDate, stageLabel } from '../../services/format'
import type {
  AuthUser,
  Ticket,
  TicketAttachment,
  TicketAttachmentsResponse,
  TicketAttachmentUploadResponse,
  TicketCommentCreateResponse,
  TicketCommentKind,
  TicketCommentsResponse,
  TicketHistoryItem,
  TicketHistoryResponse,
} from '../../types/api'

const MAX_FILE_SIZE = 10 * 1024 * 1024
const DOWNLOAD_URL_REVOKE_DELAY = 60_000
const allowedFileTypes: Record<string, string> = {
  pdf: 'application/pdf',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  txt: 'text/plain',
  csv: 'text/csv',
  zip: 'application/zip',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

function revokeObjectUrlLater(objectUrl: string) {
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), DOWNLOAD_URL_REVOKE_DELAY)
}

type SectionResult<T> = { ticketId: number; data?: T; error?: string }

function sectionError(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) return fallback
  if (error.status === 401) return '로그인 상태를 다시 확인해 주세요.'
  if (error.status === 403) return '이 내용을 조회할 권한이 없습니다.'
  if (error.status === 404) return '문의를 찾을 수 없습니다.'
  if (error.status >= 500) return `서버 오류가 발생했습니다. ${fallback}`
  return error.message
}

function writeError(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) return fallback
  if (error.status === 401) return '로그인 상태를 다시 확인해 주세요.'
  if (error.status === 403) return '이 작업을 수행할 권한이 없습니다.'
  if (error.status === 404) return '문의를 찾을 수 없습니다.'
  if ([409, 413, 422].includes(error.status)) return error.message
  if (error.status >= 500) return `서버 오류로 ${fallback}`
  return error.message
}

function useTicketSection<T>(ticketId: number, path: string, refreshKey: string) {
  const [result, setResult] = useState<SectionResult<T> | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const requestIdRef = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++requestIdRef.current
    void apiRequest<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted && requestId === requestIdRef.current) {
          setResult({ ticketId, data })
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return
        setResult({ ticketId, error: sectionError(error, '내용을 불러오지 못했습니다.') })
      })
    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [path, refreshKey, retryKey, ticketId])

  const current = result?.ticketId === ticketId ? result : null
  return {
    data: current?.data,
    error: current?.error,
    loading: !current,
    retry: () => {
      setResult(null)
      setRetryKey((value) => value + 1)
    },
  }
}

function SectionMessage({ message, retry }: { message: string; retry?: () => void }) {
  return <div className={retry ? 'activity-message activity-message--error' : 'activity-message'} role={retry ? 'alert' : undefined}><span>{message}</span>{retry && <button className="button button--secondary" type="button" onClick={retry}><RefreshCcw size={14} />다시 시도</button>}</div>
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function historyValue(item: TicketHistoryItem, side: 'old_value' | 'new_value') {
  const value = item[side]
  if (!value?.name) return '미지정'
  return item.change_type === 'status' ? stageLabel(value.name) : value.name
}

export function TicketActivitySections({ ticket, user, refreshKey, mainContent, sidebarContent }: { ticket: Ticket; user: AuthUser; refreshKey: string; mainContent: ReactNode; sidebarContent: ReactNode }) {
  const [commentsRefresh, setCommentsRefresh] = useState(0)
  const [attachmentsRefresh, setAttachmentsRefresh] = useState(0)
  const comments = useTicketSection<TicketCommentsResponse>(ticket.id, `/api/oca/tickets/${ticket.id}/comments`, `${refreshKey}:${commentsRefresh}`)
  const attachments = useTicketSection<TicketAttachmentsResponse>(ticket.id, `/api/oca/tickets/${ticket.id}/attachments`, `${refreshKey}:${attachmentsRefresh}`)
  const history = useTicketSection<TicketHistoryResponse>(ticket.id, `/api/oca/tickets/${ticket.id}/history?limit=50`, refreshKey)

  const mountedRef = useRef(true)
  const commentSavingRef = useRef<symbol | null>(null)
  const uploadSavingRef = useRef<symbol | null>(null)
  const downloadRef = useRef<{ token: symbol; controller: AbortController } | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [commentBody, setCommentBody] = useState('')
  const [commentKind, setCommentKind] = useState<TicketCommentKind>('comment')
  const [commentSaving, setCommentSaving] = useState(false)
  const [commentError, setCommentError] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [attachmentError, setAttachmentError] = useState('')
  const [downloadingId, setDownloadingId] = useState<number | null>(null)

  useEffect(() => () => {
    mountedRef.current = false
    downloadRef.current?.controller.abort()
  }, [])

  const readOnly = !ticket.active || ticket.closed
  const visibleComments = (comments.data?.comments ?? []).filter(
    (comment) => user.role === 'agent' || comment.kind !== 'note',
  )

  const submitComment = async (event: FormEvent) => {
    event.preventDefault()
    if (commentSavingRef.current || readOnly) return
    const body = commentBody.trim()
    if (!body) {
      setCommentError('댓글 내용을 입력해 주세요.')
      return
    }
    if (body.length > 10000) {
      setCommentError('댓글은 최대 10,000자까지 입력할 수 있습니다.')
      return
    }
    const kind: TicketCommentKind = user.role === 'agent' ? commentKind : 'comment'
    const token = Symbol('comment-save')
    commentSavingRef.current = token
    setCommentSaving(true)
    setCommentError('')
    try {
      await apiRequest<TicketCommentCreateResponse>(`/api/oca/tickets/${ticket.id}/comments`, {
        method: 'POST',
        body: JSON.stringify({ body, kind }),
      })
      if (!mountedRef.current || commentSavingRef.current !== token) return
      setCommentBody('')
      setCommentsRefresh((value) => value + 1)
    } catch (error) {
      if (mountedRef.current && commentSavingRef.current === token) {
        setCommentError(writeError(error, '댓글을 등록하지 못했습니다. 입력한 내용은 유지됩니다.'))
      }
    } finally {
      if (commentSavingRef.current === token) {
        commentSavingRef.current = null
        if (mountedRef.current) setCommentSaving(false)
      }
    }
  }

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null
    setSelectedFile(null)
    setAttachmentError('')
    if (!file) return
    const extension = file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() ?? '' : ''
    const expectedType = allowedFileTypes[extension]
    if (file.size === 0) {
      setAttachmentError('빈 파일은 업로드할 수 없습니다.')
    } else if (file.size > MAX_FILE_SIZE) {
      setAttachmentError('첨부 파일은 10MB를 초과할 수 없습니다.')
    } else if (!expectedType || file.type !== expectedType) {
      setAttachmentError('허용되지 않거나 파일 확장자와 MIME 형식이 일치하지 않습니다.')
    } else {
      setSelectedFile(file)
    }
  }

  const uploadFile = async (event: FormEvent) => {
    event.preventDefault()
    if (uploadSavingRef.current || !selectedFile || readOnly) return
    const token = Symbol('attachment-upload')
    uploadSavingRef.current = token
    setUploading(true)
    setAttachmentError('')
    const query = new URLSearchParams({ filename: selectedFile.name, content_type: selectedFile.type })
    try {
      await apiRequest<TicketAttachmentUploadResponse>(`/api/oca/tickets/${ticket.id}/attachments?${query}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: selectedFile,
      })
      if (!mountedRef.current || uploadSavingRef.current !== token) return
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      setAttachmentsRefresh((value) => value + 1)
    } catch (error) {
      if (mountedRef.current && uploadSavingRef.current === token) {
        setAttachmentError(writeError(error, '파일을 업로드하지 못했습니다. 선택한 파일은 유지됩니다.'))
      }
    } finally {
      if (uploadSavingRef.current === token) {
        uploadSavingRef.current = null
        if (mountedRef.current) setUploading(false)
      }
    }
  }

  const downloadFile = async (attachment: TicketAttachment) => {
    if (downloadRef.current) return
    const token = Symbol('attachment-download')
    const controller = new AbortController()
    let objectUrl: string | null = null
    let link: HTMLAnchorElement | null = null
    downloadRef.current = { token, controller }
    setDownloadingId(attachment.id)
    setAttachmentError('')
    try {
      const blob = await apiBlobRequest(`/api/oca/tickets/${ticket.id}/attachments/${attachment.id}/download`, { signal: controller.signal })
      if (!mountedRef.current || downloadRef.current?.token !== token) return
      objectUrl = URL.createObjectURL(blob)
      link = document.createElement('a')
      link.href = objectUrl
      link.download = attachment.name || `attachment-${attachment.id}`
      document.body.appendChild(link)
      link.click()
      revokeObjectUrlLater(objectUrl)
      objectUrl = null
    } catch (error) {
      if (!controller.signal.aborted && mountedRef.current && downloadRef.current?.token === token) {
        setAttachmentError(writeError(error, '파일을 다운로드하지 못했습니다.'))
      }
    } finally {
      link?.remove()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      if (downloadRef.current?.token === token) {
        downloadRef.current = null
        if (mountedRef.current) setDownloadingId(null)
      }
    }
  }

  const commentsSection = <article className="card activity-card activity-card--comments">
    <div className="activity-card__heading"><div><MessageSquareText size={19} /><div><h2>댓글 및 내부 메모</h2><p>{user.role === 'agent' ? '공개 댓글과 담당자용 내부 메모를 확인합니다.' : '문의에 대한 공개 댓글을 확인합니다.'}</p></div></div></div>
    <div className="activity-card__body">
      {comments.loading ? <SectionMessage message="댓글을 불러오는 중입니다." /> : comments.error ? <SectionMessage message={comments.error} retry={comments.retry} /> : visibleComments.length === 0 ? <SectionMessage message="등록된 댓글이 없습니다." /> : (
        <div className="comment-list">{visibleComments.map((comment) => <article className={`comment-item${comment.kind === 'note' ? ' comment-item--note' : ''}`} key={comment.id}><div className="comment-item__meta"><strong>{comment.author?.name ?? '알 수 없음'}</strong>{comment.kind === 'note' && <span>내부 메모</span>}<time>{formatDate(comment.created_at)}</time></div><p>{comment.body}</p></article>)}</div>
      )}
      {readOnly ? <p className="activity-readonly">종료·보관 문의는 댓글과 메모를 추가할 수 없습니다.</p> : (
        <form className="activity-form" onSubmit={submitComment} noValidate>
          {user.role === 'agent' && <label className="form-field"><span>작성 유형</span><select value={commentKind} onChange={(event) => { setCommentKind(event.target.value as TicketCommentKind); setCommentError('') }} disabled={commentSaving}><option value="comment">공개 댓글</option><option value="note">내부 메모</option></select></label>}
          <label className="form-field"><span>{commentKind === 'note' && user.role === 'agent' ? '내부 메모' : '댓글'} <strong>*</strong></span><textarea value={commentBody} onChange={(event) => { setCommentBody(event.target.value); setCommentError('') }} maxLength={10000} rows={5} disabled={commentSaving} /><small>{commentBody.length.toLocaleString()} / 10,000</small></label>
          {commentError && <div className="form-error detail-form-error" role="alert">{commentError}</div>}
          <button className="button button--primary" type="submit" disabled={commentSaving}><Send size={15} />{commentSaving ? '등록 중...' : '등록'}</button>
        </form>
      )}
    </div>
  </article>

  const attachmentsSection = <article className="card activity-card">
    <div className="activity-card__heading"><div><Paperclip size={19} /><div><h2>첨부파일</h2><p>최대 10MB의 허용된 문서와 이미지를 관리합니다.</p></div></div></div>
    <div className="activity-card__body">
      {attachments.loading ? <SectionMessage message="첨부파일을 불러오는 중입니다." /> : attachments.error ? <SectionMessage message={attachments.error} retry={attachments.retry} /> : (attachments.data?.attachments.length ?? 0) === 0 ? <SectionMessage message="등록된 첨부파일이 없습니다." /> : (
        <div className="attachment-list">{attachments.data?.attachments.map((attachment) => <div className="attachment-item" key={attachment.id}><div><strong>{attachment.name}</strong><span>{formatFileSize(attachment.size)} · {attachment.created_by?.name ?? '알 수 없음'} · {formatDate(attachment.created_at)}</span></div><button className="icon-button" type="button" aria-label={`${attachment.name} 다운로드`} title="다운로드" onClick={() => void downloadFile(attachment)} disabled={downloadingId !== null}>{downloadingId === attachment.id ? <span className="spinner" /> : <Download size={16} />}</button></div>)}</div>
      )}
      {attachmentError && <div className="form-error detail-form-error" role="alert">{attachmentError}</div>}
      {readOnly ? <p className="activity-readonly">종료·보관 문의는 첨부파일을 추가할 수 없습니다. 기존 파일은 다운로드할 수 있습니다.</p> : (
        <form className="attachment-form" onSubmit={uploadFile}>
          <label className="form-field"><span>파일 선택</span><input ref={fileInputRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.txt,.csv,.zip,.docx,.xlsx,.pptx" onChange={selectFile} disabled={uploading} /></label>
          {selectedFile && <p className="attachment-selection">{selectedFile.name} · {formatFileSize(selectedFile.size)}</p>}
          <button className="button button--primary" type="submit" disabled={uploading || !selectedFile}><Upload size={15} />{uploading ? '업로드 중...' : '업로드'}</button>
        </form>
      )}
    </div>
  </article>

  const historySection = <article className="card activity-card activity-card--history">
    <div className="activity-card__heading"><div><RefreshCcw size={19} /><div><h2>문의 처리 이력</h2><p>상태와 담당자 변경 내역을 최신순으로 표시합니다.</p></div></div></div>
    <div className="activity-card__body">
      {history.loading ? <SectionMessage message="처리 이력을 불러오는 중입니다." /> : history.error ? <SectionMessage message={history.error} retry={history.retry} /> : (history.data?.history.length ?? 0) === 0 ? <SectionMessage message="기록된 처리 이력이 없습니다." /> : (
        <div className="history-list">{history.data?.history.map((item) => <div className="history-item" key={item.id}><span className={`history-item__type history-item__type--${item.change_type}`}>{item.change_type === 'status' ? '상태' : '담당자'}</span><div><strong>{historyValue(item, 'old_value')} <span aria-hidden="true">→</span> {historyValue(item, 'new_value')}</strong><p>{item.changed_by?.name ?? '알 수 없음'} · {formatDate(item.changed_at)}</p></div></div>)}</div>
      )}
    </div>
  </article>

  return <section className="detail-grid ticket-detail-grid" aria-label="문의 상세 및 활동">
    <div className="detail-main-column">{mainContent}{commentsSection}{historySection}</div>
    <div className="detail-side-column">{sidebarContent}{attachmentsSection}</div>
  </section>
}
