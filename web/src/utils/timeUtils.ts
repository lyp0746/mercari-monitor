export function parseUTCtoLocal(dateStr: string): Date {
  const trimmed = (dateStr || '').trim()

  if (!trimmed) {
    return new Date(NaN)
  }

  const normalized = trimmed.replace(' ', 'T')

  let date: Date

  if (/Z$|[+-]\d{2}:?\d{2}$/.test(normalized)) {
    date = new Date(normalized)
  } else {
    date = new Date(normalized + 'Z')
  }

  if (isNaN(date.getTime())) {
    return new Date(NaN)
  }

  return date
}

export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr || !dateStr.trim()) {
    return ''
  }

  const utcDate = parseUTCtoLocal(dateStr)

  if (isNaN(utcDate.getTime())) {
    return ''
  }

  const now = Date.now()
  const diff = now - utcDate.getTime()

  if (diff < 0) {
    return '刚刚'
  }

  const mins = Math.floor(diff / 60000)

  if (mins < 1) {
    return '刚刚'
  }

  if (mins < 60) {
    return `${mins}分钟前`
  }

  const hrs = Math.floor(mins / 60)

  if (hrs < 24) {
    return `${hrs}小时前`
  }

  const days = Math.floor(hrs / 24)

  if (days < 30) {
    return `${days}天前`
  }

  const months = Math.floor(days / 30)

  if (months < 12) {
    return `${months}个月前`
  }

  const years = Math.floor(months / 12)

  return `${years}年前`
}