import {ref} from 'vue'
import {api,type ModelRegistry} from './api'
export const modelRegistry=ref<ModelRegistry>({activeId:null,profiles:[]})
export async function loadModels(){modelRegistry.value=await api.models();return modelRegistry.value}
export function updateModels(value:ModelRegistry){modelRegistry.value=value;localStorage.setItem('snapmind-models-updated',String(Date.now())+'-'+Math.random())}
window.addEventListener('storage',event=>{if(event.key==='snapmind-models-updated')loadModels().catch(()=>{})})
