-- Internal BFF session storage. Apply only through privileged migration tooling.
-- No customer sessions are enabled automatically by applying this migration.
CREATE TABLE IF NOT EXISTS "public".customer_sessions (
  id UUID PRIMARY KEY,
  link_id UUID NOT NULL REFERENCES "public".customer_account_links(id),
  central_sid UUID NOT NULL,
  token_sha256 CHAR(64) NOT NULL UNIQUE,
  csrf_sha256 CHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  CONSTRAINT ck_batlokoa_session_expiration CHECK (expires_at > created_at),
  CONSTRAINT ck_batlokoa_session_revocation CHECK (
    revoked_at IS NULL OR revoked_at >= created_at)
);
CREATE INDEX IF NOT EXISTS ix_batlokoa_sessions_link
  ON "public".customer_sessions (link_id, expires_at);
CREATE INDEX IF NOT EXISTS ix_batlokoa_sessions_central_sid
  ON "public".customer_sessions (central_sid);

-- Durable central IdP session revocations prevent reissuing local sessions
-- against a revoked central session ID.
CREATE TABLE IF NOT EXISTS "public".customer_central_session_revocations (
  central_sid UUID PRIMARY KEY,
  revoked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
