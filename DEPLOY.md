# 部署指南

## 1. 依赖

- Docker Engine 24+ 与 Compose plugin
- 推荐 8 vCPU / 32 GB RAM / NVMe；GROBID 与 embedding 模型需要额外内存
- 生产 PostgreSQL 使用带 pgvector 的镜像或已安装 `vector` 扩展的托管 PostgreSQL

## 2. 单机启动

```powershell
cd OmniScopeV1
Copy-Item .env.example .env
# 修改 POSTGRES_PASSWORD、PAPER_SEARCH_API_KEY、PAPER_SEARCH_HOST_DATA_DIR
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8088/healthz
```

首次使用 `EMBEDDING_BACKEND=sentence-transformers` 时，worker 会下载并缓存 BGE-M3。正式或隔离网络环境应提前下载模型并把 `EMBEDDING_MODEL` 指向挂载目录，同时设置 `HF_HUB_OFFLINE=1`。

## 3. 导入与检索

```powershell
curl -X POST http://127.0.0.1:8088/v1/documents `
  -H "X-API-Key: change-me" `
  -F "file=@D:\papers\thesis.pdf" `
  -F "title=学位论文题目"

curl http://127.0.0.1:8088/v1/jobs/1 -H "X-API-Key: change-me"

curl "http://127.0.0.1:8088/v1/search?q=graph neural network for citation recommendation&top_k=10" `
  -H "X-API-Key: change-me"
```

## 4. 离线模型

在一台可联网机器执行：

```powershell
python -m pip install -r requirements.txt
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3', cache_folder='models')"
```

将 `models/` 以只读卷挂载到 API 和 worker，设置：

```dotenv
EMBEDDING_MODEL=/models/bge-m3
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

## 5. 生产化建议

- PostgreSQL 开启 WAL 归档、定期 base backup 与恢复演练；不要把数据库 volume 当作唯一备份。
- 对 API、worker、GROBID 使用独立资源限制；embedding 进程优先独立为模型服务。
- 使用反向代理提供 HTTPS、请求体大小限制和租户级限流。
- 配置健康检查、日志轮转、job 超时回收和磁盘容量告警。
- 迁移升级先在备库/灰度库执行；不要用 `docker compose down -v` 作为普通更新手段。

## 6. GPU

本 compose 默认 CPU 可运行。GPU 部署可将 embedding worker 拆到带 NVIDIA runtime 的服务，并设置 `EMBEDDING_DEVICE=cuda`；数据库和 API 不需要 GPU。不要让每个 Gunicorn worker 各自加载完整模型。
