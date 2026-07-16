// Shared diff model for DiffView: turns unified-patch text (backend
// `/runs/{uid}/changes`) or an old/new string pair (Edit/Write tool inputs)
// into a flat list of renderable rows with dual line numbers.
import { parsePatch, structuredPatch } from 'diff'

export type DiffRowType = 'add' | 'del' | 'context' | 'hunk'

export interface DiffRow {
  type: DiffRowType
  /** Line number in the old file ('' for adds/hunk headers). */
  oldNo: number | ''
  /** Line number in the new file ('' for dels/hunk headers). */
  newNo: number | ''
  /** Line content without the +/-/space prefix; hunk header text for 'hunk'. */
  text: string
}

export interface DiffStats {
  additions: number
  deletions: number
}

interface HunkLike {
  oldStart: number
  newStart: number
  lines: string[]
}

function rowsFromHunks(hunks: HunkLike[]): DiffRow[] {
  const rows: DiffRow[] = []
  for (const hunk of hunks) {
    let oldNo = hunk.oldStart
    let newNo = hunk.newStart
    rows.push({
      type: 'hunk',
      oldNo: '',
      newNo: '',
      text: `@@ -${hunk.oldStart} +${hunk.newStart} @@`,
    })
    for (const line of hunk.lines) {
      const marker = line[0]
      const text = line.slice(1)
      if (marker === '+') {
        rows.push({ type: 'add', oldNo: '', newNo: newNo++, text })
      } else if (marker === '-') {
        rows.push({ type: 'del', oldNo: oldNo++, newNo: '', text })
      } else if (marker === '\\') {
        // "\ No newline at end of file" — noise in a UI diff.
        continue
      } else {
        rows.push({ type: 'context', oldNo: oldNo++, newNo: newNo++, text })
      }
    }
  }
  return rows
}

/** Rows for a unified diff patch (single file; extra files are ignored). */
export function rowsFromPatch(patch: string): DiffRow[] {
  if (!patch.trim()) return []
  try {
    const files = parsePatch(patch)
    if (!files.length) return []
    return rowsFromHunks(files[0].hunks)
  } catch {
    // Not a parseable unified diff — show it verbatim rather than nothing.
    return patch
      .split('\n')
      .map((text) => ({ type: 'context' as const, oldNo: '', newNo: '', text }))
  }
}

/** Rows for an old→new string pair (client-side diff of tool inputs). */
export function rowsFromStrings(oldText: string, newText: string, context = 3): DiffRow[] {
  const patch = structuredPatch('a', 'b', oldText ?? '', newText ?? '', '', '', { context })
  return rowsFromHunks(patch.hunks)
}

export function diffStats(rows: DiffRow[]): DiffStats {
  let additions = 0
  let deletions = 0
  for (const row of rows) {
    if (row.type === 'add') additions++
    else if (row.type === 'del') deletions++
  }
  return { additions, deletions }
}
