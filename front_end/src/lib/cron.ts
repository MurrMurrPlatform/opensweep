/** Tiny 5-field crontab helpers for the human-friendly schedule builder.
 *
 * Scope is deliberately small: parse/describe the shapes the builder can
 * produce (hourly interval, daily, weekly, monthly) and fall back to the raw
 * expression for anything fancier — correctness over cron-completeness.
 */

export interface CronParts {
  minute: string
  hour: string
  dom: string
  month: string
  dow: string
}

export const WEEKDAYS = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
]

export function parseCron(expr: string): CronParts | null {
  const fields = expr.trim().split(/\s+/)
  if (fields.length !== 5) return null
  const [minute, hour, dom, month, dow] = fields
  return { minute, hour, dom, month, dow }
}

const isNum = (s: string) => /^\d+$/.test(s)

const pad = (n: number) => String(n).padStart(2, '0')

function timeLabel(hour: string, minute: string): string {
  return `${pad(Number(hour))}:${pad(Number(minute))}`
}

/** The builder's four shapes, or null when the expression is anything else. */
export type CronShape =
  | { kind: 'hourly'; everyHours: number; minute: number }
  | { kind: 'daily'; hour: number; minute: number }
  | { kind: 'weekly'; weekday: number; hour: number; minute: number }
  | { kind: 'monthly'; day: number; hour: number; minute: number }

export function cronShape(expr: string): CronShape | null {
  const p = parseCron(expr)
  if (!p || p.month !== '*') return null
  const everyHours = /^\*\/(\d+)$/.exec(p.hour)
  if (isNum(p.minute) && everyHours && p.dom === '*' && p.dow === '*') {
    return { kind: 'hourly', everyHours: Number(everyHours[1]), minute: Number(p.minute) }
  }
  if (!isNum(p.minute) || !isNum(p.hour)) return null
  if (p.dom === '*' && p.dow === '*') {
    return { kind: 'daily', hour: Number(p.hour), minute: Number(p.minute) }
  }
  if (p.dom === '*' && isNum(p.dow) && Number(p.dow) <= 7) {
    return { kind: 'weekly', weekday: Number(p.dow) % 7, hour: Number(p.hour), minute: Number(p.minute) }
  }
  if (isNum(p.dom) && p.dow === '*') {
    return { kind: 'monthly', day: Number(p.dom), hour: Number(p.hour), minute: Number(p.minute) }
  }
  return null
}

export function buildCron(shape: CronShape): string {
  switch (shape.kind) {
    case 'hourly':
      return `${shape.minute} */${shape.everyHours} * * *`
    case 'daily':
      return `${shape.minute} ${shape.hour} * * *`
    case 'weekly':
      return `${shape.minute} ${shape.hour} * * ${shape.weekday}`
    case 'monthly':
      return `${shape.minute} ${shape.hour} ${shape.day} * *`
  }
}

function ordinal(n: number): string {
  const rem10 = n % 10
  const rem100 = n % 100
  if (rem10 === 1 && rem100 !== 11) return `${n}st`
  if (rem10 === 2 && rem100 !== 12) return `${n}nd`
  if (rem10 === 3 && rem100 !== 13) return `${n}rd`
  return `${n}th`
}

/** "Every day at 02:00 UTC" — or '' when the expression is beyond the
 *  builder's shapes (the UI then shows the raw crontab). */
export function describeCron(expr: string): string {
  const shape = cronShape(expr)
  if (!shape) return ''
  switch (shape.kind) {
    case 'hourly': {
      const every = shape.everyHours === 1 ? 'hour' : `${shape.everyHours} hours`
      const at = shape.minute ? ` at :${pad(shape.minute)}` : ''
      return `Every ${every}${at} UTC`
    }
    case 'daily':
      return `Every day at ${timeLabel(String(shape.hour), String(shape.minute))} UTC`
    case 'weekly':
      return `Every ${WEEKDAYS[shape.weekday]} at ${timeLabel(String(shape.hour), String(shape.minute))} UTC`
    case 'monthly':
      return `Monthly on the ${ordinal(shape.day)} at ${timeLabel(String(shape.hour), String(shape.minute))} UTC`
  }
}
