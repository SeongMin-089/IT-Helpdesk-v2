const API_DATETIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?(Z|[+-]\d{2}:?\d{2})?$/i
const KST_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function parseApiDate(value: string) {
  const match = API_DATETIME_PATTERN.exec(value.trim())
  if (!match) return null

  const [, yearText, monthText, dayText, hourText, minuteText, secondText = '0', fraction = '', timezone] = match
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const hour = Number(hourText)
  const minute = Number(minuteText)
  const second = Number(secondText)
  const millisecond = Number(fraction.padEnd(3, '0').slice(0, 3))
  const calendarCheck = new Date(Date.UTC(year, month - 1, day, hour, minute, second, millisecond))

  if (
    calendarCheck.getUTCFullYear() !== year
    || calendarCheck.getUTCMonth() !== month - 1
    || calendarCheck.getUTCDate() !== day
    || calendarCheck.getUTCHours() !== hour
    || calendarCheck.getUTCMinutes() !== minute
    || calendarCheck.getUTCSeconds() !== second
  ) return null

  if (!timezone || timezone.toUpperCase() === 'Z') return calendarCheck

  const offsetMatch = /^([+-])(\d{2}):?(\d{2})$/.exec(timezone)
  if (!offsetMatch) return null
  const offsetHours = Number(offsetMatch[2])
  const offsetMinutes = Number(offsetMatch[3])
  if (offsetHours > 23 || offsetMinutes > 59) return null

  const direction = offsetMatch[1] === '+' ? 1 : -1
  const offset = direction * ((offsetHours * 60) + offsetMinutes) * 60_000
  return new Date(calendarCheck.getTime() - offset)
}

export function formatDate(value: string | null | undefined) {
  if (typeof value !== 'string' || !value.trim()) return '-'
  const date = parseApiDate(value)
  if (!date) return '-'

  const parts = Object.fromEntries(
    KST_FORMATTER.formatToParts(date).map(({ type, value: partValue }) => [type, partValue]),
  )
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`
}

export function roleLabel(role: 'employee' | 'agent') {
  return role === 'agent' ? 'IT 담당자' : '일반 직원'
}

const stageLabels: Record<string, string> = {
  new: '접수',
  assigned: '담당자 확인',
  'in progress': '처리 중',
  resolved: '해결',
  done: '종료',
}

export function stageLabel(name: string | null | undefined) {
  if (!name) return '미지정'
  return stageLabels[name.trim().toLowerCase()] ?? name
}
