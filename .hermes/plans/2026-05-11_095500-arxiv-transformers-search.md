# Transformers 论文搜索计划

## Goal

帮助用户找到 transformers 相关的核心学术论文，包括原始论文和重要后续工作。

## Current Context

- 用户请求使用 arxiv skill 搜索 "transformers"
- arXiv API 返回 HTTP 429 错误（速率限制）
- 本地 `papers/` 目录为空，无已下载论文

## Assumptions

- 用户想了解 transformers 架构相关论文
- 可能需要原始论文 "Attention Is All You Need" 及后续重要工作
- 网络搜索可绕过 arXiv API 限流

## Proposed Approach

由于 arXiv API 限流，采用多渠道获取论文信息：

1. 使用网络搜索获取 transformers 关键论文列表
2. 手动构造已知经典论文的 arXiv ID 直接下载
3. 等待 API 限流解除后再尝试批量搜索

## Step-by-Step Plan

| 步骤 | 操作 | 工具 |
|------|------|------|
| 1 | 网络搜索 "transformers attention is all you need arxiv" | web_search |
| 2 | 整理关键论文列表（标题、作者、arXiv ID、年份） | 手动整理 |
| 3 | 使用 arxiv skill 直接通过 ID 下载已知论文 | arxiv skill |
| 4 | 生成论文摘要和关键贡献说明 | 手动总结 |

## Files Likely to Change

- `papers/` 目录（创建并存放 PDF）
- `.hermes/plans/` 目录（本计划文件）

## Tests / Validation

- 确认下载的 PDF 文件大小 > 10KB
- 确认能打开 PDF 文件
- 确认包含目标论文

## Risks & Tradeoffs

| 风险 | 缓解措施 |
|------|----------|
| arXiv API 持续限流 | 使用已知 arXiv ID 直接下载 |
| 网络搜索结果不准确 | 交叉验证多个来源 |
| 下载失败 | 提供论文链接让用户手动下载 |

## Open Questions

- 用户是否需要特定方向的 transformers 论文（如 NLP、CV、音频）？
- 用户需要下载 PDF 还是仅需论文列表？
- 是否需要最新的 transformers 变体论文？

---

**Plan created:** 2026-05-11 09:55 UTC
