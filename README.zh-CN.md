# HarmonyOS Agent Skills

[English](README.md) | [简体中文](README.zh-CN.md)

面向 AI Coding Agent 的 HarmonyOS / DevEco Studio 工程化技能集，覆盖项目审计、构建排障、Release 签名、验签与 Git 安全。

> 先诊断环境，再修改应用。

> 修改之前，先拿证据。

## 为什么需要这个项目

DevEco Studio 中可以构建，并不代表独立 PowerShell 中的 `hvigorw` 一定具备相同的 Node、SDK 和 Java 环境。Release 阶段还会同时涉及本机凭据、受版本影响的工具、受 Git 跟踪的配置和最终产物。这里的 Skill 将这些问题拆成可审计的工程门禁，让 AI Agent 先判断故障层级，再提出最小动作。

它是 AI 工程 Skill，不是 HarmonyOS 入门教材，也不是 ArkTS API 百科。

## Skills

| Skill | 适用场景 |
| --- | --- |
| [`harmonyos-project-audit`](skills/harmonyos-project-audit/SKILL.md) | 初次接手项目时，只读建立 Git、工程、构建、模块、产品、SDK 与签名基线。 |
| [`harmonyos-build-doctor`](skills/harmonyos-build-doctor/SKILL.md) | 诊断 Node、SDK、Java、Hvigor 与 DevEco CLI 环境，不先改业务代码。 |
| [`harmonyos-release-signing`](skills/harmonyos-release-signing/SKILL.md) | 安全检查 Debug/Release 签名，并将凭据和本机差异挡在 Git 之外。 |
| [`harmonyos-release-check`](skills/harmonyos-release-check/SKILL.md) | 发布前构建、独立验签、设备冒烟、恢复本机配置并确认 Git clean。 |

## 能解决什么问题

- IDE 可用，但命令行找不到 Node、SDK 组件或 Java。
- 环境错误被误判为 ArkTS 或业务代码错误。
- 本机 Release 签名需要配置，但 keystore、profile、密码和私有补丁不得泄露。
- 已生成 `.app`，但尚未独立确认签名、证书、profile、bundle 与构建模式。
- AI 第一次接手仓库，需要先形成可复现事实基线。

## 安装

克隆仓库后，只安装实际需要的 Skill。对 Codex，可将 `skills/` 下的单个目录复制到当前配置的 Codex skills 目录；也可以在工作区中保留本仓库并按路径调用。

```powershell
git clone <repository-url> harmonyos-agent-skills
Copy-Item -Recurse -LiteralPath .\harmonyos-agent-skills\skills\harmonyos-project-audit -Destination <codex-skills-directory>
```

不要把本机签名材料与 Skill 一起复制。

## 快速开始

先做只读审计：

```text
使用 $harmonyos-project-audit 建立当前工程基线，不要修改任何文件。
```

诊断命令行构建环境：

```text
使用 $harmonyos-build-doctor。DevEco Studio 可以构建，但 PowerShell 中同一 Hvigor 任务失败。
```

只读环境探针：

```powershell
.\scripts\check-deveco-env.ps1 -ProjectPath <project-root>
.\scripts\check-deveco-env.ps1 -ProjectPath <project-root> -Json
```

## 示例提示

- `使用 $harmonyos-project-audit 输出当前状态、风险、未知项和最小下一步。`
- `使用 $harmonyos-build-doctor 诊断 spawn java ENOENT，优先复用 IDE 自带 JBR，不做永久环境修改。`
- `使用 $harmonyos-release-signing 审查脱敏 build profile，不打印 password 字段。`
- `使用 $harmonyos-release-check 独立验证最终 APP，并在打 Tag 前停止。`

脱敏输入与证据格式见 [`examples/`](examples/)。

## 安全模型

1. 默认先只读审计。
2. 区分环境、配置、代码、凭据与最终验签失败。
3. 修改目标工程前要求明确授权。
4. 优先使用当前进程临时环境，不永久修改系统。
5. 签名材料默认放在仓库外。
6. 构建成功不等于最终产物已验签。
7. Tag 或发布前恢复本机差异，并确认 Git clean。

运行仓库自检：

```powershell
python scripts\validate_skills.py
python -m unittest discover -s tests -v
python scripts\scan_private_markers.py --generic-only
```

审计私有来源时，仅在运行时通过 `--marker` 或 `--marker-file` 传入私有标识，绝不能提交到仓库。

## 仓库结构

```text
skills/      可直接调用的 Skill、参考资料和随附脚本
scripts/     结构校验、隐私扫描和环境探针入口
examples/    脱敏构建、签名与发布案例
tests/       单元测试和决策契约 fixture
docs/        架构、兼容性、安全边界与设计原则
.github/     CI、Issue 表单与 PR 模板
```

## 兼容性

当前以 Windows 上的 DevEco Studio 与 HarmonyOS 应用工程为主要场景，Git 和审计原则大多可跨平台使用。工具路径、任务名、参数、SDK 布局和签名行为可能随版本变化；执行前必须查看本机工具帮助与项目配置。详见 [`docs/compatibility.md`](docs/compatibility.md)。

## 贡献

请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。PR 应小而聚焦，必须提供脱敏示例和测试，禁止提交真实签名材料或私有工程内容。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。

## 免责声明

这些 Skill 提供工程护栏，但不保证所有 DevEco Studio 与 HarmonyOS 版本的行为完全一致。执行签名、真机测试、发布或账号相关操作前，仍需使用者确认并承担最终责任。
