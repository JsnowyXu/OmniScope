CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS documents (
    id varchar(64) PRIMARY KEY,
    title text NOT NULL,
    authors text NOT NULL DEFAULT '',
    language varchar(16) NOT NULL DEFAULT 'und',
    source varchar(64) NOT NULL DEFAULT 'local',
    external_id varchar(255),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_documents_language ON documents(language);
CREATE INDEX IF NOT EXISTS ix_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS ix_documents_external_id ON documents(external_id);

CREATE TABLE IF NOT EXISTS document_versions (
    id bigserial PRIMARY KEY,
    document_id varchar(64) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    sha256 varchar(64) NOT NULL UNIQUE,
    source_path text NOT NULL,
    page_count integer NOT NULL DEFAULT 0,
    parser varchar(64) NOT NULL DEFAULT 'fallback',
    embedding_model varchar(255) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'queued',
    error text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_document_version_hash ON document_versions(document_id, sha256);
CREATE INDEX IF NOT EXISTS ix_document_versions_document_id ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS ix_document_versions_status ON document_versions(status);

CREATE TABLE IF NOT EXISTS chunks (
    id bigserial PRIMARY KEY,
    version_id bigint NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    chunk_no integer NOT NULL,
    text text NOT NULL,
    lexical_text text NOT NULL,
    section_path text NOT NULL DEFAULT '',
    page_start integer,
    page_end integer,
    char_start integer NOT NULL DEFAULT 0,
    char_end integer NOT NULL DEFAULT 0,
    embedding vector(1024) NOT NULL,
    embedding_model varchar(255) NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, lexical_text)) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_chunk_version_no UNIQUE(version_id, chunk_no)
);
CREATE INDEX IF NOT EXISTS ix_chunks_version_id ON chunks(version_id);
CREATE INDEX IF NOT EXISTS ix_chunks_embedding_model ON chunks(embedding_model);
CREATE INDEX IF NOT EXISTS ix_chunks_search_vector ON chunks USING gin(search_vector);
CREATE INDEX IF NOT EXISTS ix_chunks_lexical_trgm ON chunks USING gin(lexical_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id bigserial PRIMARY KEY,
    version_id bigint NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    status varchar(32) NOT NULL DEFAULT 'queued',
    attempts integer NOT NULL DEFAULT 0,
    error text NOT NULL DEFAULT '',
    locked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_status_id ON ingestion_jobs(status, id);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_version_id ON ingestion_jobs(version_id);
