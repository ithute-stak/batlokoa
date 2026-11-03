-- Migrated by privileged release job, never API bootstrap.
-- Encrypted transient OIDC secrets. State stored as irreversible SHA-256.
CREATE TABLE IF NOT EXISTS "public".oidc_login_transactions (
 state_sha256 CHAR(64) PRIMARY KEY,
 encrypted_payload BYTEA NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL,
 CONSTRAINT ck_oidc_transaction_expiration CHECK (expires_at > created_at),
 CONSTRAINT ck_oidc_transaction_payload_size CHECK (octet_length(encrypted_payload) BETWEEN 64 AND 4096)
);
CREATE INDEX IF NOT EXISTS ix_oidc_login_transactions_expiry
 ON "public".oidc_login_transactions (expires_at);
