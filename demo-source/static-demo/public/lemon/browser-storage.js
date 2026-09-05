/* Real browser-only storage for the explicitly selected preview edition. */
const STORE_KEY='point-line-plane:demo:lemon:v1';
function readTimer(){
  const raw=localStorage.getItem(STORE_KEY);
  if(!raw)return {version:1,settings:{focus_minutes:25,break_minutes:5},session:{status:'idle',phase:null,remaining_seconds:1500,initial_seconds:1500},completed:{}};
  const saved=JSON.parse(raw);
  if(saved.version!==1||!saved.settings||!saved.session||!saved.completed)throw Error('当前浏览器记录格式无法读取，请先备份浏览器数据。');
  return saved;
}
function localDay(ms){const d=new Date(ms);return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');}
async function browserApi(url,opt={}){
  const action=()=>{
    let data;
    try{data=readTimer()}catch{throw Error('无法读取当前浏览器记录。请允许此网站保存数据；已有记录不会被覆盖。')}
    const now=Date.now();let x=data.session;
    if(x.status==='running'){
      x.remaining_seconds=Math.max(0,Math.ceil((x.ends_at-now)/1000));
      if(x.remaining_seconds===0){x.status='completed';if(x.phase==='focus')data.completed[x.session_id]=localDay(x.ends_at);}
    }
    const body=opt.body?JSON.parse(opt.body):{};
    if(url==='timer/demo-finish'){
      if(x.status!=='running')throw Error('请先开始或继续计时，再体验到时效果。');
      x.remaining_seconds=0;x.ends_at=now;x.status='completed';
      if(x.phase==='focus')data.completed[x.session_id]=localDay(now);
    }else if(url==='timer/start'){
      if(['running','paused'].includes(x.status))throw Error('请先结束当前阶段。');
      if(!['focus','break'].includes(body.phase)||![body.focus_minutes,body.break_minutes].every(v=>Number.isInteger(v)&&v>=1&&v<=180))throw Error('请填写 1–180 的整数分钟。');
      if(body.phase==='break'&&!(x.status==='completed'&&x.phase==='focus'))throw Error('请先完成专注阶段。');
      data.settings={focus_minutes:body.focus_minutes,break_minutes:body.break_minutes};
      const seconds=(body.phase==='focus'?body.focus_minutes:body.break_minutes)*60;
      data.session={session_id:crypto.randomUUID(),phase:body.phase,status:'running',initial_seconds:seconds,remaining_seconds:seconds,ends_at:now+seconds*1000};
    }else if(url==='timer/pause'){
      if(x.status!=='running')throw Error('当前阶段无法暂停。');x.status='paused';
    }else if(url==='timer/resume'){
      if(x.status!=='paused')throw Error('当前阶段未暂停。');x.status='running';x.ends_at=now+x.remaining_seconds*1000;
    }else if(url==='timer/end'){
      if(!body.confirmed)throw Error('请先确认结束。');
      if(!['running','paused'].includes(x.status))throw Error('当前没有可结束的计时。');x.status='ended';
    }else if(!['session','timer'].includes(url))throw Error('轻量预览版不支持此操作。');
    try{localStorage.setItem(STORE_KEY,JSON.stringify(data))}catch{throw Error('记录未能保存，请检查浏览器存储空间或隐私设置。')}
    return {...data,completed_focus_count:Object.values(data.completed).filter(day=>day===localDay(now)).length};
  };
  return navigator.locks ? navigator.locks.request(STORE_KEY,action) : action();
}
