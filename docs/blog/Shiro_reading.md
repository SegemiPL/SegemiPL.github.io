---
title: Shiro 阅读笔记：Next.js 文件路由
date: 2026-10-21
icon: lucide/book-open
description: 从 Shiro 的目录结构理解 Next.js 文件路由、嵌套布局与路由分组。
---

# Shiro 阅读笔记：Next.js 文件路由

## 文件路由

Next.js 文件路由，阅读这个仓库感觉比较重要的就三个
- 基本文件路由：
    - 正常目录即对应 URL
    - layout 所在的样式应用于本目录所有页面（包括子目录）
    - page 相当于叶子节点，是最终放入的 children 元素

逻辑大概是这样的，对于一个 url，找到当前层以及上层的所有目录的 layout，逐次拼接起来，再加上最终叶子的 page，得到完整 html
```
/blog/react/article1 的拼接顺序：
app_layout --> blog_layout ---> react_layout ---> article1_layout --->
article1_page
```
- 动态参数路由：
    - 目录名形式为：`[param]`
    - 和基本文件路由的区别是：param 可以被捕捉并作为参数传入下层的所有 page 和 layout

- 分组：
    - 目录名形式为：`(group)`
    - 分组不进入 url 但创建一个新的目录层级，可以套 layout

分组的一个经典的例子：
```
- app
    - (home)
        - layout.tsx
        - page.tsx
    - about
    - blog
    - friend
    - layout.tsx
```
现在，在 url 为 `/` 时，应该显示 home page。
我们希望 home page 可以有一层单独的 layout（不会影响 blog、friend 等其他页面）
但不希望用一个真正的 `/home` url，只是单纯的在 `/` 时显示 home page
这时分组就起到了一个**不进入 url** 的**单独层级**的作用
