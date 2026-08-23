import { type FormEvent, useState } from "react";
import {
  CheckCircle2,
  ClipboardCheck,
  Eye,
  EyeOff,
  FileUp,
  MonitorPlay,
  Rocket,
} from "lucide-react";

const benefits = [
  {
    icon: FileUp,
    title: "上传点子或 PRD",
    description: "用一句话或现有文档开始，Agent 帮你补全真正的产品需求。",
  },
  {
    icon: ClipboardCheck,
    title: "确认产品方案",
    description: "产品范围、用户流程、技术路线与费用风险，都由你确认。",
  },
  {
    icon: MonitorPlay,
    title: "生成与预览",
    description: "自动生成可运行产品，在真实预览中体验并直接提出修改。",
  },
  {
    icon: Rocket,
    title: "部署与上线",
    description: "获得线上地址、完整代码、测试报告和可下载的交付包。",
  },
];

function DotLogo() {
  return (
    <span className="brand-mark dot-logo" aria-hidden="true">
      {Array.from({ length: 24 }, (_, index) => <i key={index} />)}
    </span>
  );
}

export function App() {
  const [displayName, setDisplayName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [showInviteCode, setShowInviteCode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  function resetDemo() {
    setDisplayName("");
    setInviteCode("");
    setMessage("");
    setShowInviteCode(false);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    if (!displayName.trim() || !inviteCode.trim()) {
      setMessage("请填写账号名称和邀请码。");
      return;
    }

    setBusy(true);
    window.setTimeout(() => {
      setBusy(false);
      setMessage("前端交互演示已完成，当前版本未连接后端。");
    }, 650);
  }

  const success = message.startsWith("前端");

  return (
    <main className="login-layout">
      <section className="login-story" aria-labelledby="product-title">
        <button className="brand" type="button" onClick={resetDemo} aria-label="重置登录演示">
          <DotLogo />
          <span>
            <strong>点线面</strong>
            <small>AI 产品交付平台</small>
          </span>
        </button>

        <h1 id="product-title">
          不需要看代码
          <br />
          <em>看着产品长出来</em>
        </h1>

        <div className="login-benefits">
          {benefits.map(({ icon: Icon, title, description }, index) => (
            <article className="login-benefit-card" key={title}>
              <div className="login-benefit-meta">
                <span><Icon size={19} strokeWidth={1.8} /></span>
                <small>0{index + 1}</small>
              </div>
              <h2>{title}</h2>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="login-panel" aria-labelledby="login-title">
        <header className="login-panel-header">
          <h2 id="login-title">登录平台</h2>
          <p>登录后继续管理和交付你的产品</p>
        </header>

        <form onSubmit={handleSubmit} noValidate>
          <div className="login-fields">
            <label>
              账号名称
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="请输入账号名称"
                autoComplete="username"
                aria-invalid={Boolean(message) && !displayName.trim()}
              />
            </label>

            <label>
              邀请码
              <span className="password-field">
                <input
                  value={inviteCode}
                  onChange={(event) => setInviteCode(event.target.value)}
                  placeholder="请输入邀请码"
                  type={showInviteCode ? "text" : "password"}
                  autoComplete="one-time-code"
                  aria-invalid={Boolean(message) && !inviteCode.trim()}
                />
                <button
                  type="button"
                  onClick={() => setShowInviteCode((value) => !value)}
                  aria-label={showInviteCode ? "隐藏邀请码" : "显示邀请码"}
                >
                  {showInviteCode ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </span>
            </label>
          </div>

          {message && (
            <div className={`inline-message ${success ? "success" : "error"}`} role="status">
              {success && <CheckCircle2 size={16} />}
              <span>{message}</span>
            </div>
          )}

          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? <><span className="button-spinner" />正在登录…</> : "登录"}
          </button>
        </form>

        <small>此页仅用于前端样式与交互演示，不会提交任何数据。</small>
      </section>
    </main>
  );
}
