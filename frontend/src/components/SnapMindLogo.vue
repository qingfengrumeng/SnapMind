<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 32 })
</script>
<template><img class="snapmind-logo" src="/snapmind-logo.svg" :width="size" :height="size" alt="" aria-hidden="true" draggable="false"/></template>
