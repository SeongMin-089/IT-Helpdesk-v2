export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function errorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) {
    return fallback
  }
  const detail = payload.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        item && typeof item === 'object' && 'msg' in item ? String(item.msg) : '',
      )
      .filter(Boolean)
      .join(' ')
  }
  return fallback
}

export async function apiRequest<T>(path: string, options: RequestInit = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: 'include',
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })

  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const fallback =
      response.status === 401
        ? '로그인이 필요합니다.'
        : response.status === 403
          ? '이 작업을 수행할 권한이 없습니다.'
          : response.status === 422
            ? '입력한 내용을 확인해 주세요.'
            : '요청을 처리하지 못했습니다.'
    throw new ApiError(response.status, errorMessage(payload, fallback))
  }
  return payload as T
}

export function toQuery(params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value))
  })
  const text = query.toString()
  return text ? `?${text}` : ''
}
