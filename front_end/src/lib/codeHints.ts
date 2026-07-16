/**
 * Extract code-identifier-shaped tokens from free text (a finding's title,
 * why_it_matters, suggested_fix, etc.) so we can locate the likely-relevant
 * lines in a source file even when the LLM emits inaccurate `path:line`
 * coordinates.
 *
 * Identifiers we accept:
 *  - UPPER_SNAKE_CASE with at least one `_` and len >= 4
 *  - snake_case with at least one `_` and len >= 5
 *  - PascalCase with at least 2 capital-run segments and len >= 6
 *    (e.g. `AttributeError`, `BackendSentryDsn`)
 *
 * Single-word common English / single-token camelCase names (`settings`,
 * `update`, `Config`) are intentionally rejected — they would match too
 * many lines and obscure the real signal.
 */
export function extractCodeIdentifiers(text: string | null | undefined): string[] {
  if (!text) return []
  const set = new Set<string>()
  for (const m of text.matchAll(/\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/g)) {
    if (m[0].length >= 4) set.add(m[0])
  }
  for (const m of text.matchAll(/\b[a-z][a-z0-9]*_[a-z0-9_]+\b/g)) {
    if (m[0].length >= 5) set.add(m[0])
  }
  for (const m of text.matchAll(/\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b/g)) {
    if (m[0].length >= 6) set.add(m[0])
  }
  return Array.from(set)
}

export function extractCodeIdentifiersFrom(...texts: (string | null | undefined)[]): string[] {
  const set = new Set<string>()
  for (const t of texts) {
    for (const id of extractCodeIdentifiers(t)) set.add(id)
  }
  return Array.from(set)
}
