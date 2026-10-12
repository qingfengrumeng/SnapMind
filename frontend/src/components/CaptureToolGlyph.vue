<script setup lang="ts">
// Screenshot annotation symbols matching the supplied toolbar reference.
defineProps<{name:'sequence'|'translate'}>()
</script>
<template>
 <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
  <g v-if="name==='sequence'">
   <circle cx="12" cy="12" r="9"/>
   <path d="m9.5 8.5 2.5-2v11"/>
  </g>
  <g v-else>
   <path d="M3 4.5h8v5H3zM7 2v10"/>
   <path d="M14 3h3a3 3 0 0 1 3 3v3m-2-2 2 2 2-2"/>
   <path d="M9 21H6a3 3 0 0 1-3-3v-3m-2 2 2-2 2 2"/>
   <path d="m12 22 5-9 5 9m-8.5-3h7"/>
  </g>
 </svg>
</template>
