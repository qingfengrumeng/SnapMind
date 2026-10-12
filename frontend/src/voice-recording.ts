import type {VoiceMessage} from './types'

export function pcmRecording(frames:ArrayBuffer[],sampleRate:number):VoiceMessage{
 const size=frames.reduce((n,frame)=>n+frame.byteLength,0)
 if(![8000,16000].includes(sampleRate)||!size||size%2||size>sampleRate*2*120)throw Error('录音内容无效或超过两分钟，请重新录制')
 const bytes=new Uint8Array(44+size),view=new DataView(bytes.buffer)
 const write=(offset:number,text:string)=>{for(let i=0;i<text.length;i++)view.setUint8(offset+i,text.charCodeAt(i))}
 write(0,'RIFF');view.setUint32(4,36+size,true);write(8,'WAVE');write(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,sampleRate,true);view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);write(36,'data');view.setUint32(40,size,true)
 let offset=44;for(const frame of frames){bytes.set(new Uint8Array(frame),offset);offset+=frame.byteLength}
 const count=size/2,bins=Math.min(32,count),waveform=[]
 for(let bin=0;bin<bins;bin++){let sum=0;const start=Math.floor(bin*count/bins),end=Math.floor((bin+1)*count/bins);for(let i=start;i<end;i++){const value=view.getInt16(44+i*2,true)/32768;sum+=value*value}waveform.push(Math.min(1,Math.sqrt(sum/(end-start))))}
 let raw='';for(let i=0;i<bytes.length;i+=16384)raw+=String.fromCharCode(...bytes.subarray(i,i+16384))
 return {data:'data:audio/wav;base64,'+btoa(raw),duration:count/sampleRate,waveform}
}
