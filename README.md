# research

`research` 是一项通用 Agent Skill，用于把研究问题转化为来源可核查的主张、可证伪的实验和范围准确的交付物。技能覆盖证据审查、共同样本比较、失败诊断、研究写作、图表检查和最小复现记录。

## 安装

将仓库克隆到 Claude Code 的个人技能目录：

```bash
git clone https://github.com/Alyosha28/research-skill.git ~/.claude/skills/research
```

其他支持 Agent Skills 的宿主可以将仓库根目录作为一项技能安装。仓库根目录直接包含 `SKILL.md`，无需额外构建。

## 使用

显式调用 `/research`，或提出以下类型的请求：

- 将观察到的现象转化为可证伪的研究问题；
- 审查报告中的数字、引用和结论边界；
- 设计共享预算、数据和随机种子的对照实验；
- 诊断失败运行并保留空结果与不可评价项；
- 根据真实结果撰写研究文本或制作图表。

只读分析不会自动创建研究文件。实际实验使用独立运行目录，保存配置、结果、必要诊断和恢复命令。

## 研究记录

`assets/research_record.example.json` 提供结构化主张记录示例。检查器使用 Python 标准库，支持记录结构、本地路径边界、JSON Pointer 和定量值一致性检查：

```bash
python3 scripts/check_research_record.py assets/research_record.example.json --root assets
```

外部 URL 只检查格式，不会自动抓取。`scope` 中的来源数组用于声明研究范围，不执行来源成员资格校验。非 JSON 来源以及只出现在 `statement` 中的数字需要人工核对。记录通过检查后仍需阅读实际来源并审阅主张语义。

## 文件

- `SKILL.md`：任务分流、执行步骤与完成条件；
- `references/evidence.md`：来源层级、主张状态和定量字段；
- `references/experiments.md`：对照、共同支持、预算、统计和失败诊断；
- `references/communication.md`：论证、图表、稿件与交付检查；
- `scripts/check_research_record.py`：研究记录检查器；
- `evals/`：基于 `skill-up` 的确定性评测配置。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_research_record.py assets/research_record.example.json --root assets
skill-up validate evals/eval.yaml
skill-up run evals/eval.yaml
```

`skill-up run` 使用本机 Claude Code 引擎及其已有登录状态。评测使用 `environment.type: none`，引擎由 `skill-up` 以 `bypassPermissions` 启动，运行前确认本机工作区权限符合预期。运行产物写入仓库旁的 `<仓库目录名>-workspace/`。

## 许可证

MIT
