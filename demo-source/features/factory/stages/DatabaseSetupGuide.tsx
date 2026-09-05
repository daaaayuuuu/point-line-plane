"use client";

import { useState } from "react";
import { ArrowRight } from "lucide-react";

export function DatabaseSetupGuide({value, onChange, lightweightAvailable}: {value: string; onChange: (value: string) => void; lightweightAvailable: boolean}) {
  const [advanced, setAdvanced] = useState(false);
  const [fields, setFields] = useState({host: "", port: "5432", database: "", username: "", password: ""});
  function update(key: keyof typeof fields, value: string) {
    const next = {...fields, [key]: value};
    setFields(next);
    const valid = /^[a-zA-Z0-9.-]+$/.test(next.host.trim()) && /^\d+$/.test(next.port) && Number(next.port) > 0 && Number(next.port) <= 65535 && next.database.trim() && next.username.trim() && next.password;
    onChange(valid ? `postgresql://${encodeURIComponent(next.username.trim())}:${encodeURIComponent(next.password)}@${next.host.trim()}:${next.port}/${encodeURIComponent(next.database.trim())}?sslmode=require` : "");
  }
  return <div className="deployment-database-help">
    <p>云数据库相当于产品放在网上的记录本。需要云端长期保存或跨设备访问时，再配置它；{lightweightAvailable ? "这个版本也支持只在当前浏览器保存记录。" : "当前产品的必需数据库须配置成功后才能发布。"}</p>
    <ol>
      <li><span>1</span><div><strong>进入数据库控制台</strong><p>用火山引擎主账号打开控制台，搜索“云数据库 PostgreSQL 版”。已有实例直接进入实例详情；没有实例时点击“创建实例”。</p><a className="deployment-help-link" href="https://console.volcengine.com/" target="_blank" rel="noreferrer">打开火山引擎控制台<ArrowRight size={14} /></a></div></li>
      <li><span>2</span><div><strong>先核对网络和费用，再决定创建</strong><p>当前产品发布地域是北京。核对实例地域、规格、存储、备份与订单金额；按量实例也可能从创建完成起持续计费。还没确定产品如何访问数据库时，先别付款，先确认网络方案。</p></div></li>
      <li><span>3</span><div><strong>准备数据库名称、账号和密码</strong><p>实例可用后，在数据库管理与账号管理中创建本产品使用的数据库和账号，授予该库读写及建表权限。记录数据库名称、数据库账号、密码；这些与火山引擎登录账号、AK/SK 不同。</p></div></li>
      <li><span>4</span><div><strong>配置连接地址、SSL 和白名单</strong><p>在实例连接信息中获取主机地址和端口，开启 SSL 加密。将验证服务和上线服务的实际出口地址加入白名单；只放行必要地址。当前验证服务在本机，云端函数还需单独确认网络可达，不能直接把内网地址填给本机。</p><a className="deployment-help-link" href="https://www.volcengine.com/docs/6438/1257674" target="_blank" rel="noreferrer">查看官方白名单操作说明<ArrowRight size={14} /></a></div></li>
      <li><span>5</span><div><strong>回到这里填写并验证</strong><p>按下面五个字段填写，系统自动组合连接地址并处理密码中的特殊字符。验证成功会显示“数据库已连接”，再查看发布方案。</p></div></li>
    </ol>
    <div className="deployment-guide-actions"><button className="ghost-button" type="button" aria-pressed={!advanced} onClick={() => {setAdvanced(false); onChange(""); setFields({host:"",port:"5432",database:"",username:"",password:""});}}>分项填写连接信息</button><button className="ghost-button" type="button" aria-pressed={advanced} onClick={() => {setAdvanced(true);onChange("");setFields({host:"",port:"5432",database:"",username:"",password:""});}}>我已有完整连接地址</button></div>
    {advanced ? <label>PostgreSQL 连接地址<input type="password" name="product-database-connection" autoComplete="new-password" value={value} onChange={event => onChange(event.target.value)} placeholder="postgresql://…?sslmode=require" /></label> : <div className="deployment-database-fields">{([
      ["host", "主机地址", "从实例连接信息复制，不含 https://"], ["port", "端口", "以控制台显示的端口为准"], ["database", "数据库名称", "你为这个产品创建的数据库"], ["username", "数据库账号", "有该库读写和建表权限的账号"], ["password", "数据库密码", "创建数据库账号时设置的密码"],
    ] as const).map(([key, label, hint]) => <label key={key}>{label}<input type={key === "password" ? "password" : "text"} inputMode={key === "port" ? "numeric" : undefined} name={`deployment-db-${key}`} autoComplete="new-password" spellCheck={false} value={fields[key]} onChange={event => update(key,event.target.value)} placeholder={hint}/></label>)}</div>}
  </div>;
}
