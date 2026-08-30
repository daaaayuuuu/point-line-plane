/* eslint-disable @next/next/no-img-element -- These are exact SVG exports from the linked Figma component. */

type BossStepItem<Key extends string> = {
  key: Key;
  label: string;
};

type BossStepsProps<Key extends string> = {
  steps: readonly BossStepItem<Key>[];
  activeKey: Key;
  completedBeforeIndex: number;
  onChange: (key: Key) => void;
};

export function BossSteps<Key extends string>({ steps, activeKey, completedBeforeIndex, onChange }: BossStepsProps<Key>) {
  return (
    <nav className="boss-steps" aria-label="产品创建进度" data-figma-node-id="85798:175">
      {steps.map((step, index) => {
        const current = step.key === activeKey;
        const completed = !current && index < completedBeforeIndex;
        const state = current ? "current" : completed ? "completed" : "pending";
        const stateLabel = current ? "当前步骤" : completed ? "已完成" : "未完成";

        return (
          <div className={`boss-step-item ${state}`} key={step.key}>
            <div className="boss-step-header">
              <button
                className="boss-step-trigger"
                type="button"
                onClick={() => onChange(step.key)}
                aria-current={current ? "step" : undefined}
                aria-label={`${step.label}，${stateLabel}`}
              >
                <span className="boss-step-progress" aria-hidden="true">
                  {completed ? <img src="/boss-step-check-outlined.svg" alt="" /> : <span>{index + 1}</span>}
                </span>
                <span className="boss-step-label">{step.label}</span>
              </button>
              {index < steps.length - 1 && (
                <span className="boss-step-tail" aria-hidden="true">
                  <img src={index < completedBeforeIndex ? "/boss-step-tail-complete.svg" : "/boss-step-tail-pending.svg"} alt="" />
                </span>
              )}
            </div>
          </div>
        );
      })}
    </nav>
  );
}
