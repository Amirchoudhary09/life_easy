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

-- MVP account, channel and approval additions (also available as migration 0002).
ALTER TABLE app_users
 ADD COLUMN IF NOT EXISTS password_hash TEXT,
 ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE,
 ADD COLUMN IF NOT EXISTS phone_e164 TEXT,
 ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
 ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE action_approvals ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE TABLE IF NOT EXISTS channel_identities (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 provider TEXT NOT NULL CHECK(provider IN ('whatsapp','telegram')),
 provider_user_id TEXT NOT NULL,
 verified_at TIMESTAMPTZ,
 is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(provider,provider_user_id)
);
CREATE TABLE IF NOT EXISTS conversations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 channel TEXT NOT NULL,
 channel_conversation_id TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conversation_messages (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 direction TEXT NOT NULL CHECK(direction IN ('inbound','outbound')),
 body TEXT NOT NULL,
 provider_message_id TEXT UNIQUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_events (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 event_type TEXT NOT NULL,
 resource_id UUID,
 details JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS channel_identities_user_idx ON channel_identities(user_id);
CREATE INDEX IF NOT EXISTS conversations_user_updated_idx ON conversations(user_id,updated_at DESC);
CREATE INDEX IF NOT EXISTS conversation_messages_user_created_idx ON conversation_messages(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_user_created_idx ON audit_events(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS action_approvals_user_status_idx ON action_approvals(user_id,status,created_at DESC);
