"use client";

import { Check, ExternalLink } from "lucide-react";
import Image from "next/image";

export const UI_STYLE_OPTIONS = [
  { key: "duolingo-sticker", name: "游戏化任务", source: "Duolingo", note: "分步任务、进度反馈与厚边主按钮", preview: "/ui-style-previews/duolingo-sticker.jpg", url: "https://styles.refero.design/style/7088d695-362b-4e09-b325-fa8136d4f350" },
  { key: "getharvest-workbench", name: "暖橙工作台", source: "Getharvest", note: "工时追踪、账单状态与工作流操作", preview: "/ui-style-previews/getharvest-workbench.jpg", url: "https://styles.refero.design/style/1eee9aa2-1e23-4675-9f6e-fb98c93969bd" },
  { key: "lpalo-storybook", name: "绘本内容库", source: "Lpalo", note: "胶囊导航、内容卡片与趣味浏览路径", preview: "/ui-style-previews/lpalo-storybook.jpg", url: "https://styles.refero.design/style/79b4ebc4-30f6-45b6-b2d2-922e28e05ca9" },
  { key: "superr-notebook", name: "贴纸笔记本", source: "Superr", note: "纸感任务卡、贴纸反馈与描边操作", preview: "/ui-style-previews/superr-notebook.jpg", url: "https://styles.refero.design/style/cfd0fec1-f25a-4b9b-9bd0-d5b66960f2f2" },
  { key: "dovetail-midnight", name: "深夜洞察台", source: "Dovetail · SaaS", note: "数据看板、洞察筛选与分析结果操作", preview: "/ui-style-previews/dovetail-midnight.jpg", url: "https://styles.refero.design/style/108e2695-6970-47d5-b5b0-eea8fc34e048" },
  { key: "lepuzz-newspaper", name: "怪趣商店", source: "Le Puzz", note: "商品网格、筛选导航与快捷操作", preview: "/ui-style-previews/lepuzz-newspaper.jpg", url: "https://styles.refero.design/style/66e7b131-d68c-4751-954c-f5d0d8869647" },
  { key: "obscura-pixel", name: "像素工具台", source: "Obscura", note: "功能导航、连接状态与设置面板", preview: "/ui-style-previews/obscura-pixel.jpg", url: "https://styles.refero.design/style/c445eb73-e403-4a00-8b90-f454c9181fd6" },
  { key: "notion-workspace", name: "温暖协作台", source: "Notion · SaaS", note: "侧边工作区、看板状态与轻量协作反馈", preview: "/ui-style-previews/notion-workspace.jpg", url: "https://styles.refero.design/style/2bf4c61f-de10-4614-ba1b-20c0453bd2a9" },
] as const;

export type UiStyleKey = (typeof UI_STYLE_OPTIONS)[number]["key"];

const UI_STYLE_STORAGE_PREFIX = "product-factory-ui-style:";

export function loadUiStylePreference(projectId: string): UiStyleKey | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(`${UI_STYLE_STORAGE_PREFIX}${projectId}`);
    return UI_STYLE_OPTIONS.some((item) => item.key === value) ? value as UiStyleKey : null;
  } catch {
    return null;
  }
}

export function saveUiStylePreference(projectId: string, value: UiStyleKey): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(`${UI_STYLE_STORAGE_PREFIX}${projectId}`, value);
  } catch {
    // The selected value remains usable for this session when browser storage is unavailable.
  }
}

type UiStylePickerProps = {
  value: UiStyleKey;
  onChange: (value: UiStyleKey) => void;
};

export function UiStylePicker({ value, onChange }: UiStylePickerProps) {
  return (
    <section className="ui-style-picker" aria-labelledby="ui-style-picker-title">
      <div className="ui-style-picker-heading">
        <div><span>生成前选择</span><h2 id="ui-style-picker-title">这个网页想用哪种 UI？</h2><p>8 种风格都能直接用于网页生成，适合工具、内容、任务与协作场景；只参考设计语言，不复制品牌资产。</p></div>
        <a href="https://styles.refero.design/?q=productivity%20app" target="_blank" rel="noreferrer">查看来源<ExternalLink size={14} /></a>
      </div>
      <div className="ui-style-options" role="radiogroup" aria-label="选择网页 UI 风格">
        {UI_STYLE_OPTIONS.map((item) => {
          const selected = item.key === value;
          return (
            <button key={item.key} className={selected ? "selected" : ""} type="button" role="radio" aria-checked={selected} onClick={() => onChange(item.key)}>
              <span className="ui-style-preview"><Image src={item.preview} width={800} height={500} sizes="(max-width: 640px) 112px, (max-width: 1100px) 50vw, 25vw" unoptimized alt={`${item.source} ${item.name}风格网页预览`} /></span>
              <span className="ui-style-copy"><strong>{item.name}</strong><small>{item.source}</small><em>{item.note}</em></span>
              <span className="ui-style-check">{selected && <Check size={14} />}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
