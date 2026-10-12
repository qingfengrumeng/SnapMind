<script setup lang="ts">
defineProps<{size?:number}>()
</script>
<template>
 <svg :width="size||24" :height="size||24" viewBox="0 0 24 24" fill="none" aria-hidden="true" class="ai-chat-bubble-icon" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3.25c-4.92 0-8.75 3.33-8.75 7.65 0 1.61.54 3.08 1.49 4.3l-1.12 4.46a.45.45 0 0 0 .58.53l4.2-1.41c1.1.42 2.32.64 3.6.64 4.92 0 8.75-3.33 8.75-7.65S16.92 3.25 12 3.25Z" stroke-width="1.7"/>
  <g stroke-width="1.5">
   <line x1="7.8" y1="7.7" x2="15.4" y2="7.7"/>
   <line x1="7.8" y1="11" x2="13.7" y2="11"/>
   <line x1="7.8" y1="14.3" x2="11.9" y2="14.3"/>
  </g>
 </svg>
</template>
