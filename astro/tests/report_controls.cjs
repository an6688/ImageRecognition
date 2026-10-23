// Offline unit test of report controls. No browser, server or network access.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
const listeners = {};
const sections = ['review_suggested', 'no_elongation_flag', 'insufficient_evidence'].map((decision, i) => ({
  hidden: false,
  dataset: {name: `frame-${i}.png`, decision},
  querySelector: selector => ({value: selector === '.human' ? 'uncertain' : 'Test note'})
}));
let exported, clicked = false, revoked = false;
const context = {
  document: {
    querySelector: selector => ({addEventListener: (event, fn) => {listeners[selector] = fn;}}),
    querySelectorAll: () => sections,
    createElement: () => ({click() {clicked = true;}})
  },
  Blob: class {constructor(parts) {exported = JSON.parse(parts.join(''));}},
  URL: {createObjectURL: () => 'blob:unit-test', revokeObjectURL: () => {revoked = true;}},
  setTimeout: fn => fn()
};
vm.runInNewContext(script, context, {timeout: 1000});
listeners['#filter']({target: {value: 'review_suggested'}});
assert.deepEqual(sections.map(section => section.hidden), [false, true, true]);
listeners['#filter']({target: {value: 'all'}});
assert.ok(sections.every(section => !section.hidden));
listeners['#export']();
assert.equal(exported.assessments.length, 3);
assert.equal(exported.assessments[0].human_assessment, 'uncertain');
assert.equal(exported.assessments[0].notes, 'Test note');
assert.equal(exported.analysis_version, process.argv[3] || 'elongation-v2');
assert.ok(clicked && revoked);
console.log('Report control unit checks passed: filtering and JSON assessment export.');
