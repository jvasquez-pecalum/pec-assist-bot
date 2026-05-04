-- Migration: channel_config + email_requests tables
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS channel_config (
    channel_type VARCHAR(20) PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO channel_config (channel_type, is_active, updated_at)
VALUES
    ('teams', true, NOW()),
    ('email', false, NOW())
ON CONFLICT (channel_type) DO NOTHING;

CREATE TABLE IF NOT EXISTS email_requests (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(500) UNIQUE NOT NULL,
    from_email VARCHAR(255),
    from_name VARCHAR(255),
    subject TEXT,
    intent VARCHAR(50),
    urgency VARCHAR(20),
    summary TEXT,
    requires_task BOOLEAN,
    asana_task_id VARCHAR(50),
    asana_task_url TEXT,
    replied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
