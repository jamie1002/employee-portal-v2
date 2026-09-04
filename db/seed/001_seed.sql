-- ============================================================
-- 001_seed.sql — 靜態參考資料
--
-- 由 backend/app/db_scripts/seed.py 在 TRUNCATE 全部業務資料表之後執行，
-- 因此本檔可放心用 INSERT（不需要 ON CONFLICT）。
--
-- 日期一律相對於 DATE '2026-08-24'（虛擬時鐘的重置起點），不用 CURRENT_DATE
-- （見 docs/PITFALLS.md E2）。出勤／請假／加班的示範資料留給對應批次補上
-- （届時要呼叫正式業務函式算出符合規則的時刻，見 docs/PITFALLS.md E1），
-- 這裡只放部門、使用者、場地、國定假日、系統設定、虛擬時鐘等不受業務規則
-- 制約的靜態資料。
-- ============================================================

-- 恆單列的設定表：TRUNCATE 後需要重新插入預設列。
INSERT INTO system_settings (id, work_start_time, work_end_time, lunch_start_time, lunch_end_time, grace_period_minutes)
VALUES (1, '09:00', '18:00', '12:00', '13:00', 10);

INSERT INTO demo_clock (id, real_anchor, virtual_anchor)
VALUES (1, now(), '2026-08-24 09:00:00+08');

-- ------------------------------------------------------------
-- 部門
-- ------------------------------------------------------------
INSERT INTO departments (id, name) VALUES
    (1, '研發部'),
    (2, '業務部'),
    (3, '人資部');

-- ------------------------------------------------------------
-- 使用者（展示密碼一律為 Demo1234，bcrypt rounds=10）
-- ------------------------------------------------------------
INSERT INTO users (id, name, email, password_hash, role, department_id, is_first_login, hire_date, extension_number, employee_no) VALUES
    (1, '系統管理者',  'admin@demo.com',    '$2b$10$VBS9ELfScrrdeqcK8FDfAOh8fFFO4SgJaWNpc66EWLLnAOk9XSEr6', 'admin',    NULL, false, '2019-03-01', '100', 'EMP2019001'),
    (2, '王小明',      'manager@demo.com',  '$2b$10$VBS9ELfScrrdeqcK8FDfAOh8fFFO4SgJaWNpc66EWLLnAOk9XSEr6', 'manager',  1,    false, '2020-06-15', '201', 'EMP2020001'),
    (3, '陳小華',      'employee@demo.com', '$2b$10$VBS9ELfScrrdeqcK8FDfAOh8fFFO4SgJaWNpc66EWLLnAOk9XSEr6', 'employee', 1,    false, '2025-09-01', '202', 'EMP2025001'),
    (4, '林小美',      'lin@demo.com',      '$2b$10$VBS9ELfScrrdeqcK8FDfAOh8fFFO4SgJaWNpc66EWLLnAOk9XSEr6', 'manager',  2,    false, '2021-01-10', '301', 'EMP2021001'),
    (5, '張大同',      'chang@demo.com',    '$2b$10$VBS9ELfScrrdeqcK8FDfAOh8fFFO4SgJaWNpc66EWLLnAOk9XSEr6', 'employee', 2,    false, '2023-04-20', '302', 'EMP2023001'),
    (6, '李小芳',      'li@demo.com',       '$2b$10$VBS9ELfScrrdeqcK8FDfAOh8fFFO4SgJaWNpc66EWLLnAOk9XSEr6', 'employee', 3,    false, '2026-06-01', '401', 'EMP2026001');

SELECT setval('employee_no_seq', 6, true);

UPDATE departments SET manager_id = 2 WHERE id = 1;
UPDATE departments SET manager_id = 4 WHERE id = 2;

SELECT setval('departments_id_seq', 3, true);
SELECT setval('users_id_seq', 6, true);

-- ------------------------------------------------------------
-- 細粒度權限下放示範：李小芳（一般員工）被 admin 授予國定假日管理權限，
-- 讓「額外權限」欄與 hasAccess() 有非空資料可展示。
-- ------------------------------------------------------------
INSERT INTO user_permissions (user_id, permission, granted_by, granted_at) VALUES
    (6, 'holidays.manage', 1, '2026-08-20 10:00:00+08');

-- ------------------------------------------------------------
-- 場地
-- ------------------------------------------------------------
INSERT INTO rooms (id, name, capacity, location_info) VALUES
    (1, '會議室 A', 8,  '3F 靠窗'),
    (2, '會議室 B', 4,  '3F 電梯旁'),
    (3, '教育訓練室', 20, '5F');

SELECT setval('rooms_id_seq', 3, true);

-- ------------------------------------------------------------
-- 國定假日（2026 全年，供假別頁與行事曆展示；不落在虛擬時鐘展示視窗內也無妨，
-- 該視窗本來就不含任何真實國定假日）
-- ------------------------------------------------------------
INSERT INTO holidays (holiday_date, name) VALUES
    ('2026-01-01', '元旦'),
    ('2026-02-16', '除夕'),
    ('2026-02-17', '春節'),
    ('2026-02-18', '春節'),
    ('2026-02-19', '春節'),
    ('2026-02-27', '和平紀念日'),
    ('2026-04-04', '兒童節'),
    ('2026-04-05', '清明節'),
    ('2026-05-01', '勞動節'),
    ('2026-06-19', '端午節'),
    ('2026-09-25', '中秋節'),
    ('2026-10-10', '國慶日');
