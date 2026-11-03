-- Batlokoa customer-account mapping, append-only audit and irreversible proof reuse prevention.
-- Apply through a reviewed, privileged migration pipeline; NOT at API startup.
-- The separate runtime role needs only SELECT/INSERT on links & events,
-- plus UPDATE(revoked_at) on links. Never grant DELETE or DDL to the runtime.
CREATE TABLE IF NOT EXISTS "public".customer_account_links (
  id UUID PRIMARY KEY,
  issuer TEXT NOT NULL CHECK (length(issuer) BETWEEN 9 AND 512),
  subject TEXT NOT NULL CHECK (length(subject) BETWEEN 1 AND 255),
  tenant_id UUID NOT NULL,
  borrower_id UUID NOT NULL,
  proof_sha256 CHAR(64) NOT NULL UNIQUE,
  consent_sha256 CHAR(64) NOT NULL UNIQUE,
  linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ,
  CONSTRAINT uq_batlokoa_auth_identity UNIQUE (issuer, subject),
  CONSTRAINT uq_batlokoa_tenant_borrower UNIQUE (tenant_id, borrower_id),
  CONSTRAINT ck_batlokoa_revocation_date CHECK (revoked_at IS NULL OR revoked_at >= linked_at)
);
CREATE TABLE IF NOT EXISTS "public".customer_account_link_events (
  id UUID PRIMARY KEY,
  link_id UUID NOT NULL REFERENCES "public".customer_account_links(id),
  event_type VARCHAR(16) NOT NULL CHECK (event_type IN ('linked','revoked')),
  actor_subject TEXT NOT NULL CHECK (length(actor_subject) BETWEEN 1 AND 255),
  reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_batlokoa_link_events_link_id
  ON "public".customer_account_link_events (link_id, created_at);
