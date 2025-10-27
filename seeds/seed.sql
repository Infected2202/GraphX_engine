INSERT INTO employees(id, fio, emp_key, office, attrs_json, is_active) VALUES
    ('E01', 'Сотрудник 1', 'E01', 'A', '{}', 1),
    ('E02', 'Сотрудник 2', 'E02', 'B', '{}', 1),
    ('E03', 'Сотрудник 3', 'E03', 'A', '{}', 1);

INSERT INTO months(ym) VALUES ('2025-09');

INSERT INTO schedule_cells(month_id, emp_id, day, value, office, meta_json) VALUES
    (1, 'E01', 1, 'DA', 'A', '{}'),
    (1, 'E01', 2, 'NA', 'A', '{}'),
    (1, 'E01', 3, 'OFF', NULL, '{}'),
    (1, 'E01', 4, 'OFF', NULL, '{}'),
    (1, 'E01', 5, 'DB', 'B', '{}'),
    (1, 'E02', 1, 'DB', 'B', '{}'),
    (1, 'E02', 2, 'NB', 'B', '{}'),
    (1, 'E02', 3, 'OFF', NULL, '{}'),
    (1, 'E02', 4, 'OFF', NULL, '{}'),
    (1, 'E02', 5, 'DA', 'A', '{}');

INSERT INTO calendar_days(date, day_type, norm_minutes) VALUES
    ('2025-09-01', 'workday', 720),
    ('2025-09-02', 'workday', 720),
    ('2025-09-03', 'workday', 720),
    ('2025-09-07', 'weekend', 0);

INSERT INTO shift_types(key, payload_json) VALUES
    ('DA', '{"label": "Day A", "css_class": "DA", "bg_color": "#F5F5F5", "text_color": "#111"}'),
    ('DB', '{"label": "Day B", "css_class": "DB", "bg_color": "#F0F8FF", "text_color": "#111"}'),
    ('NA', '{"label": "Night A", "css_class": "NA", "bg_color": "#CCE5FF", "text_color": "#111"}'),
    ('NB', '{"label": "Night B", "css_class": "NB", "bg_color": "#CCE5FF", "text_color": "#111"}'),
    ('OFF', '{"label": "Off", "css_class": "OFF", "bg_color": "#EEE", "text_color": "#666"}');

INSERT INTO settings(id, payload_json, updated_at) VALUES
    (1, '{"coverage": {"require_day_a": 0, "require_day_b": 0}}', datetime('now'));
