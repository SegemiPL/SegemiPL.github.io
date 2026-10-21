---
title: 导航栏 CSS 改造（二）：Flex 布局与视觉居中
date: 2026-10-21
icon: lucide/panels-top-left
description: 调整 gap、padding 和 Flex 对齐，让导航文字在选中块里真正居中。
---

# 导航栏 CSS 改造（二）：Flex 布局与视觉居中

## 效果

![header2](../assets/blog/header_2.png)

## 改动的代码
```tsx
{/*最外层的 div*/}
<div className="flex relative items-center text-[0.8125rem] tracking-wider border-2 rounded-2xl py-2 shadow-md">

{/*flex项目*/}
<div key={item.href} className="flex px-5 items-center justify-center">

{/*选择块*/}
{className="absolute top-0 left-0 w-1/4 p-2 z-0 h-full bg-orange-100 rounded-xl"}

```
## 说明

期望的效果是文字位于 1/4 块的正中间，但最开始显然不是这个样子的，DevTool 去看了看元素的布局，发现有以下问题导致了这个情况：
1. 最外层 flex 中有 gap，这导致每个 flex 项目占的实际位置不是 1/4，我们希望 flex 项目按比例充满整个外层容器，因此删掉 gap
2. 最外层 flex 中一开始还有 padding，导致中间两项确实居中了，但外面两项在视觉上没有居中（相当于两边到 border 多了一个 padding 的空白）
3. flex 项内部的布局，直接将 flex 项目也赋予 flex，然后 items-center justify-center 水平垂直居中即可

剩下的就是阴影和圆角，一下下的事，主要比较有趣的还是居中问题，这种 padding 导致的视觉不居中还是比较难看出来的
