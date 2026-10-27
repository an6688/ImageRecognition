// Offline control-flow checks. Run with astro/astro_report_template.html.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
const script = source.match(/<script>\s*('use strict';[\s\S]*?)<\/script>/)[1];
const frames = ['review_suggested','no_elongation_flag','insufficient_evidence'].map((decision,id)=>({
  id,decision,name:'frame-'+id+'.png',status:'ok',count:12,fraction:id===0?.8:.1,
  ratio:id===0?2.4:1.1,brightFraction:id===0?.9:.1,coverage:'all_detected_peaks',
  width:2160,height:3840,linear:'data:linear-'+id,enhanced:'data:enhanced-'+id,
  markers:[{x:420,y:900,elongated:true}],examples:[
    {id:'a',x:420,y:900,cx:20,cy:20,major:2,minor:1,angle:10,ratio:2,elongated:true,linear:'data:crop-linear',enhanced:'data:crop-enhanced'},
    {id:'b',x:1900,y:2500,cx:20,cy:20,major:1,minor:1,angle:0,ratio:1,elongated:false,linear:'data:crop2-linear',enhanced:'data:crop2-enhanced'}
  ]
}));
const data={frames,summary:'summary.csv',candidates:'stars.csv',versions:['elongation-v2']};
const elements={};
for(const [,id] of source.matchAll(/\bid="([^"]+)"/g)){
  elements[id]={id,value:'',checked:false,hidden:false,textContent:'',innerHTML:'',
    style:{},attributes:{},clientWidth:750,clientHeight:590,offsetLeft:22,offsetTop:22,
    listeners:{},classList:{values:new Set(),toggle(k,on){on?this.values.add(k):this.values.delete(k)}},
    setAttribute(k,v){this.attributes[k]=v},
    toggleAttribute(k,on){if(on)this.attributes[k]='';else delete this.attributes[k];return !!on},
    hasAttribute(k){return Object.hasOwn(this.attributes,k)},
    addEventListener(k,fn){this.listeners[k]=fn},
    click(){this.listeners.click?.({})}
  };
}
// SVG does not reflect a .hidden property into attributes. Model that distinction.
elements['selection-overlay'].attributes.hidden='';
elements['local-session'].textContent='null';
elements['report-data'].textContent=JSON.stringify(data);
for(const [id,value] of Object.entries({filter:'all','review-filter':'all',sort:'sequence','rejected-action':'export',display:'linear',gain:'1',zoom:'1'}))elements[id].value=value;
const inspector={hidden:false};
let exported,download,revoked=false;
const context={
 document:{
   getElementById(id){assert.ok(elements[id],'Missing element '+id);return elements[id]},
   querySelector(selector){assert.equal(selector,'.inspector');return inspector},
   createElement(){return {click(){download=this.download}}}
 },
 localStorage:{getItem(){return null},setItem(){}},
 window:{addEventListener(){}},
 Blob:class{constructor(parts){exported=JSON.parse(parts.join(''))}},
 URL:{createObjectURL(){return 'blob:test'},revokeObjectURL(){revoked=true}},
 setTimeout:fn=>fn()
};
vm.runInNewContext(script,context,{timeout:2000});
const fire=(id,event)=>elements[id].listeners[event]();
const pick=index=>elements['sample-grid'].listeners.click({
 target:{closest(){return {dataset:{example:String(index)}}}}
});
assert.equal(elements['frame-title'].textContent,'Frame 001');
assert.ok(elements['visual-content'].classList.values.has('no-markers'));
assert.equal(elements['selection-overlay'].hasAttribute('hidden'),true);
pick(1);
assert.equal(elements['selection-overlay'].hasAttribute('hidden'),false);
assert.equal(elements['location-bar'].hidden,false);
assert.match(elements['selection-overlay'].innerHTML,/<polygon/);
assert.match(elements['selection-overlay'].innerHTML,/cx="1900" cy="2500"/);
assert.equal(elements['selection-overlay'].attributes.viewBox,'0 0 2160 3840');
assert.ok(elements['visual-content'].classList.values.has('no-markers'),'Selection must work with general markers off');
assert.match(elements['location-caption'].textContent,/Candidate #b/);
const pointerBefore=elements['selection-overlay'].innerHTML;
elements.zoom.value='4';fire('zoom','change');
assert.match(elements['selection-overlay'].innerHTML,/cx="1900" cy="2500"/);
assert.notEqual(elements['selection-overlay'].innerHTML,pointerBefore,'Pointer scales with preview zoom');
assert.ok(elements.viewport.scrollLeft>0);
assert.ok(elements.viewport.scrollTop>0);
elements.display.value='enhanced';fire('display','change');
assert.equal(elements.overview.src,'data:enhanced-0');
assert.equal(elements.crop.src,'data:crop2-enhanced');
elements.display.value='linear';fire('display','change');
assert.equal(elements.overview.src,'data:linear-0');
assert.equal(elements.crop.src,'data:crop2-linear');
assert.equal(elements['selection-overlay'].hasAttribute('hidden'),false);
elements.markers.checked=true;fire('markers','change');
elements.markers.checked=false;fire('markers','change');
assert.equal(elements['selection-overlay'].hasAttribute('hidden'),false);
elements['hide-location'].click();
assert.equal(elements['selection-overlay'].hasAttribute('hidden'),true);
pick(0);elements.next.click();
assert.equal(elements['frame-title'].textContent,'Frame 002');
assert.equal(elements['selection-overlay'].hasAttribute('hidden'),true,'New exposure resets selected location');
elements.assessment.value='no_obvious_elongation';fire('assessment','change');
elements.notes.value='Check the galaxy separately';fire('notes','input');
elements.next.click();elements.prev.click();
assert.equal(elements.notes.value,'Check the galaxy separately');
elements.filter.value='review_suggested';fire('filter','change');
assert.equal(elements['frame-title'].textContent,'Frame 001');
elements.search.value='missing';fire('search','input');
assert.equal(elements.empty.hidden,false);
assert.equal(elements.detail.hidden,true);
elements.search.value='';fire('search','input');
elements.filter.value='all';fire('filter','change');
elements.sort.value='ratio';fire('sort','change');
elements.export.click();
assert.equal(exported.assessments.length,3);
assert.equal(exported.assessments[1].notes,'Check the galaxy separately');
assert.equal(exported.analysis_version,'elongation-v2');
assert.equal(download,'astro-review.json');
assert.equal(revoked,true);
assert.ok(!source.includes('See the evidence. Make the call.'));
assert.ok(!source.includes('Why the earlier preview looked black.'));
console.log('Report controls passed: pointer position, zoom, overlay independence, display modes, filtering, navigation, notes and export.');
