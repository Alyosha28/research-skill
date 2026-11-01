# research

**把研究问题变成可检验的实验、可追溯的证据和可恢复的研究状态。**

<p align="center">
  <img src="assets/research-whale-deepseek-compact.gif" alt="采用 DeepSeek 图标轮廓的 Q 版鲸鱼，缩小并居中放置，戴博士帽用放大镜检查文档" width="720">
</p>

`research` 是一项通用 Agent Skill。它用 Propose–Probe–Compose 组织模型推理与宿主执行器提供的真实执行，帮助 Agent 设计公平对照、保留失败证据、选择研究路线，并在预算中断后继续工作。

[快速开始](#快速开始) · [核心方法](#核心方法) · [使用示例](#使用示例) · [结构化契约](#结构化契约) · [设计文档](skill_design.md) · [许可证](LICENSE)

## 为什么使用 research

研究生成更多候选、写出更长报告或得到更高单次分数，都不足以回答研究系统是否真正改进。`research` 将执行证据置于研究循环中心：

- **公平比较**：不同覆盖范围的任务先在共同可评估样本上对齐，再计算配对差值。
- **真实反馈**：提案经过有界 Probe 后才进入采纳决策，失败与空结果保留原状态。
- **连续研究**：活动方案、参照方案、经验记忆和路线历史分别维护。
- **可恢复执行**：协议身份、真实用量和恢复现场一起保存，避免重复模型调用。
- **克制结论**：开发证据、选择证据、确认证据与独立样本外证据分别命名。

## 核心方法

```mermaid
flowchart LR
    A[Scope<br/>问题与授权] --> B[Propose<br/>可检验提案]
    B --> C[Probe<br/>匹配真实试验]
    C --> D[Compose<br/>证据驱动决策]
    D --> E[Route<br/>研究路线]
    E --> B
    E --> F[Deliver<br/>结果与恢复入口]
```

### 区分两个研究层次

**Candidate search** 关注具体候选，例如表达式、程序、模型或配置。它回答“哪个候选表现更好”。

**Research-harness evolution** 关注产生候选的执行系统，例如提案策略、记忆、诊断、搜索算子和预算分配。它回答“哪种研究方式能够持续产生更好的结果”。

每次运行先声明研究层次，再选择对应的实验单位、参照方案和主要指标。

### Propose–Probe–Compose

**Propose**：每项提案携带假设、最小编辑、预期机制、适用范围、否证条件、模型身份与真实用量。自由文本想法经过结构校验后才进入执行。

**Probe**：各条件共享任务、输入、数据角色、种子、预算、评价器和共同支持。选择与诊断使用有界真实执行。

**Compose**：主要指标与行为约束共同决定 `kept`、`revised`、`dropped` 或 `inconclusive`。组合编辑重新评价，避免从单项表现推断组合效果。

### 五类研究路线

- `EXPLOIT`：在当前协议内利用已有机制。
- `REPAIR`：修复已定位缺陷，使用相同口径复核。
- `FORK`：保留当前状态，为不同机制路径建立分支。
- `REFRAME`：重设研究问题，以新协议和新运行承接。
- `STOP`：问题已回答、预算耗尽或继续执行缺乏信息价值时停止。

## 快速开始

### 安装到 Claude Code

```bash
git clone https://github.com/Alyosha28/research-skill.git ~/.claude/skills/research
```

其他支持 Agent Skills 的宿主可以直接安装仓库根目录。无需构建，也无需安装运行时依赖。仓库提供技能规则、状态契约与通用检查器，实验执行由宿主研究执行器完成。

### 启动研究

显式调用 `/research`，或直接描述研究任务：

```text
两个实验臂的任务覆盖不同。请设计一个使用共同可评估样本、共享预算和固定主要指标的配对实验。
```

技能会自动加载当前分支需要的规则。`SKILL.md` 保持精简，详细契约位于 `references/`。

## 使用示例

### 公平比较两个条件

```text
我们正在比较增加结构化记忆与固定基线。两个条件的覆盖任务不同，团队还想在看到结果后改选指标。请给出可证伪的小实验。
```

技能会确定共同支持、共享预算、配对实验单位、主要指标、否证条件和失败处理方式。

### 评价研究执行系统

```text
研究代理这周生成了更多候选。这个证据能说明 research harness 已经改进吗？需要哪些对照？
```

技能会区分候选产出与执行系统证据，要求匹配基线、共同样本、预算控制和范围准确的判定。

### 处理部分失败

```text
十二项任务中有三项超时。请定位原因，保留失败状态，并设计能够区分基础设施故障与研究假设未获支持的检查。
```

技能会保留原始运行、比较成功与失败轨迹，并给出最小诊断路径。

### 恢复中断的研究

```text
proposal.json 和 model_usage.json 已保存，执行器随后在候选运行前超时。请恢复执行，保留累计预算并避免重复模型调用。
```

技能会要求宿主执行器复用已保存提案、继承真实用量、保持原协议身份，并从恢复现场继续执行。

## 证据与执行契约

### 可追溯主张

每项定量主张记录对象、指标、数值、单位、分母、比较方向、总体或窗口和统计单位。主张状态使用 `supported`、`contradicted`、`inconclusive` 和 `unverified`。

### 共同支持

跨候选比较先确定共同可评估实验单位，再计算指标与差值。缺失、超时、无效提案和不可评价项不会被静默补零或删除。

### 真实研究记忆

经验条目包含来源、适用范围和实际使用位置。只有进入后续提案并留下使用证据的内容才构成研究记忆。选择阶段结果与敏感字段不会直接进入提案上下文。

### 预算与恢复

调用前检查剩余额度，调用后记录真实用量。恢复时保留协议、输入、评价器、累计成本与失败记录；新协议通过新运行承接。

## 结构化契约

仓库附带两个仅使用 Python 标准库的检查器。

核对主张记录、本地来源、JSON Pointer 与定量值：

```bash
python3 scripts/check_research_record.py assets/research_record.example.json --root assets
```

核对执行中研究状态、提案、预算、路线和恢复身份：

```bash
python3 scripts/check_research_state.py assets/research_state.example.json
```

示例位于 [`assets/research_record.example.json`](assets/research_record.example.json) 与 [`assets/research_state.example.json`](assets/research_state.example.json)。

检查器验证结构契约。领域计算由宿主研究执行器完成，来源内容和主张语义仍需实际审阅。

## 验证

运行回归测试与示例检查：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_research_record.py assets/research_record.example.json --root assets
python3 scripts/check_research_state.py assets/research_state.example.json
```

安装 [`skill-up`](https://github.com/alibaba/skill-up) 后验证并运行行为与触发评测：

```bash
skill-up validate evals/eval.yaml
skill-up run evals/eval.yaml
```

当前套件包含 28 项回归测试和 10 个行为与触发用例，覆盖证据边界、共同支持、失败诊断、研究层次、路线、记忆、预算恢复、Compose 与相邻误触发。

评测使用本机 Claude Code 登录状态，采用串行 `none` 环境；引擎由 `skill-up` 以 `bypassPermissions` 启动。运行前确认本机工作区权限符合预期。产物写入仓库旁的 `<仓库目录名>-workspace/`。

## 仓库导航

- [`SKILL.md`](SKILL.md)：触发后的执行步骤与完成条件。
- [`skill_design.md`](skill_design.md)：完整方法、状态模型、执行契约与技能进化设计。
- [`references/evidence.md`](references/evidence.md)：来源、主张和证据状态。
- [`references/experiments.md`](references/experiments.md)：对照、共同支持、统计与失败诊断。
- [`references/research-loop.md`](references/research-loop.md)：两个研究层次、Propose–Probe–Compose、路线与记忆。
- [`references/execution.md`](references/execution.md)：宿主接口、信息隔离、预算与恢复。
- [`references/communication.md`](references/communication.md)：研究写作、图表与交付检查。
- [`scripts/draw_research_whale.py`](scripts/draw_research_whale.py)：重新生成 README 动画，需要 Pillow。
- [`evals/`](evals/)：可复现的行为与触发评测。

## 参与改进

提交 Issue 时提供研究场景、期望行为、实际输出和可公开的复现材料。修改技能时同步更新相关契约与评测，并运行本文验证命令。

请勿在 Issue、评测或示例中上传私有数据、凭据和封闭研究材料。

## 许可证

[MIT](LICENSE)
