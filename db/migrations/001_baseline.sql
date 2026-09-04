-- ============================================================
-- 001_baseline.sql — 12 張表的最終狀態
--
-- 本專案沒有 schema_migrations 版本表，這支檔案每次 migrate 都會全部重跑，
-- 所以每一段都必須可重複執行（見 docs/PITFALLS.md A4）：
--   - 表：CREATE TABLE IF NOT EXISTS
--   - 欄位：ADD COLUMN IF NOT EXISTS
--   - CHECK 約束：先 DROP CONSTRAINT IF EXISTS 再 ADD CONSTRAINT
--     （不可寫在 CREATE TABLE IF NOT EXISTS 裡面，表已存在時整段會被跳過）
--   - 資料：ON CONFLICT DO NOTHING
-- ============================================================

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- 共用的 updated_at 觸發器函式。
-- 注意：attendances、punch_requests、leave_requests、overtime_requests、
-- rooms、holidays 刻意不掛這個觸發器——本專案的業務時間戳一律取自
-- get_virtual_now()，若掛觸發器會呼叫 SQL 的 now()（真實時間），
-- 與虛擬時鐘的偏移量互相矛盾（見 docs/PITFALLS.md A3）。
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- 5.1 departments
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS departments (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    manager_id  INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_departments_updated_at ON departments;
CREATE TRIGGER trg_departments_updated_at
    BEFORE UPDATE ON departments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- 5.2 users
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,
    email             VARCHAR(255) NOT NULL UNIQUE,
    password_hash     VARCHAR(255) NOT NULL,
    role              VARCHAR(20) NOT NULL,
    department_id     INTEGER,
    is_first_login    BOOLEAN NOT NULL DEFAULT true,
    hire_date         DATE NOT NULL DEFAULT CURRENT_DATE,
    extension_number  VARCHAR(20),
    employee_no       VARCHAR(20),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS extension_number VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_no VARCHAR(20);

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('admin', 'manager', 'employee'));

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_department_id_fkey;
ALTER TABLE users ADD CONSTRAINT users_department_id_fkey
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL;

ALTER TABLE departments DROP CONSTRAINT IF EXISTS departments_manager_id_fkey;
ALTER TABLE departments ADD CONSTRAINT departments_manager_id_fkey
    FOREIGN KEY (manager_id) REFERENCES users(id) ON DELETE SET NULL;

CREATE SEQUENCE IF NOT EXISTS employee_no_seq;

CREATE UNIQUE INDEX IF NOT EXISTS users_employee_no_idx
    ON users (employee_no) WHERE employee_no IS NOT NULL;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- 5.3 user_permissions
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_permissions (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission  VARCHAR(50) NOT NULL,
    granted_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, permission)
);

-- CHECK 白名單獨立於 CREATE TABLE IF NOT EXISTS 之外：表已存在時該區塊會被
-- 整段跳過，日後擴充權限鍵只改這支檔案才不會靜默失效（見 SPEC.md §5.3）。
ALTER TABLE user_permissions DROP CONSTRAINT IF EXISTS user_permissions_permission_check;
ALTER TABLE user_permissions ADD CONSTRAINT user_permissions_permission_check
    CHECK (permission IN ('holidays.manage', 'settings.manage', 'exports.run'));

-- ------------------------------------------------------------
-- 5.4 system_settings（恆單列）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_settings (
    id                     INTEGER PRIMARY KEY DEFAULT 1,
    work_start_time        TIME NOT NULL DEFAULT '09:00',
    work_end_time          TIME NOT NULL DEFAULT '18:00',
    lunch_start_time       TIME NOT NULL DEFAULT '12:00',
    lunch_end_time         TIME NOT NULL DEFAULT '13:00',
    grace_period_minutes   INTEGER NOT NULL DEFAULT 10,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS system_settings_id_check;
ALTER TABLE system_settings ADD CONSTRAINT system_settings_id_check CHECK (id = 1);

ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS system_settings_grace_period_check;
ALTER TABLE system_settings ADD CONSTRAINT system_settings_grace_period_check
    CHECK (grace_period_minutes BETWEEN 0 AND 240);

DROP TRIGGER IF EXISTS trg_system_settings_updated_at ON system_settings;
CREATE TRIGGER trg_system_settings_updated_at
    BEFORE UPDATE ON system_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO system_settings (id) VALUES (1) ON CONFLICT DO NOTHING;

-- ------------------------------------------------------------
-- 5.5 attendances
--
-- 刻意不掛 updated_at 觸發器：時間一律由應用層帶入 get_virtual_now()。
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attendances (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    punch_date      DATE NOT NULL,
    punch_in_time   TIMESTAMPTZ,
    punch_out_time  TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'normal',
    work_hours      NUMERIC(5,2),
    is_early_leave  BOOLEAN NOT NULL DEFAULT false,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, punch_date)
);

ALTER TABLE attendances DROP CONSTRAINT IF EXISTS attendances_status_check;
ALTER TABLE attendances ADD CONSTRAINT attendances_status_check
    CHECK (status IN ('normal', 'late', 'absent', 'holiday_work', 'on_leave'));

CREATE INDEX IF NOT EXISTS attendances_user_date_idx
    ON attendances (user_id, punch_date DESC);

-- ------------------------------------------------------------
-- 5.6 punch_requests
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS punch_requests (
    id                   SERIAL PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_date          DATE NOT NULL,
    type                 VARCHAR(10) NOT NULL,
    requested_in_time    TIMESTAMPTZ,
    requested_out_time   TIMESTAMPTZ,
    reason               TEXT NOT NULL,
    status               VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewer_id          INTEGER REFERENCES users(id) ON DELETE SET NULL,
    review_note          TEXT,
    reviewed_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE punch_requests DROP CONSTRAINT IF EXISTS punch_requests_type_check;
ALTER TABLE punch_requests ADD CONSTRAINT punch_requests_type_check
    CHECK (type IN ('in', 'out', 'both'));

ALTER TABLE punch_requests DROP CONSTRAINT IF EXISTS punch_requests_status_check;
ALTER TABLE punch_requests ADD CONSTRAINT punch_requests_status_check
    CHECK (status IN ('pending', 'approved', 'rejected'));

CREATE INDEX IF NOT EXISTS punch_requests_status_user_idx ON punch_requests (status, user_id);
CREATE INDEX IF NOT EXISTS punch_requests_reviewer_idx ON punch_requests (reviewer_id);

-- ------------------------------------------------------------
-- 5.7 leave_requests
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leave_requests (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    leave_type    VARCHAR(20) NOT NULL,
    start_time    TIMESTAMPTZ NOT NULL,
    end_time      TIMESTAMPTZ NOT NULL,
    hours         NUMERIC(5,2) NOT NULL,
    reason        TEXT NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewer_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    review_note   TEXT,
    reviewed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE leave_requests DROP CONSTRAINT IF EXISTS leave_requests_leave_type_check;
ALTER TABLE leave_requests ADD CONSTRAINT leave_requests_leave_type_check
    CHECK (leave_type IN ('事假', '病假', '特別休假', '公假'));

ALTER TABLE leave_requests DROP CONSTRAINT IF EXISTS leave_requests_status_check;
ALTER TABLE leave_requests ADD CONSTRAINT leave_requests_status_check
    CHECK (status IN ('pending', 'approved', 'rejected'));

CREATE INDEX IF NOT EXISTS leave_requests_status_user_idx ON leave_requests (status, user_id);
CREATE INDEX IF NOT EXISTS leave_requests_reviewer_idx ON leave_requests (reviewer_id);

-- ------------------------------------------------------------
-- 5.8 overtime_requests
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS overtime_requests (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_time    TIMESTAMPTZ NOT NULL,
    end_time      TIMESTAMPTZ NOT NULL,
    hours         NUMERIC(5,2) NOT NULL,
    reason        TEXT NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewer_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    review_note   TEXT,
    reviewed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE overtime_requests DROP CONSTRAINT IF EXISTS overtime_requests_status_check;
ALTER TABLE overtime_requests ADD CONSTRAINT overtime_requests_status_check
    CHECK (status IN ('pending', 'approved', 'rejected'));

CREATE INDEX IF NOT EXISTS overtime_requests_status_user_idx ON overtime_requests (status, user_id);
CREATE INDEX IF NOT EXISTS overtime_requests_reviewer_idx ON overtime_requests (reviewer_id);

-- ------------------------------------------------------------
-- 5.9 rooms
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rooms (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    capacity       INTEGER NOT NULL,
    location_info  VARCHAR(255),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- 5.10 room_bookings
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS room_bookings (
    id          SERIAL PRIMARY KEY,
    room_id     INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       VARCHAR(255) NOT NULL,
    start_time  TIMESTAMPTZ NOT NULL,
    end_time    TIMESTAMPTZ NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'confirmed',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE room_bookings DROP CONSTRAINT IF EXISTS room_bookings_status_check;
ALTER TABLE room_bookings ADD CONSTRAINT room_bookings_status_check
    CHECK (status IN ('confirmed', 'cancelled'));

-- 兩層防護的第二層（第一層是應用層預檢，見 backend services）。
-- 半開區間 [)：09:00–11:00 與 11:00–12:00 首尾相接不算衝突。
ALTER TABLE room_bookings DROP CONSTRAINT IF EXISTS no_double_booking;
ALTER TABLE room_bookings ADD CONSTRAINT no_double_booking
    EXCLUDE USING gist (
        room_id WITH =,
        tstzrange(start_time, end_time, '[)') WITH &&
    ) WHERE (status = 'confirmed');

CREATE INDEX IF NOT EXISTS room_bookings_room_start_idx ON room_bookings (room_id, start_time);

DROP TRIGGER IF EXISTS trg_room_bookings_updated_at ON room_bookings;
CREATE TRIGGER trg_room_bookings_updated_at
    BEFORE UPDATE ON room_bookings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- 5.11 holidays
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS holidays (
    holiday_date  DATE PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- 5.12 demo_clock（恆單列）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS demo_clock (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    real_anchor     TIMESTAMPTZ NOT NULL,
    virtual_anchor  TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE demo_clock DROP CONSTRAINT IF EXISTS demo_clock_id_check;
ALTER TABLE demo_clock ADD CONSTRAINT demo_clock_id_check CHECK (id = 1);

INSERT INTO demo_clock (id, real_anchor, virtual_anchor)
VALUES (1, now(), '2026-08-24 09:00:00+08')
ON CONFLICT DO NOTHING;
