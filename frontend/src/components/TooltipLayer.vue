<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import ToolShortcutHints from './ToolShortcutHints.vue'

const id = useId(), visible = ref(false), bubble = ref<HTMLElement>()
const label = ref(''), detail = ref(''), shortcut = ref('')
const position = ref({ left: 0, top: 0, arrow: 20, side: 'above', ready: false })
let target: HTMLButtonElement | undefined, timer: ReturnType<typeof setTimeout> | undefined
let savedTitle: string | null = null, describedBy: string | null = null

function hide() {
  if (timer) clearTimeout(timer)
  timer = undefined
  visible.value = false
  if (target) {
    if (savedTitle !== null && !target.hasAttribute('title')) target.setAttribute('title', savedTitle)
    if (describedBy === null) target.removeAttribute('aria-describedby')
    else target.setAttribute('aria-describedby', describedBy)
  }
  target = undefined
  savedTitle = null
  describedBy = null
}
function candidate(node: EventTarget | null) {
  if (!(node instanceof Element)) return
  const button = node.closest<HTMLButtonElement>('button')
  if (!button || button.disabled || button.hasAttribute('data-capture-tool') || button.closest('[data-tooltip-disabled]') || button.matches('.capture-handle,.native-resize,.float-resize,.swatch,.stroke-choice')) return
  if (button === target) return button
  if (button.hasAttribute('data-tooltip') || button.hasAttribute('title') || button.hasAttribute('aria-label') && !button.textContent?.trim()) return button
}
async function show(button: HTMLButtonElement) {
  if (target !== button || !button.isConnected) { hide(); return }
  visible.value = true
  position.value.ready = false
  button.setAttribute('aria-describedby', [describedBy, id].filter(Boolean).join(' '))
  await nextTick()
  if (target !== button || !bubble.value) return
  const anchor = button.getBoundingClientRect(), box = bubble.value.getBoundingClientRect()
  const gap = 10, margin = 10
  const above = anchor.top >= box.height + gap + margin
  const left = Math.max(margin, Math.min(innerWidth - box.width - margin, anchor.left + anchor.width / 2 - box.width / 2))
  const top = above ? anchor.top - box.height - gap : Math.min(innerHeight - box.height - margin, anchor.bottom + gap)
  position.value = { left, top: Math.max(margin, top), arrow: Math.max(16, Math.min(box.width - 16, anchor.left + anchor.width / 2 - left)), side: above ? 'above' : 'below', ready: true }
}
function queue(button: HTMLButtonElement, keyboard = false) {
  if (target === button) return
  hide()
  target = button
  savedTitle = button.getAttribute('title')
  describedBy = button.getAttribute('aria-describedby')
  const text = button.dataset.tooltip || savedTitle || button.getAttribute('aria-label') || ''
  const keys = text.match(/(?:[·\s]+)((?:Ctrl|Alt|Shift|Enter|Esc)[+\w\s]*)$/)
  label.value = keys ? text.slice(0, keys.index).trim() : text
  detail.value = button.dataset.tooltipDetail || ''
  shortcut.value = button.dataset.shortcut || keys?.[1]?.replace(/\s+/g, '') || ''
  // Suppress the OS title bubble while our accessible tooltip is active.
  button.removeAttribute('title')
  timer = setTimeout(() => show(button), keyboard ? 80 : 320)
}
function over(event: PointerEvent) { const button = candidate(event.target); if (button) queue(button); else hide() }
function out(event: PointerEvent) { if (target && !(event.relatedTarget instanceof Node && target.contains(event.relatedTarget))) hide() }
function focus(event: FocusEvent) { const button = candidate(event.target); if (button) queue(button, true) }
function escape(event: KeyboardEvent) { if (event.key === 'Escape') hide() }

onMounted(() => {
  document.addEventListener('pointerover', over)
  document.addEventListener('pointerout', out)
  document.addEventListener('focusin', focus)
  document.addEventListener('focusout', hide)
  document.addEventListener('pointerdown', hide, true)
  document.addEventListener('keydown', escape)
  window.addEventListener('scroll', hide, true)
  window.addEventListener('resize', hide)
  window.addEventListener('blur', hide)
})
onBeforeUnmount(() => {
  hide()
  document.removeEventListener('pointerover', over)
  document.removeEventListener('pointerout', out)
  document.removeEventListener('focusin', focus)
  document.removeEventListener('focusout', hide)
  document.removeEventListener('pointerdown', hide, true)
  document.removeEventListener('keydown', escape)
  window.removeEventListener('scroll', hide, true)
  window.removeEventListener('resize', hide)
  window.removeEventListener('blur', hide)
})
</script>

<template>
 <ToolShortcutHints/>
 <Teleport to="body"><div v-if="visible" :id="id" ref="bubble" role="tooltip" class="snapmind-tooltip" :data-side="position.side" :style="{left:position.left+'px',top:position.top+'px',visibility:position.ready?'visible':'hidden','--tooltip-arrow':position.arrow+'px'}"><div class="tooltip-heading"><span>{{label}}</span><kbd v-if="shortcut">{{shortcut}}</kbd></div><p v-if="detail">{{detail}}</p></div></Teleport>
</template>
