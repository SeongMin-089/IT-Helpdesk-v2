export function formatDate(value: string | null) {
  if (!value) return '-'
  const normalized = value.replace('T', ' ')
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
}

export function roleLabel(role: 'employee' | 'agent') {
  return role === 'agent' ? 'IT 담당자' : '일반 직원'
}

const stageLabels: Record<string, string> = {
  new: '접수',
  assigned: '배정',
  'in progress': '처리 중',
  resolved: '해결',
  done: '종료',
}

export function stageLabel(name: string | null | undefined) {
  if (!name) return '미지정'
  return stageLabels[name.trim().toLowerCase()] ?? name
}
