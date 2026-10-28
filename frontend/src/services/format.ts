export function formatDate(value: string | null) {
  if (!value) return '-'
  const normalized = value.replace('T', ' ')
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
}

export function roleLabel(role: 'employee' | 'agent') {
  return role === 'agent' ? 'IT 담당자' : '일반 직원'
}
