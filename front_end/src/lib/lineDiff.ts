// Minimal line-based diff (LCS) for rendering DocEdit proposals against the
// current body. No dependency — good enough for human review of markdown pages.

export interface DiffLine {
  type: 'same' | 'add' | 'del'
  text: string
}

export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split('\n')
  const b = after.split('\n')
  const n = a.length
  const m = b.length

  // LCS table (guard against pathological sizes: fall back to del-all/add-all).
  if (n * m > 2_000_000) {
    return [
      ...a.map((text): DiffLine => ({ type: 'del', text })),
      ...b.map((text): DiffLine => ({ type: 'add', text })),
    ]
  }

  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const out: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ type: 'same', text: a[i] })
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      out.push({ type: 'del', text: a[i] })
      i++
    } else {
      out.push({ type: 'add', text: b[j] })
      j++
    }
  }
  while (i < n) out.push({ type: 'del', text: a[i++] })
  while (j < m) out.push({ type: 'add', text: b[j++] })
  return out
}

/** Collapse long runs of unchanged lines to keep diffs reviewable. */
export function collapseContext(lines: DiffLine[], context = 3): (DiffLine | { type: 'skip'; count: number })[] {
  const out: (DiffLine | { type: 'skip'; count: number })[] = []
  let run: DiffLine[] = []
  const flush = (isEnd: boolean, isStart: boolean) => {
    const keepHead = isStart ? 0 : context
    const keepTail = isEnd ? 0 : context
    if (run.length <= keepHead + keepTail + 1) {
      out.push(...run)
    } else {
      out.push(...run.slice(0, keepHead))
      out.push({ type: 'skip', count: run.length - keepHead - keepTail })
      out.push(...run.slice(run.length - keepTail))
    }
    run = []
  }
  let seenChange = false
  for (const line of lines) {
    if (line.type === 'same') {
      run.push(line)
    } else {
      if (run.length) flush(false, !seenChange)
      seenChange = true
      out.push(line)
    }
  }
  if (run.length) flush(true, !seenChange)
  return out
}
