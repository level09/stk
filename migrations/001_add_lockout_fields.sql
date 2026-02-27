-- Account lockout: track failed login attempts
ALTER TABLE user ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user ADD COLUMN locked_until DATETIME NULL;
