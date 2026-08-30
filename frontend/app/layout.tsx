import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  preload: false,
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  preload: false,
});

export const metadata: Metadata = {
  title: "点线面｜从产品想法到正式交付",
  description: "面向非技术产品创造者的四阶段 AI 产品工厂。",
  openGraph: {
    title: "点线面｜从产品想法到正式交付",
    description: "从一个想法开始，看着产品生成、预览并正式上线。",
    locale: "zh_CN",
    type: "website",
    images: [
      {
        url: "/product-factory-social.png",
        width: 1731,
        height: 909,
        alt: "从产品想法到正式上线的四阶段产品工厂",
      },
    ],
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
