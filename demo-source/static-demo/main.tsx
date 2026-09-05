import React, { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { ProductFactoryApp } from '../features/factory/ProductFactoryApp';
import { DEMO_PROJECT_ID, resetDemo } from './client';
import '../app/globals.css';
import './notice.css';
const u=new URL(location.href);
if(!u.searchParams.has('project')){u.searchParams.set('project',DEMO_PROJECT_ID);u.searchParams.set('phase','idea');u.searchParams.set('stage','m1a');history.replaceState({},'',u);}
const WELCOME_KEY='point-line-plane:demo-welcome:v1';
function Demo(){
 const welcome=useRef<HTMLDialogElement>(null);
 useEffect(()=>{let seen=false;try{seen=sessionStorage.getItem(WELCOME_KEY)==='seen';}catch{}if(!seen)welcome.current?.showModal();},[]);
 function acknowledge(){try{sessionStorage.setItem(WELCOME_KEY,'seen');}catch{}}
 function restart(){try{sessionStorage.removeItem(WELCOME_KEY);}catch{}resetDemo();}
 return <>
  <ProductFactoryApp/>
  <div className="static-demo-switch"><button className="static-demo-about" onClick={()=>welcome.current?.showModal()}>柠檬项目 Demo · 模拟体验</button><button onClick={restart}>重置案例</button></div>
  <dialog ref={welcome} className="demo-welcome-dialog" aria-labelledby="demo-welcome-title" aria-describedby="demo-welcome-description" onClose={acknowledge}>
   <div className="demo-welcome-brand"><span className="brand-mark dot-logo" aria-hidden="true"><span className="dot-logo-glyph">{Array.from({length:24},(_,i)=><i key={i}/>)}</span></span><span>点线面</span><small>交互 Demo</small></div>
   <h1 id="demo-welcome-title">通过一个柠檬项目，<br/>了解产品从点子到上线</h1>
   <p id="demo-welcome-description">欢迎体验点线面！当前是 <strong>Demo 版本</strong>，我们内置了已完成的「柠檬番茄闹钟」项目，带你了解平台的完整使用流程。</p>
   <ol className="demo-welcome-steps">{['提出点子','确认方案','生成预览','部署上线'].map((label,index)=><li key={label}><span>{index+1}</span>{label}</li>)}</ol>
   <p className="demo-welcome-note">你可以自由切换四个阶段，查看需求与方案，操作产品预览。对话、生成和上线均为模拟，无需登录，不会产生费用。</p>
   <button className="primary-button demo-welcome-start" onClick={()=>welcome.current?.close()} autoFocus>开始体验柠檬项目 <span aria-hidden="true">→</span></button>
  </dialog>
 </>;
}
document.addEventListener('click',e=>{const a=(e.target as Element).closest?.('a');if(!a)return;const url=new URL(a.href,location.href);if(url.origin!==location.origin&&/volcengine|openai|chatgpt/.test(url.hostname)){e.preventDefault();alert('这是内置柠檬案例演示，无需登录、购买或配置真实服务。可在当前页面继续体验。');}},true);
createRoot(document.getElementById('root')!).render(<Demo/>);
