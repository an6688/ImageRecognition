const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
const script=source.match(/<script>\s*('use strict';[\s\S]*?)<\/script>/)[1];
const frames=[0,1,2].map(id=>({id,name:'frame-'+id+'.png',path:'C:/images/frame-'+id+'.png',
 decision:id===0?'review_suggested':'no_elongation_flag',status:'ok',fraction:.1,ratio:1.1,
 count:0,coverage:'all_detected_peaks',brightFraction:null,width:100,height:100,markers:[],examples:[],
 linear:'data:linear',enhanced:'data:enhanced'}));
function launch(store=new Map(),blocked=false,session=null,fetchImpl=undefined){
 const els={},events={};let exported,download;
 for(const [,id] of source.matchAll(/\bid="([^"]+)"/g))els[id]={id,value:'',checked:false,hidden:false,textContent:'',innerHTML:'',
 style:{},attributes:{},clientWidth:750,clientHeight:590,offsetLeft:22,offsetTop:22,listeners:{},
 classList:{toggle(){}},setAttribute(k,v){this.attributes[k]=v},
 toggleAttribute(k,on){if(on)this.attributes[k]='';else delete this.attributes[k]},
 addEventListener(k,fn){const before=this.listeners[k];this.listeners[k]=before?(...args)=>{before(...args);return fn(...args)}:fn},click(){return this.listeners.click?.({})}};
 els['playback-stage'].hidden=true;
 els['local-session'].textContent=JSON.stringify(session);
 els['report-data'].textContent=JSON.stringify({frames,summary:'m31.csv',candidates:'stars.csv',versions:['test']});
 for(const [id,value] of Object.entries({filter:'all','review-filter':'all',sort:'sequence','rejected-action':'export',display:'linear','playback-display':'linear','playback-speed':'2',gain:'1',zoom:'1'}))els[id].value=value;
 const context={fetch:fetchImpl,document:{getElementById:id=>els[id],querySelector:()=>({hidden:false}),createElement:()=>({click(){download=this.download}})},
 window:{addEventListener(k,fn){events[k]=fn}},
 localStorage:{getItem(k){if(blocked)throw Error('disabled');return store.get(k)||null},setItem(k,v){if(blocked)throw Error('disabled');store.set(k,v)}},
 Blob:class{constructor(parts){exported=JSON.parse(parts.join(''))}},
 URL:{createObjectURL(){return 'blob:test'},revokeObjectURL(){}},clearTimeout(){},setTimeout:fn=>fn()};
 vm.runInNewContext(script,context,{timeout:2000});
 return {els,events,store,download(){return {document:exported,name:download}},fire:(id,event)=>els[id].listeners[event](),
 export(){els.export.click();assert.equal(download,'astro-review.json');return exported},
 async import(doc){els['import-file'].files=[{text:async()=>JSON.stringify(doc)}];await els['import-file'].listeners.change()}};
}
(async()=>{
 const app=launch(),e=app.els;
 e.keep.click();assert.equal(e['your-decision'].textContent,'Keep');assert.equal(e.keep.attributes['aria-pressed'],'true');
 assert.equal(e.decision.textContent,'Review suggested','Human decision must not alter algorithm flag');
 e.assessment.value='elongation_visible';app.fire('assessment','change');
 e.notes.value='Acceptable for this stack';app.fire('notes','input');
 assert.equal(e['your-decision'].textContent,'Keep');
 e.next.click();e.reject.click();e.next.click();e.revisit.click();
 assert.equal(e.reviewed.textContent,3);
 assert.equal(e['review-counts'].textContent,'Keep 1 · Reject 1 · Revisit 1');
 assert.match(e['frame-list'].innerHTML,/review-status reject/);
 const backup=app.export();assert.equal(backup.assessments[1].review_decision,'reject');assert.equal(backup.assessments[1].path,frames[1].path);
 assert.equal(backup.assessments[0].human_assessment,'elongation_visible');
 e['review-filter'].value='reject';app.fire('review-filter','change');
 assert.equal(e['frame-title'].textContent,'Frame 002');assert.equal(e['list-count'].textContent,'1 exposures');
 e.keep.click();assert.equal(e.empty.hidden,false,'Changing a filtered decision removes the frame');
 e['review-filter'].value='all';app.fire('review-filter','change');
 const restored=launch(app.store);
 assert.match(restored.els['save-status'].textContent,/restored/);
 assert.equal(restored.els['your-decision'].textContent,'Keep');
 assert.equal(restored.els.notes.value,'Acceptable for this stack');
 assert.equal(restored.export().assessments[1].review_decision,'keep');
 await restored.import(backup);assert.equal(restored.export().assessments[1].review_decision,'reject');
 const wrong=JSON.parse(JSON.stringify(backup));wrong.dataset=['C:/other/image.png'];
 await restored.import(wrong);assert.match(restored.els['save-status'].textContent,/not imported/);
 assert.equal(restored.export().assessments[1].review_decision,'reject','Invalid import must not erase existing review');
 const bad=JSON.parse(JSON.stringify(backup));bad.assessments[0].review_decision='delete';
 await restored.import(bad);assert.match(restored.els['save-status'].textContent,/invalid/);
 const duplicate=JSON.parse(JSON.stringify(backup));duplicate.assessments.push(duplicate.assessments[0]);
 await restored.import(duplicate);assert.match(restored.els['save-status'].textContent,/duplicate/);
 restored.els['reset-review'].click();assert.equal(restored.els['your-decision'].textContent,'Not reviewed');
 restored.els['next-unreviewed'].click();assert.equal(restored.els['frame-title'].textContent,'Frame 001');
 assert.equal(restored.els['review-filter'].value,'unreviewed');
 const key=(key,tagName='BODY')=>restored.events.keydown({key,target:{tagName},preventDefault(){}});
 key('r','TEXTAREA');assert.equal(restored.els['your-decision'].textContent,'Not reviewed');
 key('k');assert.equal(restored.els.empty.hidden,false);
 const noStorage=launch(new Map(),true);noStorage.els.reject.click();
 assert.match(noStorage.els['save-status'].textContent,/unavailable/);
 assert.equal(noStorage.export().assessments[0].review_decision,'reject');
 const corrupt=new Map(app.store);for(const k of corrupt.keys())corrupt.set(k,'not JSON');
 const recovered=launch(corrupt);assert.match(recovered.els['save-status'].textContent,/Could not restore/);
 await recovered.import(backup);assert.equal(recovered.export().assessments[1].review_decision,'reject');

 // The actual HTML default, not just the mock value, must be Linear.
 assert.match(source,/<select id="display"[^>]*><option value="linear" selected>/);
 const offline=launch();
 assert.equal(offline.els.overview.src,'data:linear');
 assert.equal(offline.els['rejected-count'].textContent,'0','Algorithm flags alone do not count as rejections');
 offline.els.keep.click();offline.els.next.click();offline.els.reject.click();
 await offline.els['rejected-run'].click();
 assert.equal(offline.download().name,'astro-rejected.json');
 assert.equal(offline.download().document.assessments.length,1);
 assert.equal(offline.download().document.assessments[0].path,frames[1].path);
 offline.els['rejected-action'].value='move';offline.fire('rejected-action','change');
 assert.equal(offline.els['rejected-run'].disabled,true);
 assert.match(offline.els['rejected-help'].textContent,/AstroTrack/);
 const calls=[],moved={[frames[0].path]:'C:/images/Rejected/frame-0.png'};
 const local=launch(new Map(),false,{token:'session',destination:'C:/images/Rejected',moved:{}},async(route,options)=>{
   calls.push({route,body:JSON.parse(options.body),token:options.headers['X-Astro-Token']});
   return {ok:true,json:async()=>route==='/api/plan'?{plan:'plan-1',destination:'C:/images/Rejected',files:[{source:frames[0].path}]}:{moved}};
 });
 local.els.reject.click();local.els['rejected-action'].value='move';local.fire('rejected-action','change');
 await local.els['rejected-run'].click();
 assert.equal(calls.length,1);assert.equal(calls[0].route,'/api/plan');
 assert.deepEqual(calls[0].body.paths,[frames[0].path]);assert.equal(calls[0].token,'session');
 assert.equal(local.els['move-preview'].hidden,false);
 await local.els['confirm-move'].click();
 assert.equal(calls[1].route,'/api/move');assert.equal(calls[1].body.plan,'plan-1');
 assert.match(local.els['rejected-status'].textContent,/Moved 1 images/);
 assert.equal(local.els['rejected-run'].disabled,true,'Already moved images cannot be submitted again');
 assert.match(local.els['rejected-list'].innerHTML,/Moved to Rejected/);
 const changed=launch(new Map(),false,{token:'session',destination:'Rejected',moved:{}},async()=>({ok:true,json:async()=>({plan:'old-plan',destination:'Rejected',files:[{source:frames[0].path}]})}));
 changed.els.reject.click();changed.els['rejected-action'].value='move';changed.fire('rejected-action','change');
 await changed.els['rejected-run'].click();changed.els.keep.click();
 assert.equal(changed.els['move-preview'].hidden,true,'Changing a decision cancels the pending move');
 const failed=launch(new Map(),false,{token:'session',destination:'Rejected',moved:{}},async()=>({ok:false,json:async()=>({error:'Destination exists',moved:{}})}));
 failed.els.reject.click();failed.els['rejected-action'].value='move';failed.fire('rejected-action','change');
 await failed.els['rejected-run'].click();
 assert.match(failed.els['rejected-status'].textContent,/Destination exists/);
 assert.equal(failed.els['rejected-run'].disabled,false,'Allow retry after a failed preview');
 console.log('Review workflow passed: decisions, independent assessments, filters, reload, import/export, invalid data, keyboard, unavailable storage, rejected-only export and confirmed moves.');
})().catch(error=>{console.error(error);process.exitCode=1});
