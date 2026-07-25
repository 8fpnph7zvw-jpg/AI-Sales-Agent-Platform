-- AI Sales Agent Platform
-- MySQL 8.0 baseline schema
-- All DATETIME values are UTC. The application is responsible for UTC conversion.

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
SET time_zone = '+00:00';

CREATE TABLE tenants (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    name VARCHAR(160) NOT NULL,
    slug VARCHAR(80) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    plan_code VARCHAR(50) NOT NULL DEFAULT 'standard',
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    default_currency CHAR(3) NOT NULL DEFAULT 'USD',
    data_region VARCHAR(32) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    CONSTRAINT pk_tenants PRIMARY KEY (id),
    CONSTRAINT uq_tenants_public_id UNIQUE (public_id),
    CONSTRAINT uq_tenants_slug UNIQUE (slug),
    CONSTRAINT ck_tenants_status_allowed
        CHECK (status IN ('active', 'suspended', 'closed')),
    INDEX ix_tenants_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE permissions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(120) NOT NULL,
    resource VARCHAR(80) NOT NULL,
    action VARCHAR(80) NOT NULL,
    description TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_permissions PRIMARY KEY (id),
    CONSTRAINT uq_permissions_code UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NULL,
    display_name VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'invited',
    locale VARCHAR(16) NOT NULL DEFAULT 'en',
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uq_users_public_id UNIQUE (public_id),
    CONSTRAINT tenant_email UNIQUE (tenant_id, email),
    CONSTRAINT ck_users_status_allowed
        CHECK (status IN ('invited', 'active', 'locked', 'disabled')),
    CONSTRAINT fk_users_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    INDEX ix_users_tenant_status (tenant_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE roles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    code VARCHAR(80) NOT NULL,
    name VARCHAR(120) NOT NULL,
    description TEXT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_roles PRIMARY KEY (id),
    CONSTRAINT uq_roles_public_id UNIQUE (public_id),
    CONSTRAINT tenant_code UNIQUE (tenant_id, code),
    CONSTRAINT fk_roles_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE user_roles (
    user_id BIGINT UNSIGNED NOT NULL,
    role_id BIGINT UNSIGNED NOT NULL,
    assigned_by BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_roles_user_id_users
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_role_id_roles
        FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_assigned_by_users
        FOREIGN KEY (assigned_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_user_roles_role_id (role_id),
    INDEX ix_user_roles_assigned_by (assigned_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE role_permissions (
    role_id BIGINT UNSIGNED NOT NULL,
    permission_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_role_permissions PRIMARY KEY (role_id, permission_id),
    CONSTRAINT fk_role_permissions_role_id_roles
        FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE,
    CONSTRAINT fk_role_permissions_permission_id_permissions
        FOREIGN KEY (permission_id) REFERENCES permissions (id) ON DELETE CASCADE,
    INDEX ix_role_permissions_permission_id (permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE auth_sessions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    refresh_token_hash VARCHAR(128) NOT NULL,
    token_family_id CHAR(26) NOT NULL,
    ip_hash VARCHAR(128) NULL,
    user_agent_hash VARCHAR(128) NULL,
    expires_at DATETIME(6) NOT NULL,
    last_used_at DATETIME(6) NULL,
    revoked_at DATETIME(6) NULL,
    revoke_reason VARCHAR(120) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_auth_sessions PRIMARY KEY (id),
    CONSTRAINT uq_auth_sessions_public_id UNIQUE (public_id),
    CONSTRAINT uq_auth_sessions_refresh_token_hash UNIQUE (refresh_token_hash),
    CONSTRAINT fk_auth_sessions_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_auth_sessions_user_id_users
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    INDEX ix_auth_sessions_user_active (user_id, revoked_at, expires_at),
    INDEX ix_auth_sessions_token_family (token_family_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(160) NOT NULL,
    company_name VARCHAR(200) NULL,
    email VARCHAR(254) NULL,
    phone_e164 VARCHAR(32) NULL,
    country_code CHAR(2) NULL,
    language VARCHAR(16) NULL,
    lifecycle_stage VARCHAR(32) NOT NULL DEFAULT 'new',
    intent_score DECIMAL(5,2) NULL,
    intent_level VARCHAR(24) NULL,
    score_explanation JSON NULL,
    source_type VARCHAR(64) NULL,
    source_ref VARCHAR(255) NULL,
    tags JSON NOT NULL,
    owner_user_id BIGINT UNSIGNED NULL,
    created_by BIGINT UNSIGNED NULL,
    consent_status VARCHAR(24) NOT NULL DEFAULT 'unknown',
    do_not_contact BOOLEAN NOT NULL DEFAULT FALSE,
    last_contact_at DATETIME(6) NULL,
    notes TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    CONSTRAINT pk_customers PRIMARY KEY (id),
    CONSTRAINT uq_customers_public_id UNIQUE (public_id),
    CONSTRAINT ck_customers_intent_score_range
        CHECK (intent_score IS NULL OR (intent_score >= 0 AND intent_score <= 100)),
    CONSTRAINT fk_customers_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT fk_customers_owner_user_id_users
        FOREIGN KEY (owner_user_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT fk_customers_created_by_users
        FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_customers_tenant_owner_stage (tenant_id, owner_user_id, lifecycle_stage),
    INDEX ix_customers_tenant_score (tenant_id, intent_score),
    INDEX ix_customers_tenant_email (tenant_id, email),
    INDEX ix_customers_tenant_phone (tenant_id, phone_e164)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE connectors (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    provider VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'draft',
    capabilities JSON NOT NULL,
    external_account_id VARCHAR(255) NOT NULL,
    health_status VARCHAR(32) NULL,
    health_detail JSON NULL,
    last_health_check_at DATETIME(6) NULL,
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    CONSTRAINT pk_connectors PRIMARY KEY (id),
    CONSTRAINT uq_connectors_public_id UNIQUE (public_id),
    CONSTRAINT tenant_provider_account
        UNIQUE (tenant_id, provider, external_account_id),
    CONSTRAINT ck_connectors_status_allowed
        CHECK (status IN ('draft', 'active', 'disabled', 'error')),
    CONSTRAINT fk_connectors_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT fk_connectors_created_by_users
        FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_connectors_tenant_status (tenant_id, status),
    INDEX ix_connectors_tenant_provider (tenant_id, provider)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE connector_configs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    connector_id BIGINT UNSIGNED NOT NULL,
    config_key VARCHAR(120) NOT NULL,
    value_type VARCHAR(24) NOT NULL DEFAULT 'string',
    value_encrypted MEDIUMBLOB NULL,
    secret_ref VARCHAR(512) NULL,
    key_version VARCHAR(64) NULL,
    is_secret BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_connector_configs PRIMARY KEY (id),
    CONSTRAINT connector_key UNIQUE (connector_id, config_key),
    CONSTRAINT fk_connector_configs_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_connector_configs_connector_id_connectors
        FOREIGN KEY (connector_id) REFERENCES connectors (id) ON DELETE CASCADE,
    CONSTRAINT fk_connector_configs_updated_by_users
        FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_connector_configs_tenant_id (tenant_id),
    INDEX ix_connector_configs_updated_by (updated_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE customer_sessions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    connector_id BIGINT UNSIGNED NOT NULL,
    external_contact_id VARCHAR(255) NOT NULL,
    external_thread_id VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    first_seen_at DATETIME(6) NOT NULL,
    last_seen_at DATETIME(6) NOT NULL,
    metadata JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_customer_sessions PRIMARY KEY (id),
    CONSTRAINT uq_customer_sessions_public_id UNIQUE (public_id),
    CONSTRAINT external_identity
        UNIQUE (tenant_id, connector_id, external_contact_id, external_thread_id),
    CONSTRAINT fk_customer_sessions_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT fk_customer_sessions_customer_id_customers
        FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
    CONSTRAINT fk_customer_sessions_connector_id_connectors
        FOREIGN KEY (connector_id) REFERENCES connectors (id) ON DELETE RESTRICT,
    INDEX ix_customer_sessions_customer_last_seen (customer_id, last_seen_at),
    INDEX ix_customer_sessions_connector_id (connector_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE prompts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    prompt_key VARCHAR(100) NOT NULL,
    name VARCHAR(160) NOT NULL,
    version INT UNSIGNED NOT NULL,
    purpose VARCHAR(255) NULL,
    content MEDIUMTEXT NOT NULL,
    variables_schema JSON NULL,
    output_schema JSON NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'draft',
    dify_app_id VARCHAR(128) NULL,
    created_by BIGINT UNSIGNED NULL,
    published_by BIGINT UNSIGNED NULL,
    published_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_prompts PRIMARY KEY (id),
    CONSTRAINT uq_prompts_public_id UNIQUE (public_id),
    CONSTRAINT tenant_key_version UNIQUE (tenant_id, prompt_key, version),
    CONSTRAINT ck_prompts_status_allowed
        CHECK (status IN ('draft', 'published', 'retired')),
    CONSTRAINT fk_prompts_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_prompts_created_by_users
        FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT fk_prompts_published_by_users
        FOREIGN KEY (published_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_prompts_created_by (created_by),
    INDEX ix_prompts_published_by (published_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE conversations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_session_id BIGINT UNSIGNED NOT NULL,
    subject VARCHAR(255) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'open',
    mode VARCHAR(16) NOT NULL DEFAULT 'ai',
    assigned_user_id BIGINT UNSIGNED NULL,
    priority VARCHAR(16) NOT NULL DEFAULT 'normal',
    unread_count INT UNSIGNED NOT NULL DEFAULT 0,
    ai_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    handoff_reason VARCHAR(500) NULL,
    last_message_at DATETIME(6) NULL,
    closed_at DATETIME(6) NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_conversations PRIMARY KEY (id),
    CONSTRAINT uq_conversations_public_id UNIQUE (public_id),
    CONSTRAINT ck_conversations_status_allowed
        CHECK (status IN ('open', 'pending', 'closed', 'blocked')),
    CONSTRAINT ck_conversations_mode_allowed
        CHECK (mode IN ('ai', 'assisted', 'human')),
    CONSTRAINT fk_conversations_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT fk_conversations_customer_id_customers
        FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
    CONSTRAINT fk_conversations_customer_session_id_customer_sessions
        FOREIGN KEY (customer_session_id) REFERENCES customer_sessions (id) ON DELETE RESTRICT,
    CONSTRAINT fk_conversations_assigned_user_id_users
        FOREIGN KEY (assigned_user_id) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_conversations_tenant_assignee_status
        (tenant_id, assigned_user_id, status),
    INDEX ix_conversations_tenant_last_message (tenant_id, last_message_at),
    INDEX ix_conversations_customer (customer_id, created_at),
    INDEX ix_conversations_customer_session_id (customer_session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE messages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    conversation_id BIGINT UNSIGNED NOT NULL,
    connector_id BIGINT UNSIGNED NULL,
    sequence_no INT UNSIGNED NOT NULL,
    direction VARCHAR(16) NOT NULL,
    sender_type VARCHAR(16) NOT NULL,
    sender_ref VARCHAR(255) NULL,
    message_type VARCHAR(32) NOT NULL,
    content_text MEDIUMTEXT NULL,
    content_json JSON NULL,
    reply_to_message_id BIGINT UNSIGNED NULL,
    external_message_id VARCHAR(255) NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'received',
    prompt_id BIGINT UNSIGNED NULL,
    citations JSON NULL,
    token_usage JSON NULL,
    error_code VARCHAR(120) NULL,
    sent_at DATETIME(6) NULL,
    delivered_at DATETIME(6) NULL,
    read_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_messages PRIMARY KEY (id),
    CONSTRAINT uq_messages_public_id UNIQUE (public_id),
    CONSTRAINT conversation_sequence UNIQUE (conversation_id, sequence_no),
    CONSTRAINT tenant_idempotency UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT ck_messages_direction_allowed
        CHECK (direction IN ('inbound', 'outbound', 'internal')),
    CONSTRAINT ck_messages_sender_type_allowed
        CHECK (sender_type IN ('customer', 'ai', 'user', 'system')),
    CONSTRAINT fk_messages_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT fk_messages_conversation_id_conversations
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
    CONSTRAINT fk_messages_connector_id_connectors
        FOREIGN KEY (connector_id) REFERENCES connectors (id) ON DELETE SET NULL,
    CONSTRAINT fk_messages_reply_to_message_id_messages
        FOREIGN KEY (reply_to_message_id) REFERENCES messages (id) ON DELETE SET NULL,
    CONSTRAINT fk_messages_prompt_id_prompts
        FOREIGN KEY (prompt_id) REFERENCES prompts (id) ON DELETE SET NULL,
    INDEX ix_messages_conversation_created (conversation_id, created_at),
    INDEX ix_messages_external (connector_id, external_message_id),
    INDEX ix_messages_tenant_status (tenant_id, status, created_at),
    INDEX ix_messages_reply_to_message_id (reply_to_message_id),
    INDEX ix_messages_prompt_id (prompt_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_agent_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    conversation_id BIGINT UNSIGNED NOT NULL,
    trigger_message_id BIGINT UNSIGNED NULL,
    output_message_id BIGINT UNSIGNED NULL,
    prompt_id BIGINT UNSIGNED NULL,
    run_type VARCHAR(40) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    model_name VARCHAR(120) NULL,
    dify_conversation_id VARCHAR(128) NULL,
    dify_task_id VARCHAR(128) NULL,
    input_redacted JSON NULL,
    output_redacted JSON NULL,
    extracted_needs JSON NULL,
    citations JSON NULL,
    policy_result JSON NULL,
    intent_score DECIMAL(5,2) NULL,
    prompt_tokens INT UNSIGNED NULL,
    completion_tokens INT UNSIGNED NULL,
    cost_amount DECIMAL(19,6) NULL,
    cost_currency CHAR(3) NULL,
    latency_ms INT UNSIGNED NULL,
    error_code VARCHAR(120) NULL,
    error_message TEXT NULL,
    started_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_ai_agent_runs PRIMARY KEY (id),
    CONSTRAINT uq_ai_agent_runs_public_id UNIQUE (public_id),
    CONSTRAINT ck_ai_agent_runs_status_allowed
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'timed_out')),
    CONSTRAINT fk_ai_agent_runs_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ai_agent_runs_conversation_id_conversations
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
    CONSTRAINT fk_ai_agent_runs_trigger_message_id_messages
        FOREIGN KEY (trigger_message_id) REFERENCES messages (id) ON DELETE SET NULL,
    CONSTRAINT fk_ai_agent_runs_output_message_id_messages
        FOREIGN KEY (output_message_id) REFERENCES messages (id) ON DELETE SET NULL,
    CONSTRAINT fk_ai_agent_runs_prompt_id_prompts
        FOREIGN KEY (prompt_id) REFERENCES prompts (id) ON DELETE SET NULL,
    INDEX ix_ai_agent_runs_conversation_created (conversation_id, created_at),
    INDEX ix_ai_agent_runs_tenant_status (tenant_id, status, created_at),
    INDEX ix_ai_agent_runs_dify_task (dify_task_id),
    INDEX ix_ai_agent_runs_trigger_message_id (trigger_message_id),
    INDEX ix_ai_agent_runs_output_message_id (output_message_id),
    INDEX ix_ai_agent_runs_prompt_id (prompt_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE knowledge_collections (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(160) NOT NULL,
    description VARCHAR(1000) NULL,
    dify_dataset_id VARCHAR(128) NULL,
    embedding_provider VARCHAR(80) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    CONSTRAINT pk_knowledge_collections PRIMARY KEY (id),
    CONSTRAINT uq_knowledge_collections_public_id UNIQUE (public_id),
    CONSTRAINT tenant_name UNIQUE (tenant_id, name),
    CONSTRAINT fk_knowledge_collections_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_collections_created_by_users
        FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_knowledge_collections_created_by (created_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE knowledge_files (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    collection_id BIGINT UNSIGNED NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    mime_type VARCHAR(160) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    sha256 CHAR(64) NOT NULL,
    language VARCHAR(16) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'uploaded',
    dify_document_id VARCHAR(128) NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    error_message VARCHAR(1000) NULL,
    uploaded_by BIGINT UNSIGNED NULL,
    processed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    CONSTRAINT pk_knowledge_files PRIMARY KEY (id),
    CONSTRAINT uq_knowledge_files_public_id UNIQUE (public_id),
    CONSTRAINT uq_knowledge_files_object_key UNIQUE (object_key),
    CONSTRAINT fk_knowledge_files_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_files_collection_id_knowledge_collections
        FOREIGN KEY (collection_id) REFERENCES knowledge_collections (id) ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_files_uploaded_by_users
        FOREIGN KEY (uploaded_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_knowledge_files_collection_status (collection_id, status),
    INDEX ix_knowledge_files_tenant_hash (tenant_id, sha256),
    INDEX ix_knowledge_files_uploaded_by (uploaded_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE knowledge_chunks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    knowledge_file_id BIGINT UNSIGNED NOT NULL,
    chunk_index INT UNSIGNED NOT NULL,
    content_text MEDIUMTEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    token_count INT UNSIGNED NULL,
    metadata JSON NULL,
    dify_segment_id VARCHAR(128) NULL,
    sync_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_knowledge_chunks PRIMARY KEY (id),
    CONSTRAINT uq_knowledge_chunks_public_id UNIQUE (public_id),
    CONSTRAINT file_chunk_index UNIQUE (knowledge_file_id, chunk_index),
    CONSTRAINT fk_knowledge_chunks_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_chunks_knowledge_file_id_knowledge_files
        FOREIGN KEY (knowledge_file_id) REFERENCES knowledge_files (id) ON DELETE CASCADE,
    INDEX ix_knowledge_chunks_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    sku VARCHAR(120) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT NULL,
    category VARCHAR(120) NULL,
    unit VARCHAR(32) NOT NULL,
    currency CHAR(3) NOT NULL,
    base_price DECIMAL(19,4) NOT NULL,
    min_order_qty DECIMAL(19,4) NULL,
    attributes JSON NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    CONSTRAINT pk_products PRIMARY KEY (id),
    CONSTRAINT uq_products_public_id UNIQUE (public_id),
    CONSTRAINT tenant_sku UNIQUE (tenant_id, sku),
    CONSTRAINT fk_products_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE quotations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    quotation_no VARCHAR(64) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    conversation_id BIGINT UNSIGNED NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'draft',
    currency CHAR(3) NOT NULL,
    subtotal DECIMAL(19,4) NOT NULL DEFAULT 0,
    discount_amount DECIMAL(19,4) NOT NULL DEFAULT 0,
    tax_amount DECIMAL(19,4) NOT NULL DEFAULT 0,
    shipping_amount DECIMAL(19,4) NOT NULL DEFAULT 0,
    total_amount DECIMAL(19,4) NOT NULL DEFAULT 0,
    valid_until DATE NULL,
    incoterm VARCHAR(16) NULL,
    payment_terms VARCHAR(500) NULL,
    notes TEXT NULL,
    ai_suggestion JSON NULL,
    created_by BIGINT UNSIGNED NULL,
    approved_by BIGINT UNSIGNED NULL,
    approved_at DATETIME(6) NULL,
    sent_at DATETIME(6) NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_quotations PRIMARY KEY (id),
    CONSTRAINT uq_quotations_public_id UNIQUE (public_id),
    CONSTRAINT tenant_number UNIQUE (tenant_id, quotation_no),
    CONSTRAINT ck_quotations_status_allowed
        CHECK (status IN ('draft', 'pending_approval', 'approved', 'sent', 'accepted',
                          'rejected', 'expired', 'cancelled')),
    CONSTRAINT fk_quotations_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT fk_quotations_customer_id_customers
        FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
    CONSTRAINT fk_quotations_conversation_id_conversations
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE SET NULL,
    CONSTRAINT fk_quotations_created_by_users
        FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT fk_quotations_approved_by_users
        FOREIGN KEY (approved_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_quotations_tenant_status_created (tenant_id, status, created_at),
    INDEX ix_quotations_customer (customer_id, created_at),
    INDEX ix_quotations_conversation_id (conversation_id),
    INDEX ix_quotations_created_by (created_by),
    INDEX ix_quotations_approved_by (approved_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE quotation_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quotation_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NULL,
    sku_snapshot VARCHAR(120) NOT NULL,
    name_snapshot VARCHAR(200) NOT NULL,
    description TEXT NULL,
    quantity DECIMAL(19,4) NOT NULL,
    unit VARCHAR(32) NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL,
    discount_rate DECIMAL(7,4) NOT NULL DEFAULT 0,
    tax_rate DECIMAL(7,4) NOT NULL DEFAULT 0,
    line_total DECIMAL(19,4) NOT NULL,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_quotation_items PRIMARY KEY (id),
    CONSTRAINT fk_quotation_items_quotation_id_quotations
        FOREIGN KEY (quotation_id) REFERENCES quotations (id) ON DELETE CASCADE,
    CONSTRAINT fk_quotation_items_product_id_products
        FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE SET NULL,
    INDEX ix_quotation_items_quotation_id (quotation_id),
    INDEX ix_quotation_items_product_id (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE workflows (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(160) NOT NULL,
    trigger_type VARCHAR(80) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'draft',
    version INT UNSIGNED NOT NULL,
    definition JSON NULL,
    n8n_workflow_id VARCHAR(128) NULL,
    last_published_at DATETIME(6) NULL,
    created_by BIGINT UNSIGNED NULL,
    updated_by BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at DATETIME(6) NULL,
    CONSTRAINT pk_workflows PRIMARY KEY (id),
    CONSTRAINT uq_workflows_public_id UNIQUE (public_id),
    CONSTRAINT tenant_name_version UNIQUE (tenant_id, name, version),
    CONSTRAINT ck_workflows_status_allowed
        CHECK (status IN ('draft', 'published', 'active', 'inactive', 'retired')),
    CONSTRAINT fk_workflows_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflows_created_by_users
        FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT fk_workflows_updated_by_users
        FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_workflows_created_by (created_by),
    INDEX ix_workflows_updated_by (updated_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE workflow_nodes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    workflow_id BIGINT UNSIGNED NOT NULL,
    node_key VARCHAR(100) NOT NULL,
    node_type VARCHAR(80) NOT NULL,
    name VARCHAR(160) NOT NULL,
    config JSON NULL,
    position JSON NULL,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_workflow_nodes PRIMARY KEY (id),
    CONSTRAINT uq_workflow_nodes_public_id UNIQUE (public_id),
    CONSTRAINT workflow_node_key UNIQUE (workflow_id, node_key),
    CONSTRAINT fk_workflow_nodes_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflow_nodes_workflow_id_workflows
        FOREIGN KEY (workflow_id) REFERENCES workflows (id) ON DELETE CASCADE,
    INDEX ix_workflow_nodes_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE notifications (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NULL,
    type VARCHAR(64) NOT NULL,
    channel VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    resource_type VARCHAR(80) NULL,
    resource_public_id CHAR(26) NULL,
    priority VARCHAR(16) NOT NULL DEFAULT 'normal',
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    dedupe_key VARCHAR(255) NOT NULL,
    error_code VARCHAR(120) NULL,
    read_at DATETIME(6) NULL,
    sent_at DATETIME(6) NULL,
    failed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_notifications PRIMARY KEY (id),
    CONSTRAINT uq_notifications_public_id UNIQUE (public_id),
    CONSTRAINT tenant_dedupe UNIQUE (tenant_id, dedupe_key),
    CONSTRAINT fk_notifications_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_notifications_user_id_users
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    INDEX ix_notifications_user_unread (user_id, read_at, created_at),
    INDEX ix_notifications_tenant_status (tenant_id, status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE system_configs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    config_key VARCHAR(160) NOT NULL,
    value_json JSON NULL,
    value_encrypted MEDIUMBLOB NULL,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    description VARCHAR(500) NULL,
    updated_by BIGINT UNSIGNED NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_system_configs PRIMARY KEY (id),
    CONSTRAINT tenant_key UNIQUE (tenant_id, config_key),
    CONSTRAINT fk_system_configs_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
    CONSTRAINT fk_system_configs_updated_by_users
        FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL,
    INDEX ix_system_configs_updated_by (updated_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE webhook_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    connector_id BIGINT UNSIGNED NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(120) NULL,
    signature_valid BOOLEAN NOT NULL,
    headers_redacted JSON NULL,
    payload_redacted JSON NULL,
    payload_hash CHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'received',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_retry_at DATETIME(6) NULL,
    processed_at DATETIME(6) NULL,
    error_code VARCHAR(120) NULL,
    error_message TEXT NULL,
    trace_id VARCHAR(64) NULL,
    received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_webhook_logs PRIMARY KEY (id),
    CONSTRAINT uq_webhook_logs_public_id UNIQUE (public_id),
    CONSTRAINT connector_event UNIQUE (connector_id, provider_event_id),
    CONSTRAINT fk_webhook_logs_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT fk_webhook_logs_connector_id_connectors
        FOREIGN KEY (connector_id) REFERENCES connectors (id) ON DELETE RESTRICT,
    INDEX ix_webhook_logs_dispatch (status, next_retry_at, id),
    INDEX ix_webhook_logs_tenant_received (tenant_id, received_at),
    INDEX ix_webhook_logs_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE audit_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    actor_type VARCHAR(32) NOT NULL,
    actor_id VARCHAR(64) NULL,
    action VARCHAR(120) NOT NULL,
    resource_type VARCHAR(80) NOT NULL,
    resource_id VARCHAR(64) NULL,
    result VARCHAR(24) NOT NULL,
    reason TEXT NULL,
    changes_redacted JSON NULL,
    ip_hash VARCHAR(128) NULL,
    user_agent_hash VARCHAR(128) NULL,
    request_id VARCHAR(64) NULL,
    trace_id VARCHAR(64) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_audit_logs PRIMARY KEY (id),
    CONSTRAINT uq_audit_logs_public_id UNIQUE (public_id),
    CONSTRAINT fk_audit_logs_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    INDEX ix_audit_logs_tenant_created (tenant_id, created_at),
    INDEX ix_audit_logs_resource (tenant_id, resource_type, resource_id),
    INDEX ix_audit_logs_actor (tenant_id, actor_type, actor_id),
    INDEX ix_audit_logs_request (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE outbox_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    public_id CHAR(26) NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    available_at DATETIME(6) NOT NULL,
    locked_at DATETIME(6) NULL,
    locked_by VARCHAR(120) NULL,
    published_at DATETIME(6) NULL,
    last_error TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_outbox_events PRIMARY KEY (id),
    CONSTRAINT uq_outbox_events_public_id UNIQUE (public_id),
    CONSTRAINT fk_outbox_events_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    INDEX ix_outbox_events_dispatch (status, available_at, id),
    INDEX ix_outbox_events_aggregate
        (tenant_id, aggregate_type, aggregate_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

