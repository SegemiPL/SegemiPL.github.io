---
date: 2026-05-28
icon: lucide/brain-circuit
description: 循环神经网络的核心思想：循环使得信息可以从当前步传递到下一步，可看作同一个神经网络的多次复制
---
<script>
  window.MathJax = {
    tex: {
      inlineMath: [["$", "$"], ["\\(", "\\)"]],
      displayMath: [["$$", "$$"], ["\\[", "\\]"]],
      processEscapes: true,
      processEnvironments: true,
      tags: "none"
    },
    options: {
      ignoreHtmlClass: "no-mathjax",
      processHtmlClass: "arithmatex"
    },
    svg: { fontCache: "global" }
  };
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<script>
  (function () {
    function typeset() {
      if (window.MathJax && window.MathJax.typesetPromise) {
        window.MathJax.typesetPromise();
      }
    }
    if (typeof document$ !== "undefined" && document$.subscribe) {
      document$.subscribe(typeset);
    } else if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", typeset);
    } else {
      typeset();
    }
  })();
</script>

# LLM

# 零、回顾：神经序列模型（RNN / LSTM）

## RNN

循环神经网络的核心思想：循环使得信息可以从当前步传递到下一步，可看作同一个神经网络的多次复制。

- 短距离依赖：如「云飘在 **天上**」
- **长距离依赖**：如「我在法国长大 ...... 我能讲一口流利的 **法语**」→ 标准 RNN 难以处理 → 引出 LSTM

## LSTM（Long Short-Term Memory）

将长期和短期的信息都考虑进来，设计了**门（gate）**来避免梯度消失。三个要点：

- 什么应该被忘记？
- 什么应该被记住？
- 基于当前状态和输入，输出应该是什么？

### LSTM 的三部分结构

**第一部分：忘记门（Forget Gate）**

Sigmoid 层输出 0 到 1 之间的数值，描述每个部分有多少量可以通过。0 代表「不许任何量通过」，1 代表「允许任意量通过」。

**第二部分：输入门（Input Gate）— 什么应该被记住**

- Sigmoid 层（输入门层）决定将要更新什么值
- Tanh 层创建一个新的候选值向量
- 更新旧神经元状态：$C_{t-1} \to C_t$

**第三部分：输出门（Output Gate）— 计算输出**

- Sigmoid 层确定神经元状态的哪个部分将被输出
- 神经元状态通过 tanh 处理（得到 -1 到 1 之间的值），与 sigmoid 门的输出相乘

!!! warning "LSTM 缺点"

    参数太多，可能导致过拟合。

---

# 一、什么是语言模型

语言模型（Language Model）的核心任务：**预测一个句子在语言中出现的概率**。

语言模型近年发展历程：

$$
\text{统计语言模型} \to \text{神经语言模型} \to \text{预训练语言模型} \to \text{大语言模型}
$$

| 阶段 | 代表 | 特点 |
| --- | --- | --- |
| 统计语言模型（SLM） | N-gram | 基于马尔科夫假设，当前词概率仅与前 $n-1$ 个词有关 |
| 神经语言模型（NLM） | NNLM, word2vec | 词映射到向量，神经网络预测 |
| 预训练语言模型（PLM） | Transformer, BERT, T5 | 上下文相关的词向量，大规模预训练 |
| 大语言模型（LLM） | GPT, Claude, DeepSeek, Qwen, 豆包... | 超大参数量，涌现能力 |

---

# 二、统计语言模型

**N-gram LM**：基于马尔科夫假设，当前词概率仅与前 $n-1$ 个词有关。

$$
p(w_i \mid w_1, \ldots, w_{i-1}) \approx p(w_i \mid w_{i-n+1}, \ldots, w_{i-1})
$$

!!! tip "回顾"

    详见课程「马尔科夫模型」一节。

---

# 三、神经语言模型

## 3.1 基本思想

单词映射到词向量，再由神经网络预测当前时刻词。衍生出**词汇表示学习（representation learning）**，生成**词向量（word embedding）**。

## 3.2 word2vec

- **One-hot 词表示**（稀疏向量）：e.g. $(0, 0, 0, \ldots, 0, 1, 0, 0)$
- **分布式语义表示**：从 one-hot 表示到 embedding 表示（稠密向量），增强了语义表示能力，克服数据稀疏性问题

核心思想：「You shall know a word by the company it keeps.」— John Rupert Firth

!!! abstract "分布式语义"

    通过词的上下文（周围的词）来学习词的向量表示。语义相近的词，其词向量在空间中距离也相近。

### 静态表示的局限

- 上下文无关的词向量表示无法处理**一词多义**的问题
- 例如：
  - I go to the **bank** for money deposit.（银行）
  - I go to the **bank** for fishing.（河岸）

!!! warning "问题"

    静态 word2vec 为每个词只分配一个固定向量，没有语境信息，无法区分多义词。

---

# 四、预训练语言模型

## 4.1 背景：自监督学习

- 能否不使用标注数据来获取知识？
- **自监督学习**：挖掘数据内部信息作为监督信号
  - 对比学习是一种代表性自监督学习方法
  - 正例：同一张图片的不同处理结果（随机裁剪、颜色失真等）
  - 负例：其他图片

## 4.2 上下文相关的词向量 — 预训练

- 让模型具备较好的文本理解能力，该能力可以很好地迁移到下游任务
- 最早的工作使用 RNN，在大规模文本上进行语言模型的预训练（如 ELMo、ULMFiT）

## 4.3 Transformer 架构

Transformer 模型架构（「Attention Is All You Need」, NIPS 2017）：

- **编码器（左）**：将输入变换为隐藏层特征
- **解码器（右）**：将隐藏层特征变换为自然语言序列
- 核心组件：多头注意力、前馈网络、残差连接与层归一化

### 编码器-解码器结构

- 编码器、解码器均为六层首位相连堆砌而成
- 结构完全相同，但**不共享参数**
- 每个位置的词仅流过自己的编码器路径
- 在 Self-Attention 层中，路径两两之间相互依赖；前向网络层则没有依赖性，可**并行执行**

### 自注意力（Self-Attention）

注意力可以近似为一种**基于相似度的查表**操作。

**Scaled Dot-Product Attention 计算**：

$$
\text{Attention}(Q, K, V) = \text{softmax}\!\left(\frac{QK^T}{\sqrt{d_k}}\right) V
$$

其中 $d_k$ 是隐藏层的维度。

!!! tip "为什么除以 $\sqrt{d_k}$？"

    当维度很高时，点积部分数值过大，使得 softmax 进入梯度过小的区域。除以 $\sqrt{d_k}$（对隐层维度做平方根规范化）缓解该问题。

### 多头注意力（Multi-Head Attention）

每一组都是随机初始化，经过训练后输入向量可被映射到不同的**子表示空间**中。

- 将多个注意力头的输出拼接（concat）后乘以一个权重矩阵 $W^O$

$$
\text{MultiHead}(Q, K, V) = \text{Concat}(\text{head}_1, \ldots, \text{head}_h) W^O
$$

其中 $\text{head}_i = \text{Attention}(QW_i^Q, KW_i^K, VW_i^V)$。

### 自注意力的含义

- 编码器、解码器中：$Q$、$K$、$V$ 相同，都是自身前一层的输出
- 交叉注意力（编-解码器注意力）：$Q$ 来自前一层输出，$K$、$V$ 来自编码器输出

### 位置编码（Positional Encoding）

自注意力机制中并未考虑输入的位置信息，需要在输入词向量中提前加入位置信息。

$$
\begin{aligned}
PE(i, 2j) &= \sin\left(\frac{i}{10000^{2j/d}}\right) \\
PE(i, 2j+1) &= \cos\left(\frac{i}{10000^{2j/d}}\right)
\end{aligned}
$$

其中 $i$ 是位置，$2j, 2j+1$ 是维度序号。

### 残差连接与层归一化

- **残差连接（Add）**：将输入与输出相加，缓解梯度爆炸和消失
- **层归一化（Norm）**：对数据进行重新放缩，提升训练的稳定性

### 解码器输出 → 词

1. **线性层**：全连接，将解码器的最后输出映射到 logits 向量（若模型有 1 万个单词，则 logit 向量有 1 万维）
2. **Softmax 层**：把分数转化为概率值，最高值对应的维度就是该步输出的单词

## 4.4 预训练架构总结

配备预训练任务进行自监督学习，大规模学习文本中语言知识。**通用任务解决器**，初步体现出泛化能力。

!!! abstract "关键意义"

    Transformer 架构使得并行训练深层次架构的神经网络成为可能，**奠定了大模型的根基**。

---

# 五、大语言模型（LLM）

## 5.1 为什么叫「大」模型？

LLM 时代，隐层的维度较大（hidden layers）。

Transformer 参数量可近似计算为：

$$
\text{Params} \approx 12lh^2 + Vh
$$

- $l$：层数，$h$：隐层维度，$V$：词汇表大小
- 自注意力有 $Q$、$K$、$V$ 的权重矩阵及输出层，每个是 $h \times h$，一共 $4h^2$
- 前馈网络通常两层：$h \to 4h$ 和 $4h \to h$，参数 $h \times 4h + 4h \times h = 8h^2$
- 嵌入层参数 $Vh$

**参数量对比**：

| 模型 | 隐层维度 |
| --- | --- |
| BERT | 768 |
| LLaMA-7B | 4096 |
| LLaMA-13B | 5120（50 层） |
| LLaMA-70B | 8192 |

## 5.2 大模型规模一览

| 模型 | 发布时间 | 参数量 | 训练数据 | 训练 GPU 量 |
| --- | --- | --- | --- | --- |
| GPT-1 | 2018.06 | 1.17 亿 | ~5GB | 8（P100） |
| GPT-2 | 2019.02 | 15 亿 | 40GB | 256（V100） |
| GPT-3 | 2020.05 | 1750 亿 | 570GB | 10,000（A100） |
| GLM-130B | 2022.08 | 1300 亿 | 400GB | 1,024（A100） |
| LLaMA-7B | 2023.02 | 70 亿 | 1T tokens | 2,048（A100） |
| GPT-4 | 2023.03 | ~1.8 万亿(总) / 2800 亿(激活) | 13T tokens | ~25,000（A100/H100） |
| Qwen-72B | 2023.08 | 720 亿 | 3T tokens | 4,096（A100） |
| 豆包（Doubao） | 2024.03 | 1280 亿 | 2.5T tokens | 8,192（A100） |
| DeepSeek-V3 | 2024.07 | 6710 亿(总) / 370 亿(激活) | 8T tokens | 12,000（A100/H100） |

!!! tip "直观感受"

    如果 1 秒能数 10 个数，那么数完 1750 亿大约需要 **550 年**。

## 5.3 涌现现象（Emergence）

!!! abstract "涌现（Emergent Abilities）"

    小模型中没有、只出现在大模型中的能力。

- 大参数量 + 大计算量（FLOPs）→ 模型突然展现出此前不存在的任务能力
- 某些能力在模型规模达到某个临界点之前几乎不存在，超过临界点后性能急剧提升

**为什么出现涌现？** — 尚未解决的疑问，当前猜想：

1. 很多任务需要更强的模型能力（参数越多意味着更强的拟合能力，如多跳推理）
2. 度量指标不够平滑，导致涌现实际上是能力差距的「假」反应
3. 知识表示的密集程度需要达到一定程度才可以

## 5.4 顿悟现象（Grokking）

!!! abstract "顿悟（Grokking, OpenAI 2022）"

    模型在训练初期表现不佳，但随着训练数据的增加和训练时间的延长，模型在某个时刻**突然展现出**对任务规律的理解和泛化能力。

- 与涌现不同：涌现关注模型**规模**带来的能力跃迁，顿悟关注**训练时长/数据量**带来的能力跃迁

## 5.5 大语言模型处理的基本流程

大语言模型的处理遵循以下基本流程（下节课继续）。

---

# 总结

| 阶段 | 关键技术 | 核心贡献 |
| --- | --- | --- |
| 统计语言模型 | N-gram | 马尔科夫假设，简单有效 |
| 神经语言模型 | word2vec | 分布式语义表示，克服稀疏性 |
| 预训练语言模型 | Transformer | 并行训练、自注意力、上下文相关表示 |
| 大语言模型 | Scaling | 涌现能力、通用任务解决 |
