/**
 * 图标名 → CSS 类名（与 icons.generated.scss 对应）。
 * 单独成文件：运行时只需要这个函数，不能把 SVG 源（icons.ts）打进小程序包。
 */

import type { IconName } from './icons'

export const iconClass = (name: IconName) => `icon-${name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`
