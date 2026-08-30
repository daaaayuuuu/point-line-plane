"use client";

import { Check, ExternalLink } from "lucide-react";
import Image from "next/image";

export const UI_STYLE_OPTIONS = [
  { key: "slack-aubergine", name: "紫色舞台", source: "Slack", note: "深紫品牌区与柔和浅紫表面", preview: "/ui-style-previews/slack-aubergine.jpg", url: "https://styles.refero.design/style/e26cb9b0-f876-41ff-9f24-fd67a6b9776c" },
  { key: "pirsch-paper", name: "纸张笔记", source: "Pirsch", note: "暖白纸张、黑色细线与荧光黄", preview: "/ui-style-previews/pirsch-paper.jpg", url: "https://styles.refero.design/style/e4b9d41a-8165-47dd-818a-5f6810046ea9" },
  { key: "aira-editorial", name: "黑白编辑", source: "Aira", note: "报刊式大标题与克制黑白灰", preview: "/ui-style-previews/aira-editorial.jpg", url: "https://styles.refero.design/style/750387be-bda4-448b-950f-c9356c3ec25f" },
  { key: "atlassian-confetti", name: "彩色工程", source: "Atlassian", note: "企业蓝主操作与彩色几何点缀", preview: "/ui-style-previews/atlassian-confetti.jpg", url: "https://styles.refero.design/style/c08ebca5-87d4-4c19-a5d7-ae5e670dae11" },
  { key: "ameba-midnight", name: "深夜玻璃", source: "Ameba", note: "午夜蓝画布与电光青玻璃面板", preview: "/ui-style-previews/ameba-midnight.jpg", url: "https://styles.refero.design/style/371df039-a090-402b-b2e4-21ab38e07625" },
  { key: "sprout-contrast", name: "黑白高对比", source: "Sprout", note: "纯黑结构、白色画布与嫩绿强调", preview: "/ui-style-previews/sprout-contrast.jpg", url: "https://styles.refero.design/style/da7c4464-f135-41fc-b635-99c6f4dc58e6" },
  { key: "surfshark-coastal", name: "海岸双色", source: "Surfshark", note: "明亮青绿与珊瑚红的消费级 SaaS", preview: "/ui-style-previews/surfshark-coastal.jpg", url: "https://styles.refero.design/style/4fc7a535-3c99-4ffe-8365-7d025d33274e" },
  { key: "pop-typographic", name: "巨型排版", source: "Pop Site", note: "极大黑色标题与单一信号蓝", preview: "/ui-style-previews/pop-typographic.jpg", url: "https://styles.refero.design/style/e7d4a7de-aeaf-4d49-8c0c-0dedd05a8992" },
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
        <div><span>生成前选择</span><h2 id="ui-style-picker-title">这个网页想用哪种 UI？</h2><p>已从你提供的 Refero SaaS 风格库中随机挑选 8 个差异明显的方向。只借鉴设计语言，不复制品牌资产。</p></div>
        <a href="https://styles.refero.design/?q=saas" target="_blank" rel="noreferrer">查看来源<ExternalLink size={14} /></a>
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
