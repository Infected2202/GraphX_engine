INSERT OR IGNORE INTO employees (id, fio, key, office, attrs_json, is_active) VALUES
    (1, 'Анна Смирнова', 'asmirnova', 'A', '{}', 1),
    (2, 'Борис Кузнецов', 'bkuznetsov', 'B', '{}', 1),
    (3, 'Виктория Орлова', 'vorlova', 'A', '{}', 1);

INSERT OR IGNORE INTO months (id, ym) VALUES
    (1, '2025-01'),
    (2, '2025-02');

INSERT OR IGNORE INTO schedule_cells (id, month_id, emp_id, day, value, office, meta_json) VALUES
    (1, 1, 1, 1, 'DA', 'A', '{}'),
    (2, 1, 1, 2, 'DA', 'A', '{}'),
    (3, 1, 1, 3, 'OFF', NULL, '{}'),
    (4, 1, 2, 1, 'DB', 'B', '{}'),
    (5, 1, 2, 2, 'DB', 'B', '{}'),
    (6, 1, 2, 3, 'OFF', NULL, '{}'),
    (7, 1, 3, 1, 'NA', 'A', '{}'),
    (8, 1, 3, 2, 'NB', 'B', '{}'),
    (9, 1, 3, 3, 'OFF', NULL, '{}'),
    (10, 2, 1, 1, 'DA', 'A', '{}'),
    (11, 2, 2, 1, 'DB', 'B', '{}'),
    (12, 2, 3, 1, 'OFF', NULL, '{}');

INSERT OR IGNORE INTO calendar_days (id, date, day_type, norm_minutes) VALUES
    (1, '2025-01-01', 'holiday', 0),
    (2, '2025-01-02', 'workday', 480),
    (3, '2025-01-03', 'workday', 480),
    (4, '2025-02-01', 'workday', 480);

INSERT OR IGNORE INTO settings (id, payload_json) VALUES
    (1, '{"timezone": "Europe/Moscow"}');
