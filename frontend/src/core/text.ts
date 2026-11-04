/** Canvas 文本折行：中文逐字断行，连续的字母数字作为一个词不拆开 */

const TOKEN = /[A-Za-z0-9_\-.]+ ?|[\s\S]/gu

export function wrapLines(
  text: string,
  maxWidth: number,
  measure: (s: string) => number,
  maxLines = Infinity
): string[] {
  const lines: string[] = []
  for (const para of text.split('\n')) {
    const tokens = para.match(TOKEN) ?? ['']
    let line = ''
    for (const tok of tokens) {
      if (line && measure(line + tok) > maxWidth) {
        lines.push(line)
        line = tok.trimStart()
      } else {
        line += tok
      }
    }
    lines.push(line)
  }
  if (lines.length <= maxLines) return lines
  const kept = lines.slice(0, maxLines)
  let lastLine = kept[maxLines - 1]
  while (lastLine && measure(lastLine + '…') > maxWidth) lastLine = Array.from(lastLine).slice(0, -1).join('')
  kept[maxLines - 1] = lastLine + '…'
  return kept
}
