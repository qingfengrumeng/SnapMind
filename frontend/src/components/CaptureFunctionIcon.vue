<script setup lang="ts">
import {Circle} from 'lucide-vue-next'
import Icon from './Icon.vue'
import CaptureToolGlyph from './CaptureToolGlyph.vue'
import type {CaptureToolId} from '../tool-shortcuts'
defineProps<{tool:CaptureToolId}>()
const icons:Partial<Record<CaptureToolId,string>>={objects:'cursor',eyedropper:'pipette',scroll:'crop',chat:'aiChat',clear:'trash',save:'download',cancel:'close',copy:'check'}
</script>
<template>
 <Circle v-if="tool==='ellipse'" :size="24" :stroke-width="1.7" aria-hidden="true"/>
 <CaptureToolGlyph v-else-if="tool==='number'||tool==='translate'" :name="tool==='number'?'sequence':'translate'"/>
 <svg v-else-if="tool==='blur'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4"/><rect x="8" y="8" width="8" height="8" rx="1.5"/></svg>
 <Icon v-else :name="icons[tool]||tool" :size="24"/>
</template>
