import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import vm from 'node:vm';
const base = new URL('../site/demo/', import.meta.url);
const source = readFileSync(new URL('lemon/browser-storage.js', base), 'utf8');
function timer(){const values=new Map();const context=vm.createContext({localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)},navigator:{},crypto:{randomUUID:()=>crypto.randomUUID()},Date,JSON,Math,Number,Error});vm.runInContext(source,context);return (url,body)=>context.browserApi(url,body?{body:JSON.stringify(body)}:{});}
test('focus completion counts once, break completion does not count, early end does not count',async()=>{const api=timer();await api('timer/start',{phase:'focus',focus_minutes:25,break_minutes:5});await api('timer/pause');let state=await api('timer');assert.equal(state.session.status,'paused');await api('timer/resume');state=await api('timer/demo-finish');assert.equal(state.completed_focus_count,1);assert.equal((await api('timer')).completed_focus_count,1);await assert.rejects(api('timer/demo-finish'));await api('timer/start',{phase:'break',focus_minutes:25,break_minutes:5});assert.equal((await api('timer/demo-finish')).completed_focus_count,1);await api('timer/start',{phase:'focus',focus_minutes:25,break_minutes:5});await assert.rejects(api('timer/end',{confirmed:false}));assert.equal((await api('timer/end',{confirmed:true})).completed_focus_count,1);});
test('invalid durations and premature break cannot start',async()=>{const api=timer();for(const n of [0,181,1.5,null])await assert.rejects(api('timer/start',{phase:'focus',focus_minutes:n,break_minutes:5}));await assert.rejects(api('timer/start',{phase:'break',focus_minutes:25,break_minutes:5}));});
test('original UI build contains full case data and excludes live API client',()=>{
 const raw=readFileSync(new URL('case-data.json',base),'utf8'), d=JSON.parse(raw);
 assert.ok(d.artifacts.find(a=>a.type==='prd').content.full_document.functional_requirements.length>=17);
 assert.ok(d.artifacts.find(a=>a.type==='solution').content.recommended_approach);
 assert.equal(d.deployments[0].revision,6);
 assert.equal(d.guide.selectedStepId,'acceptance');
 assert.doesNotMatch(raw,/localhost|127\.0\.0\.1|\/Users\/|volceapi\.com|"(?:owner_id|access_token|secret_ref|credential_ref_id|authorization_id)"/);
 const landing=readFileSync(new URL('../index.html',base),'utf8');
 assert.equal((landing.match(/href="\.\/demo\/"/g)||[]).length,3);
 const manifest=JSON.parse(readFileSync(new URL('ui-source-manifest.json',base),'utf8'));
 assert.equal(manifest.mode,'original-components-with-demo-data');
 assert.equal(Object.keys(manifest.sources).length,9);
 const assets=readdirSync(new URL('assets/',base));
 const js=assets.filter(f=>f.endsWith('.js')).map(f=>readFileSync(new URL('assets/'+f,base),'utf8')).join('');
 assert.doesNotMatch(js,/\/auth\/codex\/start|\/auth\/invite-login|NEXT_PUBLIC_API_BASE_URL/);
 assert.match(js,/lemon-demo-preview/);
});
