<script setup lang="ts">
import { computed } from 'vue'
import {AudioLines,Mic,Keyboard,Send,PhoneCall,User,Volume2,Pause,ArrowLeft} from 'lucide-vue-next'
import ChatBubbleIcon from './ChatBubbleIcon.vue'
import { Braces, NotebookPen, RefreshCw, MessageCircle, QrCode, Link, ScanText, Highlighter, Eraser, WandSparkles, Layers2, Redo2, ClipboardCheck, RotateCw, RotateCcw, Pipette } from 'lucide-vue-next'
import { MessageSquareText, ScanEye, ScanLine, Sparkles, Plus, ArrowUpRight, ChevronDown, ChevronRight, Search, Clock3, MoreHorizontal, Settings2, CircleHelp, ImagePlus, Images, Upload, Download, Copy, Check, X, ArrowUp, Paperclip, MousePointer2, Square, MoveUpRight, Pencil, Type, Grid2X2, Undo2, Crop, ZoomIn, ZoomOut, Maximize2, Pin, Trash2, FileText, Table2, Sigma, Languages, Terminal, PanelLeft, Play, SquarePen, LoaderCircle, CircleCheck, BookOpen, ExternalLink, GripVertical, CircleAlert, Sun, Monitor } from 'lucide-vue-next'
const props=defineProps<{name:string; size?:number}>()
const icons: Record<string,typeof ScanLine> = { annotate:MessageSquareText, detect:ScanEye, scan:ScanLine, sparkles:Sparkles, plus:Plus, link:ArrowUpRight, down:ChevronDown, right:ChevronRight, search:Search, clock:Clock3, more:MoreHorizontal, settings:Settings2, help:CircleHelp, image:ImagePlus, images:Images, upload:Upload, download:Download, copy:Copy, check:Check, close:X, send:ArrowUp, attach:Paperclip, cursor:MousePointer2, rect:Square, arrow:MoveUpRight, pen:Pencil, text:Type, mosaic:Grid2X2, undo:Undo2, crop:Crop, zoomIn:ZoomIn, zoomOut:ZoomOut, fit:Maximize2, pin:Pin, trash:Trash2, file:FileText, table:Table2, formula:Sigma, translate:Languages, terminal:Terminal, panel:PanelLeft, play:Play, edit:SquarePen, loading:LoaderCircle, success:CircleCheck, book:BookOpen, external:ExternalLink, grip:GripVertical, alert:CircleAlert, sun:Sun, monitor:Monitor }
Object.assign(icons,{code:Braces,paper:NotebookPen,refresh:RefreshCw,chat:MessageCircle,qr:QrCode,entity:Link,ocr:ScanText,offline:ScanText,highlight:Highlighter,eraser:Eraser,heal:WandSparkles,lift:Layers2,redo:Redo2,exam:ClipboardCheck,rotate:RotateCw,rotateLeft:RotateCcw,pipette:Pipette})
Object.assign(icons,{voice:AudioLines,microphone:Mic,keyboard:Keyboard,paperSend:Send,voiceCall:PhoneCall,user:User,speaker:Volume2,pause:Pause,back:ArrowLeft})
const icon=computed(()=>icons[props.name] || Sparkles)
</script>
<template><ChatBubbleIcon v-if="name==='aiChat'" :size="size||24"/><component v-else :is="icon" :size="size || 18" :stroke-width="1.7" aria-hidden="true"/></template>
