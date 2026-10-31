import test from 'node:test';
import assert from 'node:assert/strict';
import {termPreview, familyItems, familyBatch} from '../../src/ainiee_translate/workbench_runtime/web/scripts/glossary.js';

const term = (id, base='account') => ({id, term_info:{source:id,base}, requires_human:false,
  before:[{id:'dst',text:'当前'}], proposal:[{id:'dst',text:'备选'}]});
test('previews use before until explicitly chosen, retain empty edits and source', () => {
  const i = term('household account');
  assert.deepEqual(termPreview(i, {}), {source:'household account',translation:'当前'});
  assert.equal(termPreview(i, {mode:'accept'}).translation, '备选');
  assert.equal(termPreview(i, {mode:'edit',edits:{dst:'自定'}}).translation, '自定');
  assert.equal(termPreview(i, {mode:'edit',edits:{dst:''}}).translation, '');
  assert.equal(termPreview(i, {mode:'comment'}).translation, '当前');
});
test('family batch spans pages but preserves all human work, required and submitted items', () => {
  const items = Array.from({length:30}, (_,n)=>term('a'+n));
  items.push(term('other','module'),term('account',null));
  items[1].requires_human = true;
  items[2].before[0].text = '';
  const drafts = {items:{a3:{mode:'edit',edits:{dst:'改'}},a4:{comment:'意见'},a5:{touched:true},
    a6:{edits:{dst:'未选择的修改'}},a7:{quotes:[{}]},a8:{mode:'keep'}}};
  const submitted = new Set(['a9']);
  assert.equal(familyItems(items,'account').length,30);
  const eligible = familyBatch(items,'account',drafts,submitted);
  assert.equal(eligible.length,21);
  assert(eligible.some(i=>i.id==='a29'));
  assert(!eligible.some(i=>i.id==='other' || i.id==='account'));
  assert.deepEqual(items[0].proposal,[{id:'dst',text:'备选'}]);
});
