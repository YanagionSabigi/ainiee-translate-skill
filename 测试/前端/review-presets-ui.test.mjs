// Component tests use an in-memory DOM, without controlling a browser or user data.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import * as glossary from '../../src/ainiee_translate/workbench_runtime/web/scripts/glossary.js';
import * as draftHelpers from '../../src/ainiee_translate/workbench_runtime/web/scripts/drafts.js';
import * as reading from '../../src/ainiee_translate/workbench_runtime/web/scripts/reading-notes.js';
import * as navigation from '../../src/ainiee_translate/workbench_runtime/web/scripts/navigation.js';
import {el,plain,math,diffText,table} from '../../src/ainiee_translate/workbench_runtime/web/scripts/render.js';

class Element {
  constructor(tag) { this.tag=tag; this.children=[]; this.attrs={}; this.style={}; this.dataset={}; this.events={}; this.className='';
    this.classList={toggle:(name,on)=>{const names=new Set(this.className.split(' ')); on?names.add(name):names.delete(name);this.className=[...names].join(' ');},contains:name=>this.className.split(' ').includes(name)}; }
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children=children;}
  setAttribute(k,v) {this.attrs[k]=v; if(k==='class')this.className=v;}
  addEventListener(k,fn) {this.events[k]=fn;}
  set textContent(text) {this.children=[String(text)];}
  get textContent() {return this.children.map(c=>c instanceof Element?c.textContent:c).join('');}
  querySelector(selector) {return descendants(this).find(n=>selector.startsWith('.')?n.className.split(' ').includes(selector.slice(1)):selector==='summary'?n.tag==='summary':false)??null;}
  focus() {}
}
function descendants(node) {return node.children.filter(c=>c instanceof Element).flatMap(c=>[c,...descendants(c)]);}

async function harness() {
  const nodes=new Map();
  const document={addEventListener(){},createElement:t=>new Element(t),createTextNode:t=>String(t),
    querySelector:s=>{if(s.startsWith('#')) {if(!nodes.has(s))nodes.set(s,new Element('div'));return nodes.get(s);} return null;}};
  globalThis.Node=Element; globalThis.document=document;
  const item=(id,base)=>({id,target_id:id,group_id:'terms',facets:{},location:id,requires_human:false,
    term_info:{source:id,category:'finance',context:'A real sentence.',page:1,...(base?{base}:{})},
    before:[{id:'dst',type:'text',text:'当前 '+id}],baseline:[{id:'dst',type:'text',text:'当前 '+id}],
    proposal:[{id:'dst',type:'text',text:'备选 '+id}], evidence:[],rationale:''});
  const items=[item('account'),...Array.from({length:27},(_,n)=>item('account-'+n,'account')),item('module'),item('free module','module')];
  items[2].requires_human=true;
  const data={package:{review_profile:'glossary',title:'合成测试',package_id:'test',groups:[{id:'terms',title:'术语'}],facets:[],items},
    drafts:{revision:0,items:{'account-2':{mode:'edit',touched:true,edits:{dst:'人工改名'}}}},submissions:[{decisions:[{item_id:'account-3'}]}]};
  let saved;
  const context=vm.createContext({document,Node:Element,CSS:{escape:x=>x},structuredClone,el,plain,math,diffText,table,
    ...glossary,...draftHelpers,...reading,...navigation,addEventListener:()=>{},setTimeout:()=>0,clearTimeout:()=>{},
    sessionStorage:{setItem(){},removeItem(){}},api:async(path,method,body)=>{
      assert.equal(path,'/api/drafts'); saved=structuredClone(body.drafts); saved.revision++; return saved;
    }, data});
  let source=await readFile(new URL('../../src/ainiee_translate/workbench_runtime/web/scripts/app.js',import.meta.url),'utf8');
  source=source.replace(/^import .*;\r?\n/gm,'');
  source=source.slice(0,source.indexOf('$("#image-stage").addEventListener'));
  vm.runInContext(source,context);
  vm.runInContext('state=data;drafts=structuredClone(data.drafts);activeId="account";render();',context);
  return {context,nodes,run:code=>vm.runInContext(code,context),saved:()=>saved};
}

test('actual glossary components hide ordinary queue and render open minimal term details',async()=>{
  const h=await harness();
  assert.equal(h.nodes.get('#queue').hidden,true);
  const card=h.nodes.get('#articles').children[0];
  const details=descendants(card).filter(n=>n.tag==='details');
  assert.equal(details.length,1);
  assert.equal(details[0].attrs.open,'');
  assert.equal(details[0].children[0].textContent,'术语信息');
  assert.deepEqual(descendants(details[0]).filter(n=>n.tag==='dt').map(n=>n.textContent),['原词','分类领域','上下文','PDF 页码']);
  assert(!card.textContent.includes('修改依据'));
  assert(!card.textContent.includes('分类finance'));
  assert(descendants(h.nodes.get('#sidebar')).some(n=>n.className.includes('term-preview')&&n.children[0].textContent==='account'&&n.children[1].textContent==='当前 account'));
});

test('actual family action keeps current names across pages, leaves other families and drafts intact',async()=>{
  const h=await harness();
  h.run('group="family:account";activeId="account-0";render();');
  const queue=h.nodes.get('#queue');
  assert.equal(queue.hidden,false);
  assert(queue.textContent.includes('同意一类'));
  assert(!queue.textContent.includes('free module'));
  assert(!queue.textContent.includes('备选 account-0'));
  await h.run('approveFamily("account")');
  const saved=h.saved();
  assert.equal(saved.items['account-26'].mode,'keep');
  assert.equal(saved.items['account-0'].mode,'keep');
  assert.equal(saved.items['account-2'].edits.dst,'人工改名');
  assert.equal(saved.items['account-1'].mode,null);
  assert.equal(saved.items['account-3'].mode,null);
  assert.equal(saved.items.account.mode,null);
  assert(!saved.items['free module']?.mode);
  h.run('query="account-0";render();');
  assert.equal(descendants(queue).find(n=>n.tag==='button'&&n.textContent==='同意一类').disabled,true);
});
