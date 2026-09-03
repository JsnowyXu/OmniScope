# 检索评测与上线门槛

## 1. Golden set

建立脱敏 JSONL，每行一个查询：

```json
{"query":"联邦学习中的差分隐私保护","relevant_document_ids":["doc-001","doc-017"],"language":"zh","filters":{"year_from":2020}}
{"query":"retrieval augmented generation for scholarly QA","relevant_document_ids":["doc-203"],"language":"en","filters":{}}
```

查询应覆盖：中文学位论文、英文论文、跨语言查询、方法名/数据集名/DOI、宽主题、窄主题、年份和学科过滤。

## 2. 指标

- Recall@10/20：相关论文是否进入候选集合。
- MRR@10：最早相关结果的位置。
- nDCG@10：多级相关性标注下的排序质量。
- 零结果率与重复论文率。
- API p50/p95/p99 延迟、worker 吞吐、失败重试率和磁盘增长率。

对比至少三组：dense-only、lexical-only、hybrid-RRF；如果启用 reranker，再报告 hybrid+reranker。

## 3. 运行方式

```powershell
python -m pytest -q
python -m omniscope.cli eval --queries eval/golden.jsonl
```

上线前建议目标：Recall@20 不低于现网基线且提升至少 5 个百分点，MRR/nDCG 不下降；p95 由业务确定，但必须在目标并发下稳定，不能只看本地单请求。

## 4. 质量回归

每次改动以下任一项都重新评测：embedding 模型、分块长度/重叠、GROBID 版本、中文分词词典、RRF 参数、metadata filter、reranker、数据库索引参数。
