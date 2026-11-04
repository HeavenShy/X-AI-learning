/**
 * WXSS 兼容性守护：WXSS 不支持 :root / * / 属性选择器。
 * 任何一条规则的选择器列表里混入不支持的选择器，整条规则会被丢弃——
 * 曾因 `page, :root { --ink: ... }` 导致所有 CSS 变量失效、模拟器里页面近乎空白。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

function scssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return scssFiles(p)
    return p.endsWith('.scss') ? [p] : []
  })
}

/** 取出每条规则的选择器部分（去掉注释与声明块，足够做静态检查） */
function selectorLists(source: string): string[] {
  const noComments = source.replace(/\/\*[\s\S]*?\*\//g, '')
  return Array.from(noComments.matchAll(/([^{};]+)\{/g))
    .map((m) => m[1].trim())
    .filter((s) => s && !s.startsWith('@'))
}

const files = scssFiles(join(__dirname, '..', 'src'))

test('能找到样式文件', () => {
  assert.ok(files.length >= 8)
})

for (const file of files) {
  test(`WXSS 兼容：${file.split(/[\\/]src[\\/]/)[1]}`, () => {
    for (const sel of selectorLists(readFileSync(file, 'utf8'))) {
      const parts = sel.split(',').map((s) => s.trim())
      // :root 只能单独成一条规则（给 H5 用），不能和其他选择器写在一起
      if (parts.some((p) => p === ':root')) {
        assert.deepEqual(parts, [':root'], `“${sel}” 把 :root 和其他选择器写在了一起，WXSS 会丢弃整条规则`)
      }
      assert.ok(!/(^|[\s,>+~])\*(?![=])/.test(sel), `“${sel}” 使用了 WXSS 不支持的 * 选择器`)
      assert.ok(!/\[[^\]]+\]/.test(sel), `“${sel}” 使用了 WXSS 不支持的属性选择器`)
    }
  })
}
