import { AlertCircle, Inbox } from 'lucide-react'

export function PageLoader({ label = '데이터를 불러오는 중입니다.' }: { label?: string }) {
  return (
    <div className="page-state" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="page-state page-state--error" role="alert">
      <AlertCircle size={28} aria-hidden="true" />
      <p>{message}</p>
      {onRetry && (
        <button className="button button--secondary" type="button" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="page-state">
      <Inbox size={30} aria-hidden="true" />
      <p>{message}</p>
    </div>
  )
}
