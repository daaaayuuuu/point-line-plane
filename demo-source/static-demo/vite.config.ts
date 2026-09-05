import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { cpSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url));
const app=path.resolve(here,'..');
export default defineConfig({
 root:here, base:'./', publicDir:path.join(app,'public'),
 resolve:{alias:[{find:'@/lib/api/client',replacement:path.join(here,'client.ts')},{find:'next/image',replacement:path.join(here,'Image.tsx')},{find:'@',replacement:app}]},
 define:{'process.env.NEXT_PUBLIC_AUTH_MODE':JSON.stringify('static-demo')},
 plugins:[{
  name:'static-demo-compatibility',enforce:'pre',
  resolveId(source,importer){if(source==='./api/client'&&importer?.endsWith('/lib/requirement-runs.ts'))return path.join(here,'client.ts');},
  transform(code,id){
   if(!id.startsWith(app)||id.includes('node_modules')||! /\.[jt]sx?$/.test(id))return;
   // Use the same components. Only make their public asset URLs relative for project Pages.
   code=code.replace(/(["'])\/([^"'\n]+\.(?:svg|png|jpg|webp))\1/g,(_,quote,asset)=>quote+'./'+asset+quote);
   // In this case-study build, reopening the launch tab resumes its built-in completed guide.
   if(id.endsWith('ProductFactoryApp.tsx'))code=code.replace(/window\.sessionStorage\.setItem\(`deployment-fresh-entry:\$\{project\.id\}`, "new"\)/g,'void 0');
   // The built-in Lemon case is already published, even while visitors browse an earlier stage.
   if(id.endsWith('BossSteps.tsx'))code=code
    .replace('const completed = !current && index < completedBeforeIndex;', 'const completed = step.key === "launch" || (!current && index < completedBeforeIndex);')
    .replace('const state = current ? "current" : completed ? "completed" : "pending";', 'const state = step.key === "launch" ? "completed" : current ? "current" : completed ? "completed" : "pending";')
    .replace('const stateLabel = current ? "当前步骤" : completed ? "已完成" : "未完成";', 'const stateLabel = step.key === "launch" ? "已完成" : current ? "当前步骤" : completed ? "已完成" : "未完成";');
   if(id.endsWith('M1ARequirements.tsx'))code=code
    .replace('const canChatWithCodex = project.stage === "REQUIREMENTS" || project.stage === "PRD_REVIEW";', 'const canChatWithCodex = true;')
    .replace('&& project.stage === "PRD_REVIEW"', '&& true');
   if(id.endsWith('M2BDeployment.tsx'))code=code
    .replace('const [accessKey, setAccessKey] = useState("");', 'const [accessKey, setAccessKey] = useState("DEMO_ACCESS_KEY");')
    .replace('const [secretKey, setSecretKey] = useState("");', 'const [secretKey, setSecretKey] = useState("DEMO_SECRET_KEY");')
    .replace('setAccessKey("");', 'setAccessKey("DEMO_ACCESS_KEY");')
    .replace('setSecretKey("");', 'setSecretKey("DEMO_SECRET_KEY");')
    .replace('运行服务和访问入口可能持续计费，准确金额以火山引擎账单为准。停用时需核对本项目的函数和网关，关闭网页不会停止计费。', '这里展示柠檬原案例的费用与服务管理环节。本次 Demo 使用内置数据，不会创建云资源，也不会产生费用。');
   // This original check gates a relative image from API data; its demo fixture uses relative assets.
   if(id.endsWith('M2BDeployment.tsx'))code=code.replace('startsWith("/deployment-previews/")','includes("deployment-previews/")');
   return code;
  },
  closeBundle(){const out=path.resolve(here,'../../site/demo');if(existsSync(out)){
    cpSync(path.join(here,'public'),out,{recursive:true});
    const files=['features/factory/ProductFactoryApp.tsx','features/factory/BossSteps.tsx','features/factory/StagePanels.tsx','features/factory/stages/M1ARequirements.tsx','features/factory/stages/SolutionVisualDecisionView.tsx','features/factory/stages/M1DPreview.tsx','features/factory/stages/M2BDeployment.tsx','app/globals.css','app/design-tokens.css'];
    const sources=Object.fromEntries(files.map(file=>[file,createHash('sha256').update(readFileSync(path.join(app,file))).digest('hex')]));
    writeFileSync(path.join(out,'ui-source-manifest.json'),JSON.stringify({mode:'original-components-with-demo-data',sources},null,2));
   }}
 },react()],
 css:{postcss:path.join(app,'postcss.config.mjs')},
 build:{outDir:path.resolve(here,'../../site/demo'),emptyOutDir:true},
});
