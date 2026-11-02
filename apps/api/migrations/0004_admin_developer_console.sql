ALTER TABLE app_users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user', ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
DO $$ BEGIN
  ALTER TABLE app_users ADD CONSTRAINT app_users_role_check CHECK(role IN ('user','admin','developer'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE app_users ADD CONSTRAINT app_users_status_check CHECK(status IN ('active','suspended'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS app_users_role_status_idx ON app_users(role,status,created_at DESC);
CREATE TABLE IF NOT EXISTS admin_job_sources(
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 provider TEXT NOT NULL CHECK(provider IN ('greenhouse','lever')),
 board_key TEXT NOT NULL,
 active BOOLEAN NOT NULL DEFAULT TRUE,
 created_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(provider,board_key)
);
CREATE TABLE IF NOT EXISTS feature_flags(
 flag_key TEXT PRIMARY KEY,
 enabled BOOLEAN NOT NULL DEFAULT FALSE,
 description TEXT NOT NULL DEFAULT '',
 updated_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_events_created_idx ON audit_events(created_at DESC);

CREATE TABLE IF NOT EXISTS worker_heartbeats(
 service_name TEXT PRIMARY KEY,
 last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

INSERT INTO feature_flags(flag_key,enabled,description) VALUES
 ('job_search',TRUE,'Enable user-facing job discovery'),
 ('ai_assistant',TRUE,'Enable the career copilot'),
 ('resume_processing',TRUE,'Enable private resume upload and analysis'),
 ('gmail_integration',TRUE,'Allow users to connect Gmail'),
 ('whatsapp_assistant',TRUE,'Enable linked WhatsApp career assistant replies'),
 ('external_delivery',TRUE,'Allow approved external email and WhatsApp delivery')
ON CONFLICT(flag_key) DO NOTHING;
