// Exercise actual viewer script offline with tiny known pixels and DOM stubs.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const template=fs.readFileSync(process.argv[2],'utf8');
const b64=a=>Buffer.from(a).toString('base64');
const data={width:2,height:1,original_width:2,original_height:1,rejected:[],frames:[
 {name:'first',pixels:b64([10,20]),mask:b64([1,1]),correlation:1,angle:0,dx:0,dy:0,overlap:1},
 {name:'second',pixels:b64([30,40]),mask:b64([1,0]),correlation:1,angle:0,dx:0,dy:0,overlap:.5}]};
function element(){return {value:'0',children:[],events:{},append(...nodes){this.children.push(...nodes)},addEventListener(e,fn){this.events[e]=fn},getContext(){return {createImageData(w,h){return {data:new Uint8ClampedArray(w*h*4)}},putImageData(){}}}}}
const elements={};for(const id of ['play','reference','mode','gain','timeline','position','left','right','leftCaption','rightCaption','status','explanation','frames','alignment','rejected','provenance'])elements[id]=element();
elements.mode.value='frame';elements.gain.value='1';
let intervalCallback;
const context={document:{getElementById:id=>elements[id],createElement:element,createTextNode:s=>s,addEventListener(){}},atob:s=>Buffer.from(s,'base64').toString('binary'),setInterval:fn=>{intervalCallback=fn;return 1},clearInterval(){},Uint8Array,Float32Array,Uint8ClampedArray};
vm.createContext(context);vm.runInContext(template.match(/<script>([\s\S]*?)<\/script>/)[1].replace('__DATA__',JSON.stringify(data)),context);
function calc(mode,cur=0,ref=0,indices=[0,1]){return vm.runInContext(`compute('${mode}',${cur},${ref},${JSON.stringify(indices)})`,context)}
assert.deepEqual(Array.from(calc('max').output),[30,0]);
assert.deepEqual(Array.from(calc('min').output),[10,0]);
assert.deepEqual(Array.from(calc('median').output),[20,0]);
assert.deepEqual(Array.from(calc('variation').output),[10,0]);
assert.deepEqual(Array.from(calc('difference',1,0).output),[20,0]);
assert.deepEqual(Array.from(calc('difference',1,1).output),[0,0]);
assert.deepEqual(Array.from(calc('max',0,0,[]).mask),[0,0]);
assert.deepEqual(Array.from(calc('max',0,0,[0]).output),[10,20]);
elements.reference.value='1';elements.reference.events.change();assert.match(elements.leftCaption.textContent,/second/);
elements.timeline.value='1';elements.timeline.events.input();assert.match(elements.position.textContent,/2 \/ 2/);
elements.mode.value='max';elements.mode.events.change();
elements.frames.children.forEach(label=>{const check=label.children[0];check.checked=false;check.events.change()});
assert.match(elements.status.textContent,/at least two/);
elements.play.events.click();intervalCallback();assert.equal(elements.timeline.value,0);elements.play.events.click();assert.equal(elements.play.textContent,'Play');
console.log('Sequence controls passed: reference, slider, play/pause, selection, max/min/median/deviation, difference, and common-support masking.');
