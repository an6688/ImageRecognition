const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
const script=source.match(/<script>\s*('use strict';[\s\S]*?)<\/script>/)[1];
function launch({session={token:'test',analysisEnabled:true,analysis:{phase:'idle'}},blocked=false}={}){
 const els={},timers=new Map(),requests=[];let next=0,reloads=0,responses=[];
 for(const [,id] of source.matchAll(/\bid="([^"]+)"/g))els[id]={value:'',checked:false,hidden:false,textContent:'',innerHTML:'',
 style:{},attributes:{},clientWidth:750,clientHeight:590,offsetLeft:22,offsetTop:22,listeners:{},
 classList:{toggle(){}},setAttribute(k,v){this.attributes[k]=v},
 toggleAttribute(k,on){if(on)this.attributes[k]='';else delete this.attributes[k]},
 addEventListener(k,fn){this.listeners[k]=fn},click(){return this.listeners.click?.({})}};
 const frames=[{id:0,name:'old.png',path:'C:/old/old.png',decision:'no_elongation_flag',status:'ok',fraction:0,ratio:1,
 count:0,coverage:'all_detected_peaks',brightFraction:null,width:100,height:100,markers:[],examples:[],linear:'linear',enhanced:'enhanced'}];
 els['local-session'].textContent=JSON.stringify(session);
 els['report-data'].textContent=JSON.stringify({frames,summary:'test.csv',candidates:'stars.csv',versions:['test']});
 for(const [id,value] of Object.entries({filter:'all','review-filter':'all',sort:'sequence','rejected-action':'export',display:'linear','playback-display':'linear','playback-speed':'2',gain:'1',zoom:'1'}))els[id].value=value;
 const store=new Map(),context={
 fetch:async(route,options)=>{requests.push({route,...options});const response=responses.shift();if(response instanceof Error)throw response;if(!response)throw Error('Missing test response');return {ok:!response.error,json:async()=>response}},
 document:{getElementById:id=>els[id],querySelector:()=>({hidden:false}),createElement:()=>({click(){}})},
 window:{addEventListener(){},location:{reload(){reloads++}}},
 localStorage:{getItem:k=>store.get(k)||null,setItem(k,v){if(blocked)throw Error('storage blocked');store.set(k,v)}},
 Blob:class{},URL:{createObjectURL(){return 'blob:test'},revokeObjectURL(){}},
 clearTimeout:id=>timers.delete(id),setTimeout(fn){timers.set(++next,fn);return next}};
 vm.runInNewContext(script,context,{timeout:2000});
 return {els,requests,store,timers,reloads:()=>reloads,respond(...values){responses.push(...values)},
 async tick(){const first=timers.entries().next().value;assert.ok(first,'Expected a scheduled status check');timers.delete(first[0]);await first[1]()}};
}
(async()=>{
 const standalone=launch({session:null});
 await standalone.els['choose-folder'].click();
 assert.match(standalone.els['folder-status'].textContent,/Start AstroTrack/);
 assert.equal(standalone.requests.length,0);
 const app=launch(),e=app.els;
 e.keep.click();e.notes.value='Keep my notes';e.notes.listeners.input();
 app.respond({phase:'choosing',job:'a',message:'Choose folder'});
 await e['choose-folder'].click();
 assert.equal(app.requests[0].route,'/api/analysis/choose');
 assert.equal(app.requests[0].headers['X-Astro-Token'],'test');
 assert.equal(app.requests[0].body,'{}');
 assert.equal(e['choose-folder'].disabled,true);
 app.respond({phase:'previews',job:'a',message:'Preparing',done:2,total:8,folder:'C:/captures'});
 await app.tick();
 assert.equal(e['folder-progress'].value,2);
 assert.equal(e['folder-progress'].max,8);
 assert.equal(e['folder-path'].textContent,'C:/captures');
 app.respond({phase:'ready',job:'a',message:'Ready'}, {reload:true});
 await app.tick();
 assert.equal(app.reloads(),1);
 assert.equal(app.requests.at(-1).route,'/api/analysis/open');
 assert.match([...app.store.values()][0],/Keep my notes/);
 const cancel=launch();
 cancel.respond({phase:'analysis',job:'b',message:'Analyzing'});
 await cancel.els['choose-folder'].click();
 cancel.respond({phase:'cancelling',job:'b',message:'Cancelling'});
 await cancel.els['folder-cancel'].click();
 assert.equal(cancel.requests.at(-1).route,'/api/analysis/cancel');
 cancel.respond({phase:'cancelled',job:'b',message:'Cancelled'});
 await cancel.tick();
 assert.equal(cancel.reloads(),0);
 assert.equal(cancel.els['choose-folder'].disabled,false);
 const blocked=launch({blocked:true});
 blocked.respond({phase:'choosing',job:'c',message:'Choose'}, {phase:'ready',job:'c',message:'Ready'});
 await blocked.els['choose-folder'].click();await blocked.tick();
 assert.equal(blocked.reloads(),0);
 assert.match(blocked.els['folder-status'].textContent,/download a Review backup/);
 assert.equal(blocked.els['folder-open'].hidden,false);
 blocked.respond({reload:true});await blocked.els['folder-open'].click();
 assert.equal(blocked.reloads(),1);
 const resumed=launch({session:{token:'test',analysisEnabled:true,analysis:{phase:'analysis',job:'d',message:'Analyzing'}}});
 resumed.respond(new Error('offline'));await resumed.tick();
 assert.match(resumed.els['folder-status'].textContent,/not connected/);
 assert.equal(resumed.els['folder-retry'].hidden,false);
 resumed.respond({phase:'error',job:'d',message:'No readable images'});
 await resumed.els['folder-retry'].click();
 assert.equal(resumed.els['folder-status'].textContent,'No readable images');
 assert.equal(resumed.els['choose-folder'].disabled,false);
 console.log('Folder controls passed: local picker, progress, same-tab switch, preserved notes, cancellation, storage failure, reconnect and standalone guidance.');
})().catch(error=>{console.error(error);process.exitCode=1});
