'use strict';
function documentFixture() {
  const elements = new Map();
  const document = { activeElement: null, listeners: {},
    addEventListener(k,fn) {(this.listeners[k] ||= []).push(fn);},
    fire(k) {for (const fn of this.listeners[k] || []) fn();},
  };
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
  const ids=['role-request-list','role-request-host-panel','role-request-host-status','role-request-host-name','role-request-host-enable','role-request-host-disable','role-create-form','role-create-modal','role-create-runner','role-create-model','role-create-name','role-create-description','role-create-auto-start','role-create-submit','role-create-close','role-create-notice','role-create-result'];
  ids.push('role-create-model-setup');
  for(const id of ids) {const n=element(id.includes('submit')||id.includes('close')?'button':'div'); n.id=id;elements.set(id,n);}
  const el=id=>elements.get(id);
  const texts=n=>[n.textContent,...n.children.flatMap(texts)].filter(Boolean).join('\n');
  return {document,el,texts,elements};
}
module.exports={documentFixture};

// 此文件也被其他测试作为 fixture 引用；只在直接运行时注册用例。
if (require.main === module) {
  const {test}=require('node:test');
  const assert=require('node:assert/strict');
  const vm=require('node:vm');
  const fs=require('node:fs');
  const path=require('node:path');
  const context=vm.createContext({module:{exports:{}},exports:{}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/role-creation.js'),'utf8'),context);
  const {createRoleRequestUI}=context.module.exports;
  const tick=()=>new Promise(resolve=>setImmediate(resolve));

  async function alertsFor(rows,roles) {
    const dom=documentFixture(),alerts=[];
    const savedKey='talk-role-intent:["p","human:a"]:saved';
    const saved=JSON.stringify(rows.map(row=>row.request_key));
    const storage=new Map([[savedKey,saved]]);
    const ui=createRoleRequestUI({document:dom.document,
      context:()=>({projectId:'p',accountId:'human:a',active:true,settings:true,human:true}),
      storage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
      setTimeout:()=>1,clearTimeout:()=>{},alert:text=>alerts.push(text),
      refreshRoster:async()=>{},renderDetails:()=>{},
      api:async request=>({ok:true,status:200,json:async()=>{
        if (request.endsWith('/role-provision-host')) return {enabled:true};
        if (request.includes('/role-requests?')) return rows;
        if (request.endsWith('/roles')) return roles;
        throw Error('unexpected '+request);
      }})});
    ui.sync();await tick();
    assert.equal(ui.state.error,'');
    assert.equal(ui.state.rows.length,rows.length);
    assert.equal(storage.get(savedKey),saved);
    return {alerts,ui};
  }
  const row=(member,extra={})=>({request_key:'role-'+(member||'unassigned').replace(/[^a-z0-9]/gi,'-')+'-request',
    member_id:member,role_name:member||'待创建',status:'provisioned',revision:1,auto_start:true,auto_start_status:'failed',...extra});

  test('归档角色自动启动失败不提示，活跃角色首次失败仍提示',async()=>{
    const rows=[row('agent:archived'),row('agent:active')];
    const {alerts,ui}=await alertsFor(rows,[{member_id:'agent:archived',archived:true},{member_id:'agent:active',archived:false}]);
    assert.equal(alerts.length,1);
    assert.match(alerts[0],/agent:active.*自动启动未完成/);
    await ui.refresh();assert.equal(alerts.length,1);
  });
  test('名册缺失角色的自动启动失败不提示',async()=>{
    const {alerts}=await alertsFor([row('agent:missing')],[]);
    assert.deepEqual(alerts,[]);
  });
  test('归档和缺失角色的请求失败不提示，活跃角色及尚未分配成员的请求失败仍提示',async()=>{
    const rows=[row('agent:archived',{status:'failed'}),row('agent:missing',{status:'failed'}),
      row('agent:active',{status:'failed'}),row(null,{status:'failed'})];
    const {alerts}=await alertsFor(rows,[{member_id:'agent:archived',archived:true},{member_id:'agent:active',archived:false}]);
    assert.equal(alerts.length,2);
    assert.ok(alerts.some(text=>text.includes('agent:active')));
    assert.ok(alerts.some(text=>text.includes('待创建')));
  });
}
