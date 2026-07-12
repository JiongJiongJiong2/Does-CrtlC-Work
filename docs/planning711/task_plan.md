# 项目技术审查与演进计划

## Goal
基于当前未暂存改动、历史实现与 TMP 动画原型，明确动画退化原因、核心剪贴板逻辑问题，以及 Python/C#/C++ 的合理演进路线，并给出可执行的优先级计划。

## Current Phase
Phase 5 (complete)

## Phases

### Phase 1: 仓库与变更盘点
- [x] 识别项目结构、依赖、打包方式和入口
- [x] 对比未暂存改动与当前基线
- [x] 定位 TMP 原型及动画相关代码
- **Status:** complete

### Phase 2: 动画链路审查
- [x] 还原原型动画的状态、时序、缓动和渲染路径
- [x] 对比 Python 实现，定位缺失步骤与卡顿来源
- [x] 提出最小修复方案和验收标准
- **Status:** complete

### Phase 3: 核心功能与性能审查
- [x] 追踪 Ctrl+C、选区、剪贴板和提示 UI 的事件链
- [x] 判断是否真正监听系统剪贴板及是否存在误判/低效轮询
- [x] 给出正确、低开销的 Windows 实现建议
- **Status:** complete

### Phase 4: 技术栈与体积方案评估
- [x] 分析当前 45 MB 体积来源和 Python 优化空间
- [x] 比较 Python、C#、C++ 的开发/体积/部署/系统集成成本
- [x] 提出推荐架构与迁移边界
- **Status:** complete

### Phase 5: 综合路线图与交付
- [x] 汇总结论、风险、优先级和阶段性实施计划
- [x] 为每阶段定义验证方式和建议目录/模块边界
- [x] 交付用户可直接决策的建议
- **Status:** complete

## Key Questions
1. TMP 原型与当前动画在状态机、帧时序、缓动、合成方式上分别差在哪里？
2. 当前实现检测的是 Ctrl+C 按键、选中文本，还是系统剪贴板实际变化？
3. 45 MB 是否值得用跨语言重写解决，还是先优化打包更划算？
4. Windows 原生剪贴板监听和 UI 动画最合适的技术边界是什么？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 先审查再修改代码 | 用户当前要的是分析和计划，且未暂存改动可能属于待发布版本，不能贸然覆盖 |
| 以未暂存 diff、历史基线和 TMP 原型三方对照 | 能区分动画回归、原型遗漏和架构固有问题 |
| 当前版本继续 Python，暂不做 pybind11 混合 | 现有瓶颈不是 CPU 数学，混合方案不移除 Python/PySide/Qt，体积收益极低 |
| 长期 Windows-only 候选为 C# WPF | 原生剪贴板/消息窗口集成成熟，维护成本明显低于 C++ Win32 |
| 系统剪贴板事件与 sequence number 作为成功依据 | 比内容 fingerprint 更符合产品语义，并覆盖非 Ctrl+C 的复制入口 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 在工作区根目录执行 git 命令提示“not a git repository” | 1 | 已定位实际仓库为 `dose-ctrlc/`，后续 Git 调用均在该目录执行 |
| 当前 `spring_ease(1,0,t)` 调用触发 ZeroDivisionError | 1 | 已确认是新旧函数接口错配；列为动画 P0 修复 |
| 更新规划文档时 apply_patch 上下文不匹配 | 1 | 已读取实际内容并改用更小的精确补丁 |
| 完成报告后再次从工作区根调用 git status | 2 | 已保留已知仓库边界；最终状态检查改到 `dose-ctrlc/` |

## Notes
- 只创建本次审查所需的规划文档，不修改产品代码。
- 对动画的判断需要结合代码、资源及可运行验证；无法运行的部分要明确证据边界。
