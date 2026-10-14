'use strict';
function documentFixture() {
  const elements = new Map();
  const document = { activeElement: null };
  function element(tag = 'div') {
    const classes = new Set(); let text = '';
    const n = { tagName: tag.toUpperCase(), className: '', children: [], dataset: {}, value: '', disabled: false, listeners: {}, attrs: {},
      classList: {add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c,on){on ??= !classes.has(c);on?classes.add(c):classes.delete(c);}},
      append(...nodes) { this.children.push(...nodes); }, appendChild(c) { this.children.push(c); return c; },
      replaceChildren(...nodes) {this.children = [...nodes];text='';},
      insertBefore(child,before) {const index=this.children.indexOf(before);this.children.splice(index<0?this.children.length:index,0,child);return child;},
      setAttribute(k,v) {this.attrs[k]=String(v);},
      addEventListener(k,fn) {(this.listeners[k] ||= []).push(fn);},
      async fire(k,event={}) {for(const fn of this.listeners[k]||[]) await fn(event);},
      focus() {document.activeElement=this;},
      querySelectorAll() {return this.children.flatMap(c=>[c,...c.querySelectorAll()]);},
    };
    Object.defineProperty(n,'textContent',{get:()=>text,set:v=>{text=String(v);n.children=[];}});
    return n;
  }
  document.createElement=element;
  document.getElementById=id=>elements.get(id)||[...elements.values()].flatMap(n=>n.querySelectorAll()).find(n=>n.id===id)||null;
  const ids=['role-request-list','role-request-host-panel','role-request-host-status','role-request-host-name','role-request-host-enable','role-request-host-disable','role-create-form','role-create-modal','role-create-runner','role-create-model','role-create-name','role-create-description','role-create-submit','role-create-close','role-create-notice','role-create-result'];
  ids.push('role-create-model-setup');
  for(const id of ids) {const n=element(id.includes('submit')||id.includes('close')?'button':'div'); n.id=id;elements.set(id,n);}
  const el=id=>elements.get(id);
  const texts=n=>[n.textContent,...n.children.flatMap(texts)].filter(Boolean).join('\n');
  return {document,el,texts,elements};
}
module.exports={documentFixture};
