CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_users (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 email TEXT UNIQUE NOT NULL,
 display_name TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS profiles (
 user_id UUID PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
 headline TEXT, location TEXT, experience_years NUMERIC(4,1),
 skills JSONB NOT NULL DEFAULT '[]'::jsonb,
 preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
 resume_object_key TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jobs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 source TEXT NOT NULL, source_job_id TEXT, company TEXT NOT NULL,
 title TEXT NOT NULL, location TEXT, employment_type TEXT,
 experience_text TEXT, description TEXT, apply_url TEXT NOT NULL,
 posted_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
 source_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(source, source_job_id)
);
CREATE TABLE IF NOT EXISTS job_matches (
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 match_score NUMERIC(5,2), explanation JSONB NOT NULL DEFAULT '{}'::jsonb,
 status TEXT NOT NULL DEFAULT 'saved', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id, job_id)
);
CREATE TABLE IF NOT EXISTS recruiter_contacts (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), company TEXT NOT NULL,
 name TEXT, role TEXT, public_email TEXT, public_profile_url TEXT,
 source_url TEXT NOT NULL, verified_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS applications (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
 contact_id UUID REFERENCES recruiter_contacts(id) ON DELETE SET NULL,
 status TEXT NOT NULL DEFAULT 'planned', applied_at TIMESTAMPTZ,
 notes TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS action_approvals (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 action_type TEXT NOT NULL, payload JSONB NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', approved_at TIMESTAMPTZ,
 executed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS memory_items (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 memory_type TEXT NOT NULL, content TEXT NOT NULL,
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb, embedding VECTOR(768),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memory_items_embedding_idx
 ON memory_items USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
