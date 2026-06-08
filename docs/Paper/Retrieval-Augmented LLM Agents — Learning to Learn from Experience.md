---
date: 2026-04-26
icon: lucide/scroll-text
description: ExpRAG 用检索增强 + 经验学习机制，让 LLM agent 从历史交互中持续学习和改进。
---

# 论文阅读笔记 — ExpRAG：检索增强的LLM智能体

## 元信息

| 字段 | 内容 |
| --- | --- |
| 标题 | Retrieval-Augmented LLM Agents: Learning to Learn from Experience |
| arXiv | [2603.18272](https://arxiv.org/abs/2603.18272) |
| 作者 | Thomas Palmeira Ferraz, Romain Deffayet, Vassilina Nikoulina, Hervé Déjean, Stéphane Clinchant（NAVER LABS Europe） |
| 代码 | 未公开 |
| 基础模型/数据 | Ministral 3-8B, Gemma 3-4B, Qwen 2.5-7B, Qwen 2.5-7B-1M；ALFWorld + ScienceWorld |

!!! tip "精读建议"

    本文建议重点阅读：
    - **Section 4.3（Inference-only ExpRAG 消融）**：K 值、static vs. dynamic、index 构成的设计选择分析是最实用的部分
    - **Section 4.4（ExpRAG-LoRA）**：训练中融入检索的实验结果，以及 OOD 泛化的反直觉发现（validation loss 上升但 OOD 性能继续提升）
    - Introduction 的 Table 1 和 Related Work 可以速读

## 一句话总结

!!! abstract "TL;DR"

    本文提出 ExpRAG 框架，将经验轨迹检索（experience retrieval）与 LLM agent 的监督微调相结合。核心思路是：从过去的交互轨迹（episodic memory）中检索相关的成功/失败经验作为 in-context prompt，并在 LoRA 微调过程中同步注入检索结果，使模型学会如何在上下文中利用检索到的经验。实验在 ALFWorld 和 ScienceWorld 上表明，ExpRAG-LoRA 在 unseen task（OOD）上的泛化能力远超纯 LoRA 或纯检索的单独使用。

---

## 1 问题与动机

### 1.1 现有方法的不足

LLM agent 在面对 unseen task 时泛化能力不足。现有两条路线各有局限：

- **Fine-tuning（SFT）**：在训练任务上表现好，但 OOD 泛化差，容易出现 distribution shift 和 compounding errors
- **Memory-augmented generation**（检索经验）：无需训练，但效果通常不如有监督 baseline；且大多数工作仅做 inference-time retrieval，未研究如何在训练中融入检索

### 1.2 关键的研究缺口

- 如何在 **训练阶段** 就让模型学会利用检索到的轨迹？
- 经验检索的关键设计选择（存储什么、如何查询、检索多少、何时检索）缺乏系统分析
- 检索增强训练能否同时保持 in-distribution 性能并提升 OOD 泛化？

### 1.3 本文目标

1. 建立一个强的 SFT + 检索 baseline
2. 系统分析 ExpRAG 的设计选择
3. 提出 ExpRAG-LoRA：将经验检索融入微调过程，实现"learn to learn from experience"

---

## 2 方法：ExpRAG 框架

### 2.1 Agent 交互形式化

考虑一个 LLM agent 在文本环境中执行任务 $\mathcal{T}$，最多进行 $T$ 步交互。在第 $t$ 步（$t = 1, 2, \dots, T$）：

- 环境返回文本观察（observation）$o_t$，描述当前环境状态和可执行的动作
- Agent 根据当前历史 $h_t$ 输出动作（action）$a_t$，$a_t$ 是从预定义的动作模板集合中选取的自然语言指令
- 环境执行 $a_t$，返回下一观察 $o_{t+1}$

一条完整的 **交互轨迹**（trajectory）定义为：

$$
\tau = (\mathcal{T},\; o_1,\; a_1,\; o_2,\; a_2,\; \dots,\; o_T)
$$

其中 $\mathcal{T}$ 是任务描述（task description），$T$ 是实际交互步数（可能因任务完成或超时提前终止）。

在决策时刻 $t$，agent 可用的 **交互历史**（interaction history）$h_t$ 定义为在当前步之前已发生的所有观察-动作对：

$$
h_t = (\mathcal{T},\; o_1,\; a_1,\; o_2,\; a_2,\; \dots,\; o_t)
$$

注意 $h_t$ 以 $o_t$ 结尾（当前的观察），不包含 $a_t$（尚未选择）。

LLM 策略（policy）$\pi_\theta$ 是一个参数化的条件分布，输入历史 $h_t$，输出动作 $a_t$：

$$
a_t \sim \pi_\theta(\cdot \mid h_t)
$$

其中 $\theta$ 是 LLM 的参数。本文考虑两种使用 $\pi_\theta$ 的方式：
- **Frozen**：$\theta$ 不变，仅通过 in-context retrieval 改变输入
- **Fine-tuned**：通过 SFT 更新 $\theta$

!!! info "形式化说明"

    该形式化本质上是一个 **部分可观测马尔可夫决策过程**（POMDP），其中：
    - 状态：环境内部状态（不可直接观测）
    - 观察 $o_t$：对状态的文本描述
    - 动作 $a_t$：自然语言指令
    - 策略 $\pi_\theta$：从历史到动作的映射
    - 奖励/成功信号：仅在 episode 结束后给出

### 2.2 轨迹编码与训练目标

#### 2.2.1 Chat-template 序列化

轨迹被编码为多轮对话格式，使用 base model 自带的 chat template：

- **观察 $o_t$** → 编码为 **user role** 的消息（模拟用户向 agent 报告环境状态）
- **动作 $a_t$** → 编码为 **assistant role** 的消息（模拟 agent 的决策输出）

形式化地，给定轨迹 $\tau$，其序列化结果为一个 token 序列：

$$
\text{encode}(\tau) = [\text{user}(o_1),\; \text{assistant}(a_1),\; \text{user}(o_2),\; \text{assistant}(a_2),\; \dots,\; \text{user}(o_T)]
$$

其中 $\text{user}(\cdot)$ 和 $\text{assistant}(\cdot)$ 分别表示用 chat template 包裹后的消息所对应的 token 序列。

#### 2.2.2 训练目标

SFT 使用标准的 **next-token prediction loss**，但 **仅在 assistant token 上计算 loss**（user token 不参与 loss 计算）。对于一条轨迹 $\tau$，损失函数为：

$$
\mathcal{L}_{\text{SFT}}(\theta) = -\frac{1}{|\mathcal{A}(\tau)|} \sum_{x \in \mathcal{A}(\tau)} \log P_\theta(x \mid \text{context}(x))
$$

其中：
- $\mathcal{A}(\tau)$ 是轨迹中所有属于 assistant 消息的 token 集合（即所有 $a_t$ 包含的 token）
- $\text{context}(x)$ 是 token $x$ 之前的所有 token（即其前缀上下文）
- $P_\theta(x \mid \cdot)$ 是 LLM 在参数 $\theta$ 下对 token $x$ 的预测概率

!!! tip "KV-cache 复用"

    由于轨迹被编码为完整的多轮对话（而非逐 step 独立编码），训练时可以对一整条轨迹复用 KV-cache：前缀 token 的 key-value 表示在生成后续 token 时被缓存并复用。这比逐 step 编码（每步重新编码完整上下文）在训练速度上有显著提升。这是本文 SFT pipeline 的实现细节优势之一。

#### 2.2.3 LoRA 适配

本文使用 **LoRA**（Low-Rank Adaptation）进行参数高效微调。LoRA 在预训练权重矩阵 $W_0 \in \mathbb{R}^{d \times k}$ 旁引入低秩分解的可训练增量：

$$
W = W_0 + \Delta W = W_0 + B A
$$

其中：
- $A \in \mathbb{R}^{r \times k}$，$B \in \mathbb{R}^{d \times r}$
- $r \ll \min(d, k)$ 为秩（rank），本文取 $r = 8$
- 训练时仅更新 $A, B$，$W_0$ 保持冻结

LoRA 作用于 attention 层的四个投影矩阵：$W_Q$（query）、$W_K$（key）、$W_V$（value）、$W_O$（output），对应代码中的 `q_proj, k_proj, v_proj, output_proj`。

训练超参数详见 Section 3.1。

### 2.3 经验索引与检索

#### 2.3.1 经验库构建

从前收集的交互轨迹构成 **经验库**（experience bank/experience index）$\mathcal{I}$：

$$
\mathcal{I} = \{ (\tau_1,\; e_1),\; (\tau_2,\; e_2),\; \dots,\; (\tau_N,\; e_N) \}
$$

其中：
- $\tau_i$：第 $i$ 条完整轨迹
- $e_i = \phi(\tau_i) \in \mathbb{R}^d$：轨迹的嵌入向量（embedding），由 **轨迹编码器**（trajectory encoder）$\phi$ 计算
- $\phi$ 使用的是 **Qwen3-Embedding-0.6B**（一个专门训练的 sentence embedding 模型），在全部实验中固定不变
- $d$ 为嵌入向量的维度
- $N$ 为经验库大小

!!! info "轨迹内容"

    编码器 $\phi$ 以轨迹的 **文本表示**（经 chat template 格式化的完整对话）作为输入，输出一个固定长度的向量。嵌入捕获的是轨迹的整体语义——包括任务类型、交互模式、成功/失败结果等。

经验库在离线阶段一次性构建，推理时不再更新（read-only memory）。构建时包含 **成功和失败** 的轨迹。

#### 2.3.2 查询构建与相似度检索

在交互的决策时刻 $t$，需要从经验库中检索与当前情境最相关的轨迹。检索流程：

**Step 1 — 构造查询**：将当前的任务描述和交互历史拼接为查询文本 $q_t$：

$$
q_t = \text{concat}(\mathcal{T},\; h_t)
$$

**Step 2 — 编码查询**：用相同的轨迹编码器 $\phi$ 编码查询文本，得到查询向量：

$$
e_q = \phi(q_t) \in \mathbb{R}^d
$$

**Step 3 — 计算相似度**：用点积（dot product）计算 $e_q$ 与经验库中每条轨迹嵌入 $e_i$ 的相似度：

$$
\text{sim}(e_q,\; e_i) = e_q^\top e_i
$$

**Step 4 — Top-K 检索**：选出相似度最高的 $K$ 条轨迹：

$$
\mathcal{R}_t = \underset{(\tau_i, e_i) \in \mathcal{I}}{\text{top-}K}\; e_q^\top e_i
$$

其中 $\mathcal{R}_t$ 是检索到的 $K$ 条轨迹的集合，下标 $t$ 表示该集合可能与时间步有关（dynamic 模式下会变化）。

!!! warning "检索粒度说明"

    检索是以 **整条轨迹** 为单位的，而不是按 step 或按 observation-action pair。这意味着检索到的每条轨迹都包含完整的任务描述和多步交互，可能跨越不同的任务类型。

### 2.4 经验条件生成（Experience-Conditioned Generation）

#### 2.4.1 Memory Block 构造

检索到的 $K$ 条轨迹被整理为一个 **memory block** $m_t$，其格式化为：

- 使用 header 文本标记 retrieved memory 区域的开始/结束
- 按成功/失败将轨迹分为两组，各自标注（如 `[Successful Experience]` / `[Failed Experience]`）
- 每条轨迹保留其完整的对话格式（user/assistant 交替）

Memory block 在形式上是一个纯文本片段，直接拼接到 prompt 中。

#### 2.4.2 条件动作生成

Memory block $m_t$ 被插入 system prompt（系统提示词），位于任务描述和交互历史之前。动作生成的条件分布变为：

$$
a_t \sim \pi_\theta(\cdot \mid m_t,\; h_t)
$$

即在检索到的历史经验和当前交互历史的联合条件下生成动作。直观上，$m_t$ 为模型提供了"遇到类似情况时别人是怎么做的"作为参考。

#### 2.4.3 检索模式：Static vs. Dynamic

论文定义了两种检索触发策略：

| 模式 | 检索时机 | $m_t$ 的更新 |
| --- | --- | --- |
| **Static** | 仅在 $t = 0$（episode 开始）检索一次 | $m_t = m_0$ 在整个 episode 中保持不变 |
| **Dynamic** | 每个决策步 $t$ 都重新检索 | $m_t$ 每步更新，反映最新的交互历史 $h_t$ |

!!! warning "Dynamic 的 context churn 问题"

    Dynamic 模式虽能根据最新历史检索更相关的轨迹，但存在 **上下文震荡**（context churn）：前一步的检索结果从 prompt 中移除，被新的结果替换。这意味着模型看到的历史动作（由之前的 memory block 指导做出的）与当前 memory block（不再包含那些指导轨迹）之间可能产生不一致。论文实验表明 dynamic 在 index 匹配时略好，但在 index 不匹配时反而更不稳定。

#### 2.4.4 完整推理流程

将上述组件组合，一个 episode 的完整推理流程如下：

1. 接收任务描述 $\mathcal{T}$
2. **(Static 模式在此时检索一次)** 构造 $q_0$，检索 $\mathcal{R}_0$，构建 $m_0$
3. 对于 $t = 1, 2, \dots, T$：
   - 接收观察 $o_t$
   - **(Dynamic 模式在此时检索)** 构造 $q_t$，检索 $\mathcal{R}_t$，构建 $m_t$
   - 将 $m_t$、$\mathcal{T}$、$h_t$ 组装为 prompt，输入 LLM
   - LLM 生成 $a_t \sim \pi_\theta(\cdot \mid m_t, h_t)$
   - 环境执行 $a_t$，返回 $o_{t+1}$
4. Episode 结束，评估是否成功

### 2.5 ExpRAG-LoRA：检索增强微调

前述 2.3–2.4 节描述的是 inference-only ExpRAG（模型参数 $\theta$ 冻结，仅靠 retrieved context 提升性能）。ExpRAG-LoRA 进一步将检索融入 **训练过程**。

#### 2.5.1 训练数据构造

对于训练集中的每条成功轨迹 $\tau$，在训练时：
- 用 $\tau$ 所属的 easy 任务 split 构建检索 index $\mathcal{I}_{\text{train}}$
- 对于 $\tau$ 中的每个决策步，用该步的历史 $h_t$ 作为查询，从 $\mathcal{I}_{\text{train}}$ 中检索 $K$ 条轨迹
- 将检索到的 memory block $m_t$ 拼接到训练样本的 prompt 中

因此训练样本不再是 $(h_t, a_t)$，而是 $(m_t, h_t, a_t)$——模型在训练时就学习如何 **利用检索到的经验来辅助决策**。

#### 2.5.2 训练目标

ExpRAG-LoRA 的训练目标与标准 SFT 相同（next-token prediction on assistant tokens），唯一的区别是输入上下文包含了 $m_t$：

$$
\mathcal{L}_{\text{ExpRAG-LoRA}}(\theta) = -\frac{1}{|\mathcal{A}|} \sum_{x \in \mathcal{A}} \log P_\theta(x \mid m_t,\; \text{context}(x))
$$

#### 2.5.3 推理

ExpRAG-LoRA 训练完成后，推理时同样使用 ExpRAG 检索（与 inference-only ExpRAG 的推理流程一致），用 hard 任务的 index 进行检索。

#### 2.5.4 对比方法

论文设置了三组对比以分离 retrieval 和 training 的贡献：

| 方法 | 训练时注入 $m_t$？ | 推理时注入 $m_t$？ | 说明 |
| --- | --- | --- | --- |
| **ExpRAG**（frozen） | 否（无训练） | 是 | 纯 in-context retrieval 的 baseline |
| **LoRA**（no ExpRAG） | 否 | 否 | 标准 SFT，测量参数更新的单独贡献 |
| **LoRA + ExpRAG** | 否 | 是 | SFT 训练，推理时启用检索；测量训练后外加检索的效果 |
| **ExpRAG-LoRA** | 是 | 是 | 检索增强训练 + 检索增强推理；本文核心方法 |

---

## 3 实验

### 3.1 实验设置

#### 3.1.1 评测环境

**ALFWorld**：
- 类型：文本化的家居操作任务（基于 ALFRED benchmark 的文本版）
- 交互：agent 通过自然语言指令操作虚拟家居环境中的物体
- 动作空间：预定义的动作模板（如 `go to <recep> <obj>`, `take <obj> from <recep>`, `put <obj> in/on <recep>`, `heat/cool/clean <obj> with <recep>` 等）
- 评估指标：二值成功/失败（episode 结束或达到 $T$ 步时是否完成任务目标）
- 任务种类：6 种 task-type（如 `pick_and_place_simple`、`pick_clean_then_place_in_recep`、`pick_two_obj_and_place` 等）
- 最大步数：$T = 50$
- 动作列表：给模型的是一个 **全局动作模板列表**（所有合法动作的模板），而非每步的 valid actions

**ScienceWorld**：
- 类型：科学实验模拟任务
- 交互：agent 在模拟的科学实验环境中进行观察和操作
- 原始指标：dense episode score $\in [-1, 1]$（每一步都有部分得分）
- 二值化：为与 ALFWorld 统一评估框架，将 score 转换为二值（成功/失败）
- 任务种类：10 个 topic（如 `find-plant`、`boil`、`melt`、`grow-plant`、`mendelian-genetics`、`chemistry-mix`、`test-conductivity` 等）
- 最大步数：$T = 50\text{–}150$（因任务而异）

!!! info "全局动作模板 vs. 每步 valid actions"

    作者刻意选择提供一个 **全局的** 动作模板列表（整个环境中所有可能的动作格式），而非每步动态给出的 valid actions。这增加了任务难度（模型需要自己判断哪些动作在当前状态下合法），但也更贴近真实场景（真实环境中通常没有 oracle 告诉你哪些动作合法）。

#### 3.1.2 OOD 泛化评估设计

标准 ALFWorld/ScienceWorld 的 train/test split 是在 **同组 task-type 内采样的**，导致 test set 与 training distribution 过于接近。本文作者重新设计了更加严格的 OOD split：

- 将 task-type（任务类型）按语义难度和复杂程度分为两组：
  - **Easy 任务**：较简单的任务类型，用于训练
  - **Hard 任务**：较复杂的任务类型，**完全不出现在训练中**，用于 OOD 测试
- 训练集仅包含 easy 任务的 expert trajectories
- 测试时分别评估 **in-distribution**（easy test）和 **out-of-distribution**（hard test）

具体划分如下：

| Split | ALFWorld 样本数 | ALFWorld 任务类型 | ScienceWorld 样本数 | ScienceWorld 任务类型 |
| --- | --- | --- | --- | --- |
| easy (train) | train=1748, test=73 | look_at_obj_in_light, pick_clean_then_place_in_recep, pick_and_place_simple | train=2335, test=1183 | 17 种（含 find-plant, boil, melt, freeze, find-animal 等基础任务） |
| hard (test) | train=1805, test=61 | pick_cool_then_place_in_recep, pick_heat_then_place_in_recep, pick_two_obj_and_place | train=1254, test=636 | 13 种（含 chemistry-mix, mendelian-genetics, grow-plant, test-conductivity 等需要多步推理的复杂任务） |

!!! warning "注意"

    Hard split 也有 train 样本（用于构建检索 index），但 **绝不用于模型训练**。Easy train 样本同时用于 SFT 训练和构建 easy index。

#### 3.1.3 模型选择

论文选用中等规模的开源 instruction-tuned 模型（3B–8B 参数范围），以研究较弱模型的检索增强效果：

| 模型 | 参数量 | 特点 |
| --- | --- | --- |
| `mistralai/Ministral-3-8B-Instruct-2512-BF16` | 8B | 主力实验模型 |
| `google/gemma-3-4b-it` | 4B | 较小模型，检验弱模型的检索增益 |
| `Qwen/Qwen2.5-7B-Instruct` | 7B | 强 in-context learning 能力 |
| `Qwen/Qwen2.5-7B-Instruct-1M` | 7B | 支持 1M 长上下文，检验长上下文对检索增强的影响 |

此外在附录中测试了 Qwen 2.5-3B。

#### 3.1.4 训练配置

| 参数 | 值 | 含义/说明 |
| --- | --- | --- |
| Optimizer | PagedAdamW8bit | 8-bit 量化 AdamW，节省显存 |
| Learning rate | 5e-5 | 恒定学习率 |
| LR scheduler | constant | 不衰减 |
| Weight decay | 0.0 | 无权重衰减 |
| LoRA rank $r$ | 8 | 低秩分解的秩 |
| LoRA $\alpha$ | 16 | LoRA 缩放因子（$\Delta W$ 实际缩放为 $\frac{\alpha}{r} \cdot BA$） |
| LoRA dropout | 0.1 | LoRA 层的 dropout 率 |
| LoRA target modules | q_proj, v_proj, k_proj, output_proj | Attention 四投影矩阵 |
| dtype | bf16 | bfloat16 混合精度 |
| Decoding temperature | 0.0（greedy） | 确定性解码 |
| Random seed | 2025 | 实验可复现 |
| 硬件 | 单卡 80GB NVIDIA A100 | — |

训练 epoch 数：最多 50 epoch（远超常规 fine-tuning 的 3–10 epoch），以观察长期训练对 OOD 泛化的影响。

对于 ScienceWorld 的 subsample：每个 task 随机采样 5 个 variation 以加速评估。

#### 3.1.5 经验库与检索配置

- **轨迹编码器 $\phi$**：`Qwen/Qwen3-Embedding-0.6B`（固定，不参与训练）
- **嵌入计算库**：Sentence Transformers
- **相似度**：点积（dot product）
- **Index 构成**：默认使用对应 split 的 train 集构建（含成功和失败轨迹）
- **默认 K**：$K = 2$（在 ExpRAG-LoRA 实验中），Inference-only 实验扫描 $K \in \{1, 2, 4\}$
- **默认检索模式**：static（ExpRAG-LoRA）
- **轨迹格式**：JSON 存储

### 3.2 Baseline 对比（ALFWorld）

论文报告了两组 baseline **①** training-free memory-augmented 方法和 **②** supervised fine-tuned 方法。所有结果均在 ALFWorld 的 **标准 test split**（非 OOD split）上测量。

#### Training-free 方法

这些方法不进行任何参数更新，仅通过 prompting 或 memory 机制提升 zero-shot 性能：

| 方法 | 成功率 | 方法说明 |
| --- | --- | --- |
| Zero-shot | 29.9 | 仅给出任务描述和动作模板，无 few-shot 示例 |
| ReAct | 17.1 | 标准的 Reasoning + Acting prompt（交替生成 thought 和 action） |
| ITPI | 35.7 | In-context Trajectory-augmented Policy Iteration |
| Mem0 | 33.6 | Memory-augmented agent |
| A-MEM | 34.7 | Adaptive Memory |
| AgeMem-noRL | 37.9 | Agentic Memory（无 RL 版本） |
| Memory Bank | 40.3 | 固定记忆库检索 |
| Reflexion | 42.7 | Self-reflection：失败后反思并重试 |
| **ExpRAG（本文 frozen）** | **83.6** | 简单的 episodic retrieval，固定 index，$K=4$, static |

!!! tip "关键观察"

    ExpRAG（83.6）以 **近一倍的差距** 超过 Reflexion（42.7）——后者曾是 training-free setting 下最强的 memory-augmented 方法。这说明 **简单的整轨迹检索比复杂的 self-reflection + memory update 机制更有效**，至少在此类文本环境中。

#### Supervised Fine-tuned 方法

这些方法使用 expert trajectories 进行某种形式的训练：

| 方法 | 成功率 | 训练方式说明 |
| --- | --- | --- |
| Prompting Zero-shot | 29.9 | 无训练 baseline |
| ReAct | 17.1 | 无训练 baseline |
| NAT + ReAct | 66.4 | Native Action Tokenization + ReAct |
| IWM | 70.3 | Implicit World Model |
| Self-Reflection | 71.1 | 在训练中融入 self-reflection |
| ETO + ReAct | 79.9 | Environment Trajectory Optimization + ReAct |
| SFT + ReAct | 80.7 | 标准 SFT，使用 ReAct-format 轨迹 |
| SAND | 85.0 | Situated Agent for Novel Domains |
| ITPR | 85.1 | In-context Trajectory-augmented Policy Refinement |
| Rule-based Expert | 89.6 | 环境内置的规则式专家策略（上界参考） |
| **LoRA baseline（本文）** | **94.1** | 标准 LoRA SFT，无需 ReAct 格式，使用 chat-template 轨迹 |

!!! warning "Benchmark 饱和现象"

    本文的 LoRA baseline（94.1）甚至超过了 rule-based expert（89.6）。expert policy 是环境提供的脚本，不会犯错但受限于预定义的规则；LoRA-SFT 模型学到了比 expert 更优的策略（可能利用了 expert 没有的常识推理能力）。这一结果说明标准的 ALFWorld benchmark **近乎饱和**，不再能有效区分不同训练方法的好坏——因此本文转向 OOD split 作为更严格的评估标准。

### 3.3 Inference-only ExpRAG 消融实验

本节系统研究 ExpRAG 在 **frozen 模型**（不训练）下的各设计选择。实验模型为 Ministral 3-8B。

#### 3.3.1 Top-K 与检索模式

| 配置 | ALFWorld（All Tasks） | ScienceWorld（All Tasks） |
| --- | --- | --- |
| No RAG | 4.48 | 10.40 |
| Static, $K=1$ | 39.30 | 26.62 |
| Static, $K=2$ | 50.99 | 34.67 |
| Static, $K=4$ | **64.18** | 33.56 |
| Dynamic, $K=4$ | 63.81 | **35.24** |

**逐项分析**：

- **$K$ 的影响**：
  - ALFWorld 上成功率随 $K$ 单调递增：$1 \to 2 \to 4$ 分别带来 $+34.8 \to +11.7 \to +13.2$ 个百分点的增益
  - ScienceWorld 上 $K=2$ 基本饱和（34.67 vs. 33.56），更大的 $K$ 不再带来显著提升
  - 解释：ALFWorld 任务之间的结构差异较大，需要更多样化的参考轨迹；ScienceWorld 任务相似度更高，少数几条轨迹就能覆盖有用信息

- **Static vs. Dynamic**：
  - 在 index 匹配（all-index）时，两种模式差异很小（ALFWorld: 64.18 vs. 63.81；ScienceWorld: 33.56 vs. 35.24）
  - Dynamic 的优势有限，因为每次重检索带来的相关性提升，被 context churn（已有动作与新的 memory block 不一致）部分抵消

#### 3.3.2 Index 构成的影响

研究者构建了三种 index 变体：
- **Index = all**：使用对应 split 的全部 train 轨迹
- **Index = easy**：仅使用 easy split 的训练轨迹
- **Index = hard**：仅使用 hard split 的训练轨迹

然后测试在 easy/hard test set 上的交叉表现。

| 测试 split → \ 使用的 index ↓ | ALFWorld easy | ALFWorld hard | ScienceWorld easy | ScienceWorld hard |
| --- | --- | --- | --- | --- |
| No RAG | 4.5 | 4.5 | — | — |
| Index = all | **52.1** | 75.4 | **23.0** | 34.0 |
| Index = easy（匹配） | **52.1** | 62.3 | **23.0** | 30.5 |
| Index = hard（匹配） | 46.6 | **82.0** | 16.9 | **36.2** |

!!! tip "Cross-split transfer 现象"

    即使 index 与测试任务不匹配，检索仍有显著的正面效果。例如用 easy index 测试 ALFWorld hard 任务，成功率为 62.3（对比 no RAG 的 4.5）。这是因为：
    1. 不同 task-type 之间有共享的子任务（如「拿起物体」「移动到位置」）
    2. 即使任务不同，轨迹中的动作格式和交互模式仍是可迁移的
    3. 检索到的轨迹提供了合法的动作格式示范

!!! warning "不对称性"

    ALFWorld 上 hard index → easy test 仅为 46.6（远低于 easy index → hard test 的 62.3）。可能原因是 hard 任务的轨迹更长、包含更多失败尝试，在检索给 easy 任务时反而引入噪声。ScienceWorld 上也观察到类似但方向相反的不对称。

#### 3.3.3 Cross-model 扩展

将 inference-only ExpRAG 应用于不同 backbone 模型，测试检索增益是否取决于模型的内在能力：

- **Qwen 2.5-7B**：no RAG 时已较强，但 ExpRAG 仍带来额外增益，说明即使强模型也能从经验检索中受益
- **Gemma 3-4B**：no RAG 时极弱，ExpRAG 提升幅度最大（相对提升倍数最高），但绝对性能仍低于大模型
- **Qwen 2.5-7B-1M**：长上下文模型能更好地利用大 $K$ 值（$K=4$ 时仍无饱和迹象）

### 3.4 ExpRAG-LoRA：检索增强微调

#### 3.4.1 OOD 泛化动态学（Delayed Generalization）

论文发现了一个与常规认知相悖的现象：**在 agent fine-tuning 中，OOD 性能的提升与 validation loss 的走势可能脱节**。

具体观察：
- 训练的前几个 epoch：validation loss 下降，OOD 性能同步提升（正常行为）
- 10 epoch 以后：validation loss 开始上升（过拟合信号），但 OOD 性能 **继续提升**，在 30–50 epoch 达到峰值
- 最佳 OOD checkpoint 往往出现在远超常规 early-stopping 点的位置

作者将这一现象称为 **"delayed downstream generalization in agent fine-tuning"**（agent 微调中的延迟下游泛化），认为可能与 grokking 文献中的现象有关。

!!! warning "实践启示"

    这意味着在 agent SFT 中，**不能仅凭 validation loss 做 early stopping**——需要通过实际的 task success rate（尤其在 OOD split 上）来选择 checkpoint。这在计算上更昂贵（需要 rollout 评估），但对 OOD 泛化至关重要。

#### 3.4.2 ALFWorld 主结果

以下为在 ALFWorld easy→hard OOD split 上的四组方法对比。每个模型报告 easy/hard 两个数字：

| 方法 | Ministral 3-8B | Gemma 3-4B | Qwen 2.5-7B | Qwen 2.5-7B-1M |
| --- | --- | --- | --- | --- |
| **ExpRAG**（no training） | 54.8 / 47.5 | 20.6 / 4.9 | 81.6 / 81.9 | 67.1 / 54.1 |
| **LoRA**（no ExpRAG） | 98.6 / 34.4 | 61.6 / 1.6 | 86.3 / 21.3 | 98.6 / 23.0 |
| **LoRA + ExpRAG** | 97.3 / 67.2 | 57.5 / 3.3 | 89.0 / 70.5 | 82.2 / 68.9 |
| **ExpRAG-LoRA** | **97.3** / **88.5** | **86.3** / **73.8** | 84.9 / **90.2** | **97.3** / **91.8** |

**逐列解读**：

- **Ministral 3-8B**（主力实验模型）：
  - 纯 LoRA 在 easy 上达到 98.6（几乎完美），但 hard 上仅 34.4——典型的 OOD 崩溃
  - LoRA + ExpRAG 在 hard 上提升到 67.2（检索的单独增益为 $+32.8$）
  - ExpRAG-LoRA 在 hard 上达到 88.5（检索增强训练的额外增益为 $+21.3$），同时 easy 保持 97.3

- **Gemma 3-4B**（最弱模型）：
  - Frozen ExpRAG 几乎无效（hard: 4.9），纯 LoRA 在 hard 上完全崩溃（1.6）
  - LoRA + ExpRAG 同样效果不佳（3.3）——说明如果模型基础能力不足以理解检索到的轨迹，推理时加入检索也没有帮助
  - ExpRAG-LoRA 将 hard 拉升至 73.8，easy 至 86.3——**训练时接触检索数据使弱模型学会了如何利用这些额外信息**

- **Qwen 2.5-7B**（强 in-context learner）：
  - Frozen ExpRAG 已在 hard 上达到 81.9——该模型的 in-context learning 能力极强
  - 纯 LoRA 在 hard 上反而下降（21.3）——微调破坏了模型的 in-context 泛化能力
  - ExpRAG-LoRA 恢复至 90.2——检索增强训练既保留了检索能力，又通过参数更新优化了决策

- **Qwen 2.5-7B-1M**（长上下文模型）：
  - 与 Ministral 表现类似，但得益于长上下文支持，可能从更大的 $K$ 中受益

#### 3.4.3 ScienceWorld 主结果

ScienceWorld hard（OOD）结果，四模型两方法对比：

| 模型 | LoRA（无检索） | ExpRAG-LoRA |
| --- | --- | --- |
| Ministral 3-8B | 15.6 | **42.2** |
| Gemma 3-4B | 6.3 | 4.7（例外） |
| Qwen 2.5-7B | 7.8 | **29.7** |
| Qwen 2.5-7B-1M | 12.5 | **29.7** |

ScienceWorld 上 ExpRAG-LoRA 的优势同样显著（除 Gemma 4B 外），但绝对数值远低于 ALFWorld——ScienceWorld 的任务更复杂、交互步数更多、子任务多样性更大，经验检索的覆盖难度更高。

Gemma 3-4B 在 ScienceWorld 上 ExpRAG-LoRA 反而略低于纯 LoRA（4.7 vs. 6.3），说明当模型容量不足以同时处理任务推理和检索信息利用时，检索增强训练可能引入额外的学习负担。

#### 3.4.4 实验结论汇总

1. **ExpRAG-LoRA 在 OOD 泛化上最强**：在所有模型和几乎所有设置中，ExpRAG-LoRA 在 OOD hard split 上取得最高成功率
2. **LoRA + 推理时检索 优于纯 LoRA**：即使训练时未接触检索数据，推理时加入 ExpRAG 也能提升 OOD 性能（但不如 ExpRAG-LoRA）
3. **纯 LoRA 的 OOD 崩溃**：标准 SFT 在 easy 上近乎完美但 hard 上严重退化，说明纯参数更新无法解决 distribution shift
4. **检索增益具有模型依赖性**：强 in-context learner（Qwen 7B）frozen 时即可从检索中大量受益；弱模型（Gemma 4B）需要通过 ExpRAG-LoRA 训练才能有效利用检索

### 3.5 鲁棒性测试

论文设计了两种压力测试，评估 ExpRAG-LoRA 在检索条件不理想时的表现。

#### 3.5.1 测试设置

- **空 Index（Empty Index）**：检索阶段不返回任何轨迹，$m_t$ 为空或仅含占位符文本。模拟「缺乏相关经验」的最坏情况。
- **不匹配 Index（Mismatched Index）**：在 hard 任务上测试时，使用 easy 任务的 index（而非 hard index）。模拟「仅有过往简单任务经验，需要泛化到复杂新任务」的实际场景。

#### 3.5.2 Ministral 3-8B 结果（ALFWorld Hard）

| 测试条件 | 成功率 | 相对 matched index 的降幅 |
| --- | --- | --- |
| Matched index（hard index） | 88.5 | — |
| Mismatched index（easy index） | 39.3 | −49.2 |
| Empty index | 29.5 | −59.0 |

**分析**：
- **Empty index** 时退化最严重（从 88.5 降至 29.5）。这是因为 ExpRAG-LoRA 在训练时始终有 memory block 作为输入的一部分，当推理时完全失去这一信号，输入分布发生了最大的偏移。
- **Mismatched index** 降至 39.3，但仍高于纯 LoRA 的 34.4（见 3.4.2 表）。即使检索到的轨迹来自不同任务类型，input context 的格式（有 memory block + 对话历史）仍与训练分布相近，模型仍能部分利用这些信息。
- Mismatched ExpRAG-LoRA（39.3）仍然是 hard OOD 上最强的单一方法（对比 LoRA + ExpRAG 的 67.2 虽然更高，但那使用了 matched index）。

#### 3.5.3 Qwen 2.5-7B-1M 结果（ALFWorld Hard）

| 测试条件 | 成功率 |
| --- | --- |
| Matched index | **91.8** |
| Mismatched index | **60.7** |
| Empty index | 36.1 |

Qwen-1M 在不匹配 index 下保持了最强的鲁棒性（60.7），可能得益于其长上下文能力使其在训练时学会了更灵活地利用不同质量的检索结果。

#### 3.5.4 ScienceWorld 鲁棒性

ScienceWorld 上所有方法在 empty/mismatched index 下均大幅下降，且 mismatched 相对 empty 的恢复幅度很小。原因在于 ScienceWorld 的 task-type 之间行为模式差异更大（化学混合 vs. 遗传学 vs. 导电测试），easy 轨迹对 hard 任务的可迁移信息有限。

---

## 4 评价（忠实原文）

### 4.1 论文自身主张的贡献

1. 建立了强的 LoRA SFT 和 ExpRAG retrieval baseline，超过多种 SOTA agent training pipeline
2. 系统分析了经验检索的设计选择：$K$ 值、static vs. dynamic、index 构成、backbone 的影响
3. 提出 ExpRAG-LoRA，将检索融入训练，显著提升 unseen task 泛化
4. 发现 prolonged training 有助于 OOD 泛化（类似 grokking 的 delayed generalization）

### 4.2 论文自身承认的局限性

1. 检索 index 由 scripted expert trajectories 构建，可能不反映 LLM 自身的错误模式 — 用 LLM-generated rollouts 构建 index 的效果未知
2. 性能依赖轨迹可用性 — 缺少任务相关轨迹时泛化急剧下降
3. 使用固定的只读 episodic memory — 探索 read-write memory（总结、抽象、选择性保留）可能有助于扩展性和长周期适应

### 4.3 本文方法在论文自身的定位

作者将 ExpRAG 定位为一种简单而高效的 baseline：不追求复杂的 self-evolving memory 或 RL-based agent training，而是用最直接的 episodic retrieval + LoRA SFT 组合，达到甚至超过更复杂方法的 OOD 泛化能力。强调社区应该将 retrieval-augmented baseline 作为标准对比。

---

## 5 我的思考

### 5.1 与相关工作的对比

- vs. **Reflexion / A-MEM**：后者使用 self-reflection 或 adaptive memory，需要额外推理和更新。ExpRAG 用简单的固定索引 + 检索，效果反而更好（83.6 vs. 42.7），提示简单 baseline 被低估
- vs. **ETO / SAND / ITPR**：这些 SFT 方法引入了更复杂的训练目标（如 multi-turn reward modeling）。本文的 LoRA baseline 仅用标准 next-token prediction 就达到 94.1%，说明 ALFWorld 这类 benchmark 的挑战可能不在训练方法，而在 OOD 泛化
- vs. **classical RAG**：将 semantic memory（文档）替换为 episodic memory（轨迹），是自然的扩展。关键差异在于 episodic memory 的检索/利用方式需要更多设计选择

### 5.2 值得关注的点

- **Delayed OOD generalization** 是反直觉的：validation loss 上升但 OOD 性能继续提升。这提示在 agent fine-tuning 中不应仅依赖 validation loss 做 early stopping，需要考虑任务成功率
- **Qwen 2.5-7B 在 no-training ExpRAG 上已经很强**（ALFWorld 81.6/81.9），说明基础模型的 in-context learning 能力对检索增强效果影响很大 — 弱模型（如 Gemma 3-4B，20.6）需要训练才能有效利用检索
- **Experience 的定义**是本文的一个 hidden variable：使用 scripted expert trajectories 意味着 index 中的经验是"干净且最优的"。如果 index 中的轨迹来自实际 LLM rollout（含错误和次优行为），效果如何？这是关键的实际部署问题

### 5.3 实用性评估

- 对于需要快速适配新任务的 agent 系统，ExpRAG-LoRA 提供了一条可行的路径：先用已有轨迹构建 index，微调时注入检索，推理时继续检索
- 但 index 构建依赖 expert trajectories 这一前提限制了其在实际场景中的直接应用 — 实际场景中 expert trajectories 往往不可得
- $K=2$ 的发现很实用：在效果和延迟之间取到好的平衡点，且 static retrieval 足够可靠，避免了 dynamic retrieval 的 context churn 问题
