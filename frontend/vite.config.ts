import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue()], server: { proxy: { '/api': {target:'http://127.0.0.1:'+(process.env.SNAPMIND_BACKEND_PORT||'8765'),ws:true} },watch:{ignored:['**/src-tauri/**','**/.desktop-runtime/**','**/backend/data/**']} } })
