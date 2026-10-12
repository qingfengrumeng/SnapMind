// Mono PCM16 LE. Resample the AudioContext rate to the configured ASR rate.
class SnapMindPcm extends AudioWorkletProcessor {
 constructor(options){super();this.targetRate=options.processorOptions.sampleRate;this.phase=0;this.sum=0;this.count=0;this.samples=[];this.stopped=false;this.port.onmessage=event=>{if(event.data==='flush'){this.stopped=true;this.flush();this.port.postMessage({flushed:true})}}}
 flush(){if(!this.samples.length)return;const data=new ArrayBuffer(this.samples.length*2),view=new DataView(data);this.samples.forEach((value,i)=>view.setInt16(i*2,value,true));this.samples=[];this.port.postMessage(data,[data])}
 process(inputs,outputs){for(const channel of outputs[0]||[])channel.fill(0);if(this.stopped)return true;const channels=inputs[0];if(!channels?.length)return true;for(let i=0;i<channels[0].length;i++){let value=0;for(const channel of channels)value+=channel[i];this.sum+=value/channels.length;this.count++;this.phase+=this.targetRate/sampleRate;if(this.phase>=1){const mean=Math.max(-1,Math.min(1,this.sum/this.count));this.samples.push(Math.round(mean*(mean<0?32768:32767)));this.phase-=1;this.sum=0;this.count=0;if(this.samples.length>=this.targetRate/20)this.flush()}}return true}
}
registerProcessor('snapmind-pcm',SnapMindPcm)
