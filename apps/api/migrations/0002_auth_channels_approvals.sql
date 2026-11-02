ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS password_hash TEXT,
  ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS phone_e164 TEXT,
  ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS app_users_phone_e164_unique ON app_users(phone_e164) WHERE phone_e164 IS NOT NULL;
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
CREATE INDEX IF NOT EXISTS channel_identities_user_idx ON channel_identities(user_id);

CREATE TABLE IF NOT EXISTS conversations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 channel TEXT NOT NULL,
 channel_conversation_id TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversations_user_updated_idx ON conversations(user_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS conversation_messages (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 direction TEXT NOT NULL CHECK(direction IN ('inbound','outbound')),
 body TEXT NOT NULL,
 provider_message_id TEXT UNIQUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversation_messages_user_created_idx ON conversation_messages(user_id,created_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 event_type TEXT NOT NULL,
 resource_id UUID,
 details JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_events_user_created_idx ON audit_events(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS action_approvals_user_status_idx ON action_approvals(user_id,status,created_at DESC);
