const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
const script=source.match(/<script>\s*('use strict';[\s\S]*?)<\/script>/)[1];
function start(count=4){
 const frames=Array.from({length:count},(_,id)=>({id,name:'capture-'+String(id).padStart(4,'0')+'.png',
 path:'C:/images/'+id+'.png',decision:'no_elongation_flag',status:id===2?'error':'ok',error:id===2?'Unreadable exposure':'',
 width:100,height:100,count:0,fraction:0,ratio:1,coverage:'all_detected_peaks',brightFraction:null,
 markers:[],examples:[],linear:'linear-'+id,enhanced:'enhanced-'+id})).reverse();
 const els={},windowEvents={},documentEvents={},timers=new Map();let serial=0;
 for(const [,id] of source.matchAll(/\bid="([^"]+)"/g))els[id]={value:'',open:false,hidden:false,checked:false,textContent:'',innerHTML:'',
 style:{},attributes:{},clientWidth:750,clientHeight:590,listeners:{},classList:{toggle(){}},
 setAttribute(k,v){this.attributes[k]=v},toggleAttribute(k,on){if(on)this.attributes[k]='';else delete this.attributes[k]},
 addEventListener(k,fn){(this.listeners[k]??=[]).push(fn)},async click(){for(const fn of this.listeners.click||[])await fn({})}};
 els['report-data'].textContent=JSON.stringify({frames,summary:'test.csv',candidates:'stars.csv',versions:['test']});
 els['local-session'].textContent='null';els['playback-stage'].hidden=true;
 els['playback-image'].decode=async()=>{};
 for(const [id,value] of Object.entries({filter:'all','review-filter':'all','rejected-action':'export',sort:'sequence',
 display:'linear','playback-display':'linear','playback-speed':'2',gain:'1',zoom:'1'}))els[id].value=value;
 const context={document:{getElementById:id=>els[id],querySelector:()=>({hidden:false}),
 addEventListener(k,fn){documentEvents[k]=fn},hidden:false},
 window:{addEventListener(k,fn){windowEvents[k]=fn}},
 localStorage:{getItem(){return null},setItem(){}},
 setTimeout(fn,delay){const id=++serial;timers.set(id,{fn,delay});return id},
 clearTimeout(id){timers.delete(id)}};
 vm.runInNewContext(script,context,{timeout:2000});
 return {els,timers,context,documentEvents,windowEvents,
 async fire(id,event){for(const fn of els[id].listeners[event]||[])await fn({})},
 async tick(){assert.equal(timers.size,1);const [id,timer]=timers.entries().next().value;timers.delete(id);timer.fn();await Promise.resolve();await Promise.resolve()}}
}
(async()=>{
 const app=start(),e=app.els;
 assert.match(source,/<details id="playback-panel" class="playback-panel">/);
 assert.equal(e['playback-panel'].open,false,'Playback starts collapsed');

 await e['playback-play'].click();
 assert.equal(e['playback-image'].src,'linear-0','Playback follows filename order, not input/review sort order');
 assert.equal(e.keep.disabled,true,'Pause before making decisions in the inspector');
 app.windowEvents.keydown({key:'r',target:{tagName:'BODY'},preventDefault(){}});
 assert.equal(e.reviewed.textContent,0,'Review shortcuts must also be disabled during playback');

 assert.match(e['playback-caption'].textContent,/1 \/ 4/);
 assert.equal([...app.timers.values()][0].delay,500);
 await app.tick();assert.equal(e['playback-image'].src,'linear-1');
 e['playback-speed'].value='5';await app.fire('playback-speed','change');
 assert.equal(app.timers.size,1);assert.equal([...app.timers.values()][0].delay,200);
 await app.tick();
 assert.equal(e['playback-error'].hidden,false);assert.match(e['playback-error'].textContent,/Unreadable/);
 assert.match(e['playback-caption'].textContent,/3 \/ 4/,'Failed exposures remain in the sequence');
 await app.tick();assert.equal(e['playback-image'].src,'linear-3');
 assert.equal(app.timers.size,0);assert.equal(e['playback-play'].textContent,'Play captures');
 assert.equal(e.keep.disabled,false);
 e['playback-position'].value='1';await app.fire('playback-position','input');
 assert.equal(e['playback-image'].src,'linear-1');assert.equal(app.timers.size,0);
 e['playback-display'].value='enhanced';await app.fire('playback-display','change');
 assert.equal(e['playback-image'].src,'enhanced-1');assert.equal(e.display.value,'enhanced');
 await e['playback-review'].click();assert.equal(e['frame-title'].textContent,'Frame 002');
 assert.equal(e['review-filter'].value,'all');
 e['playback-position'].value='3';await app.fire('playback-position','input');
 e['playback-loop'].checked=true;await e['playback-play'].click();await app.tick();
 assert.equal(e['playback-image'].src,'enhanced-0');
 app.context.document.hidden=true;app.documentEvents.visibilitychange();
 assert.equal(app.timers.size,0);assert.equal(e['playback-play'].textContent,'Play captures');
 // Pausing while an image is decoding must not restart a stale timer.
 let ready;app.context.document.hidden=false;
 e['playback-image'].decode=()=>new Promise(resolve=>{ready=resolve});
 const starting=e['playback-play'].click();
 await Promise.resolve();await e['playback-play'].click();ready();await starting;
 assert.equal(app.timers.size,0);

 const collapsible=start();
 await collapsible.els['playback-play'].click();
 assert.equal(collapsible.els['playback-panel'].open,true);
 collapsible.els['playback-panel'].open=false;
 await collapsible.fire('playback-panel','toggle');
 assert.equal(collapsible.timers.size,0,'Closing the panel stops playback');
 assert.equal(collapsible.els['playback-play'].textContent,'Play captures');
 collapsible.els.display.value='enhanced';
 await collapsible.fire('display','change');
 assert.equal(collapsible.els['playback-panel'].open,false,'Display changes do not reopen the collapsed panel');
 const bulk=start(),b=bulk.els;
 b.filter.value='no_elongation_flag';await bulk.fire('filter','change');
 await b['bulk-action'].click();
 assert.equal(b['bulk-preview'].hidden,false);
 await b['playback-play'].click();
 assert.equal(b['bulk-confirm'].disabled,true);
 await b['bulk-confirm'].click();
 assert.equal(b.reviewed.textContent,0,'Pending bulk decisions cannot apply while playing');
 await b['playback-play'].click();
 await b['bulk-confirm'].click();
 assert.equal(b.reviewed.textContent,4);
 await b['playback-play'].click();
 await b['bulk-undo'].click();
 assert.equal(b.reviewed.textContent,4,'Undo is also blocked while playing');
 await b['playback-play'].click();await b['bulk-undo'].click();
 assert.equal(b.reviewed.textContent,0);
 const many=start(501);
 assert.match(many.els['playback-summary'].textContent,/501 captures/);
 assert.equal(many.els['playback-position'].max,'500','No 40-frame aligned-viewer cap');
 const one=start(1);assert.equal(one.els['playback-play'].disabled,true);
 console.log('Playback passed: full sequence, filename order, speed, scrub, loop, pause, failed previews, display modes and review selection.');
})().catch(error=>{console.error(error);process.exitCode=1});
