# OmniScope

面向中文学位论文、英文/中文学术论文的可部署检索服务参考实现。该目录与现有 `app/` 完全隔离，适合作为下一阶段生产化演进基线。

## 解决的问题

- PostgreSQL 保存论文、版本、章节、分块、来源与处理任务；原始 PDF 不进入数据库。
- pgvector HNSW 在数据库侧执行 dense ANN，不再把全部向量载入 Python 内存。
- PostgreSQL GIN + `tsvector` 承担英文词法检索；应用层中文分词后再进入 `simple` 配置，兼顾中文术语和英文精确词。
- Dense 与 lexical 通过 Reciprocal Rank Fusion（RRF）融合，减少只依赖单一检索信号造成的漏召回。
- 结果保留 `document_id/version_id/chunk_id/page_start/page_end/section_path`，支持下游论文评估、引用和生成的证据回溯。
- 导入与解析由数据库任务队列驱动，API 只负责接收文件和返回 job，不在 HTTP 请求内执行长时间解析。
- 默认生产 embedding 为 `BAAI/bge-m3`；测试和无模型环境可使用可重复的 hashing fallback，但该 fallback 不作为生产质量方案。

## 快速开始

```powershell
cd OmniScopeV1
Copy-Item .env.example .env
docker compose up -d --build
curl http://127.0.0.1:8088/healthz
```

上传论文：

```powershell
curl -X POST http://127.0.0.1:8088/v1/documents `
  -H "X-API-Key: change-me" `
  -F "file=@D:\papers\example.pdf" `
  -F "title=Example paper"
```

检索：

```powershell
curl "http://127.0.0.1:8088/v1/search?q=联邦学习中的隐私保护与差分隐私&top_k=10" `
  -H "X-API-Key: change-me"
```

## 文档

- [DESIGN.md](DESIGN.md)：架构、数据模型、检索流程、扩展边界和容量假设。
- [DEPLOY.md](DEPLOY.md)：本地、单机生产和离线模型部署。
- [EVALUATION.md](EVALUATION.md)：离线评测数据格式、指标、压测方法和上线门槛。
- [docs/TECHNICAL_ROUTE.md](docs/TECHNICAL_ROUTE.md)：项目技术路线图与创新点。

## 重要边界

这是可运行的生产化基线，不等同于已经在目标论文库上完成验收。正式上线前必须使用脱敏、授权的论文样本建立 golden set，校准 chunk、RRF、过滤条件和 reranker 阈值，并完成版权、访问控制、备份、恢复和监控验收。
