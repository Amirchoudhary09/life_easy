-- GENERATED FILE - do not edit by hand.
-- Source of truth: apps/api/app/db/models.py + Alembic migrations in apps/api/alembic/versions.
-- Apply with:  cd apps/api && alembic upgrade head      (DATABASE_URL must point at Postgres + pgvector)
-- Regenerate:  cd apps/api && DATABASE_URL=postgresql+asyncpg://u:p@h/db alembic upgrade head --sql > ../../database/schema.sql

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE EXTENSION IF NOT EXISTS vector;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_users (
    id UUID NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    display_name VARCHAR(120), 
    password_hash VARCHAR(255), 
    is_active BOOLEAN NOT NULL, 
    email_verified_at TIMESTAMP WITH TIME ZONE, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_app_users_email ON app_users (email);

CREATE TABLE jobs (
    id UUID NOT NULL, 
    source VARCHAR(40) NOT NULL, 
    source_job_id VARCHAR(200) NOT NULL, 
    company VARCHAR(200) NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    location VARCHAR(200), 
    remote BOOLEAN, 
    employment_type VARCHAR(60), 
    salary_text VARCHAR(200), 
    description TEXT, 
    apply_url VARCHAR(1000) NOT NULL, 
    source_url VARCHAR(1000), 
    posted_at TIMESTAMP WITH TIME ZONE, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    content_hash VARCHAR(64) NOT NULL, 
    embedding VECTOR(1024), 
    PRIMARY KEY (id), 
    CONSTRAINT uq_job_source UNIQUE (source, source_job_id)
);

CREATE INDEX ix_jobs_posted_at ON jobs (posted_at);

CREATE TABLE processed_events (
    id UUID NOT NULL, 
    provider VARCHAR(20) NOT NULL, 
    event_id VARCHAR(200) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_processed_event UNIQUE (provider, event_id)
);

CREATE TABLE audit_events (
    id UUID NOT NULL, 
    user_id UUID, 
    actor VARCHAR(20) NOT NULL, 
    event_type VARCHAR(60) NOT NULL, 
    target_type VARCHAR(40), 
    target_id VARCHAR(64), 
    details JSONB NOT NULL, 
    request_id VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_events_user_id ON audit_events (user_id);

CREATE TABLE channel_identities (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    provider VARCHAR(20) NOT NULL, 
    external_id VARCHAR(100) NOT NULL, 
    display_name VARCHAR(120), 
    verified_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_channel_identity UNIQUE (provider, external_id)
);

CREATE INDEX ix_channel_identities_user_id ON channel_identities (user_id);

CREATE TABLE conversations (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    channel VARCHAR(20) NOT NULL, 
    title VARCHAR(200), 
    last_message_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_conversations_user_id ON conversations (user_id);

CREATE TABLE job_matches (
    user_id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    score NUMERIC(5, 2) NOT NULL, 
    explanation JSONB NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    digest_sent_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (user_id, job_id), 
    FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE TABLE link_codes (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    code VARCHAR(12) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE, 
    UNIQUE (code)
);

CREATE INDEX ix_link_codes_user_id ON link_codes (user_id);

CREATE TABLE memory_items (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    memory_type VARCHAR(40) NOT NULL, 
    content TEXT NOT NULL, 
    meta JSONB NOT NULL, 
    embedding VECTOR(1024), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_memory_items_user_id ON memory_items (user_id);

CREATE TABLE oauth_connections (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    provider VARCHAR(20) NOT NULL, 
    account_email VARCHAR(320) NOT NULL, 
    scopes JSONB NOT NULL, 
    access_token_enc TEXT, 
    refresh_token_enc TEXT, 
    token_expires_at TIMESTAMP WITH TIME ZONE, 
    extra JSONB NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    last_error TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_oauth_connection UNIQUE (user_id, provider, account_email)
);

CREATE INDEX ix_oauth_connections_user_id ON oauth_connections (user_id);

CREATE TABLE profiles (
    user_id UUID NOT NULL, 
    headline VARCHAR(200), 
    summary TEXT, 
    location VARCHAR(120), 
    experience_years NUMERIC(4, 1), 
    skills JSONB NOT NULL, 
    preferences JSONB NOT NULL, 
    timezone VARCHAR(64) NOT NULL, 
    digest_enabled BOOLEAN NOT NULL, 
    embedding VECTOR(1024), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE TABLE recruiter_contacts (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    company VARCHAR(200) NOT NULL, 
    name VARCHAR(200), 
    role VARCHAR(200), 
    public_email VARCHAR(320), 
    public_profile_url VARCHAR(1000), 
    source_url VARCHAR(1000) NOT NULL, 
    source_excerpt TEXT, 
    retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_recruiter_contacts_user_id ON recruiter_contacts (user_id);

CREATE TABLE refresh_tokens (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE, 
    UNIQUE (token_hash)
);

CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE TABLE resumes (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    content_type VARCHAR(100) NOT NULL, 
    object_key VARCHAR(512) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    text TEXT, 
    parsed JSONB NOT NULL, 
    is_primary BOOLEAN NOT NULL, 
    tailored_for_job_id UUID, 
    embedding VECTOR(1024), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(tailored_for_job_id) REFERENCES jobs (id) ON DELETE SET NULL, 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_resumes_user_id ON resumes (user_id);

CREATE TABLE usage_counters (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    day VARCHAR(10) NOT NULL, 
    kind VARCHAR(40) NOT NULL, 
    count INTEGER NOT NULL, 
    tokens_in INTEGER NOT NULL, 
    tokens_out INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_usage_counter UNIQUE (user_id, day, kind)
);

CREATE INDEX ix_usage_counters_user_id ON usage_counters (user_id);

CREATE TABLE applications (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    job_id UUID, 
    contact_id UUID, 
    company VARCHAR(200) NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    source_url VARCHAR(1000), 
    applied_at TIMESTAMP WITH TIME ZONE, 
    next_follow_up_at TIMESTAMP WITH TIME ZONE, 
    last_contact_at TIMESTAMP WITH TIME ZONE, 
    notes TEXT, 
    resume_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(contact_id) REFERENCES recruiter_contacts (id) ON DELETE SET NULL, 
    FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE SET NULL, 
    FOREIGN KEY(resume_id) REFERENCES resumes (id) ON DELETE SET NULL, 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_applications_user_id ON applications (user_id);

CREATE TABLE messages (
    id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    content TEXT NOT NULL, 
    meta JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_messages_conversation_id ON messages (conversation_id);

CREATE INDEX ix_messages_user_id ON messages (user_id);

CREATE TABLE action_approvals (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    action_type VARCHAR(60) NOT NULL, 
    channel VARCHAR(40) NOT NULL, 
    destination JSONB NOT NULL, 
    subject VARCHAR(500), 
    body TEXT NOT NULL, 
    attachments JSONB NOT NULL, 
    payload JSONB NOT NULL, 
    content_hash VARCHAR(64) NOT NULL, 
    idempotency_key VARCHAR(80) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    preview_channel VARCHAR(20), 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    approved_at TIMESTAMP WITH TIME ZONE, 
    rejected_at TIMESTAMP WITH TIME ZONE, 
    executed_at TIMESTAMP WITH TIME ZONE, 
    result JSONB NOT NULL, 
    error TEXT, 
    related_application_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(related_application_id) REFERENCES applications (id) ON DELETE SET NULL, 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE, 
    UNIQUE (idempotency_key)
);

CREATE INDEX ix_action_approvals_user_id ON action_approvals (user_id);

CREATE TABLE application_events (
    id UUID NOT NULL, 
    application_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    from_status VARCHAR(20), 
    to_status VARCHAR(20) NOT NULL, 
    note TEXT, 
    source VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(application_id) REFERENCES applications (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_application_events_application_id ON application_events (application_id);

CREATE INDEX ix_application_events_user_id ON application_events (user_id);

CREATE TABLE interviews (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    application_id UUID NOT NULL, 
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    kind VARCHAR(40) NOT NULL, 
    location VARCHAR(500), 
    notes TEXT, 
    prep_sent_at TIMESTAMP WITH TIME ZONE, 
    outcome VARCHAR(40), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(application_id) REFERENCES applications (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_interviews_application_id ON interviews (application_id);

CREATE INDEX ix_interviews_user_id ON interviews (user_id);

CREATE TABLE follow_ups (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    application_id UUID NOT NULL, 
    due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    approval_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(application_id) REFERENCES applications (id) ON DELETE CASCADE, 
    FOREIGN KEY(approval_id) REFERENCES action_approvals (id) ON DELETE SET NULL, 
    FOREIGN KEY(user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX ix_follow_ups_application_id ON follow_ups (application_id);

CREATE INDEX ix_follow_ups_user_id ON follow_ups (user_id);

CREATE INDEX IF NOT EXISTS ix_jobs_embedding_hnsw ON jobs USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS ix_memory_items_embedding_hnsw ON memory_items USING hnsw (embedding vector_cosine_ops);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

