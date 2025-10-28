# GraphX Web MVP — перенос генератора в локальное Flask-приложение

Это **живой документ**. Разделы `Progress`, `Surprises & Discoveries`, `Decision Log` и `Outcomes & Retrospective` необходимо поддерживать в актуальном состоянии в ходе работ.

Если этот файл находится в корне репозитория, он — единственный источник правды о ходе и решениях по этому эпик-переходу. Исполнитель (человек или агент) может реализовать всё, имея **только** текущую рабочую копию репозитория и этот PLANS.md. Внешний контекст не требуется.

## Purpose / Big Picture

Цель: перенести текущий генератор графиков из `GraphX_engine` в простой локальный **однопользовательский** веб-интерфейс на **Flask + SQLite**, без сборки фронтенда.
Пользователь сможет:

* Открыть веб-страницу `http://127.0.0.1:5000/`, выбрать месяц, **сгенерировать** сетку смен (алгоритм использует **предыдущий календарный месяц**, а не `prev_tail_by_emp`) и увидеть результат в виде интерактивной таблицы.
* Редактировать ячейки (в т.ч. мультивыделение и «сдвиг фазы») в **черновике**, затем применить изменения в базу.
* Управлять справочниками: сотрудники (CRUD + импорт JSON), календарь (праздники/рабочие выходные/норма часов/отпуска), типы смен (легенда/цвета) и настройки (settings.json).
* Экспортировать отчёт в XLSX и просматривать встроенные метрики.

**Критерий наблюдаемого результата (E2E):** запуск `flask run` → переход в `/editor?month=YYYY-MM` → кнопка **Generate** строит сетку; правки в ячейках накапливаются в черновике; **Commit** применяет; **Export XLSX** скачивает файл.

## Progress

Отмечайте реальное состояние с таймштампами (UTC-формат или локальный с TZ). Любая остановка — запись в прогресс. Разбивайте частично выполненные задачи.

* [ ] (2025-10-27) Создан Flask-каркас, блюпринты и базовые шаблоны.
* [ ] (2025-10-27) Миграция SQLite + сиды синтетических данных.
* [ ] (2025-10-27) `generator_adapter.generate_schedule()` возвращает матрицу без записи на диск.
* [ ] (2025-10-27) `/editor` read-only: отрисовка сетки месяца из БД.
* [ ] (2025-10-27) Черновик правок (`draft_edits`) + commit в `schedule_cells`.
* [ ] (2025-10-27) Экспорт XLSX как скачиваемый файл.
* [ ] (2025-10-27) Employees CRUD + импорт JSON.
* [ ] (2025-10-27) Календарь (праздники/норма/отпуска) + импорт JSON.
* [ ] (2025-10-27) Редактор `shift_types.json` и `settings.json`.
* [ ] (2025-10-27) Базовые отчёты/метрики.
* [ ] (2025-10-27) Тест-проход E2E и документация по запуску.

## Surprises & Discoveries

Отмечайте неожиданные эффекты (производительность, побочные условия, ошибки), приводите короткие доказательства (лог/вывод/скрин).

* Observation: …
  Evidence: …

## Decision Log

Фиксируйте существенные решения и аргументацию.

* Decision: Храним легенду/цвета в `configs/shift_types.json`, глобальные параметры — в `configs/settings.json`; в БД — только фактические данные (сетка/календарь/отпуска/сотрудники).
  Rationale: проще редактировать и версионировать, не смешиваем визуальные настройки с данными.
  Date/Author: 2025-10-27 GraphX

* Decision: Не используем тяжёлый фронтенд; минимальный JS (HTMX/Alpine) и Jinja.
  Rationale: оффлайн, однопользовательское; скорость поставки MVP.
  Date/Author: 2025-10-27 GraphX

* Decision: Генерация всегда опирается на **предыдущий месяц**, `prev_tail_by_emp` не используется.
  Rationale: обновлённая бизнес-правка.
  Date/Author: 2025-10-27 GraphX

## Outcomes & Retrospective

По завершении основных вех: что сделано, что осталось, уроки.

## Context and Orientation

**Исходный репозиторий:** `Infected2202/GraphX_engine` (Python). В нём реализованы ядро генерации, отчёты и стили xlsx. Этот план не полагается на отдельные внешние документы и содержит все нужные инструкции для MVP. ([GitHub][2])

**Термины:**

* **Сетка** — таблица «сотрудники × дни месяца», значение ячейки — ключ смены (DA/NB/…, либо OFF) + офис/вариант (например, NA/NB).
* **Черновик** — временное хранилище правок, применяемое одной транзакцией.
* **Легенда** — соответствие ключей смен визуальным стилям (цвет, подпись), влияет на отрисовку.
* **Отчёты** — метрики/сводные таблицы, формируемые из текущей сетки.

**Пользовательские сценарии:**

* Просмотр/генерация за выбранный `YYYY-MM`.
* Редактирование ячеек (одиночное/мульти/сдвиг фазы) → `Commit`.
* Управление справочниками и настройками.
* Экспорт XLSX.

## Plan of Work

Ниже — последовательность изменений по файлам/каталогам. Все пути даны относительно корня репозитория.

1. **Структура проекта (новые директории)**

* `graphx_web/app.py` — `create_app()`, регистрация блюпринтов.
* `graphx_web/blueprints/{editor,employees,calendar,shifts,reports,settings}/routes.py`
* `graphx_web/services/{generator_adapter.py,schedule_service.py,reports_service.py}`
* `graphx_web/dao/{db.py,employees_dao.py,schedule_dao.py,draft_dao.py,calendar_dao.py,settings_dao.py}`
* `graphx_web/templates/_layout.html` и по разделам.
* `graphx_web/static/{css/app.css,js/*.js,vendor/{htmx.min.js,alpine.min.js}}`
* `graphx_web/configs/{settings.json,shift_types.json}`
* `graphx_web/migrations/0001_init.sql`
* `graphx_web/seeds/{seed.sql,*.json}`
* `requirements.txt` (добавить Flask, openpyxl/xlsxwriter при необходимости, sqlite3 встроен).
* `run.py` — точка входа (опционально) для `flask run`.

2. **БД и миграции**

Создать схему (в `migrations/0001_init.sql`):

* `employees(id INTEGER PK, fio TEXT, key TEXT, office TEXT, attrs_json TEXT, is_active INTEGER)`
* `months(id INTEGER PK, ym TEXT UNIQUE)` — `ym` вида `YYYY-MM`.
* `schedule_cells(id INTEGER PK, month_id INTEGER, emp_id INTEGER, day INTEGER, value TEXT, office TEXT, meta_json TEXT)`
* `draft_edits(id INTEGER PK, month_id INTEGER, emp_id INTEGER, day INTEGER, new_value TEXT, new_office TEXT, op TEXT, created_at TEXT)`
* `calendar_days(id INTEGER PK, date TEXT UNIQUE, day_type TEXT, norm_minutes INTEGER)`
* `vacations(id INTEGER PK, emp_id INTEGER, start_date TEXT, end_date TEXT, kind TEXT)`
* `reports(id INTEGER PK, month_id INTEGER, name TEXT, payload_json TEXT, created_at TEXT)`
* `settings(id INTEGER PK, payload_json TEXT)` — одна запись (id=1).

3. **Адаптер генератора**

`graphx_web/services/generator_adapter.py`:

* Ввести чистую функцию:

  * `generate_schedule(month: date, *, employees, calendar, settings, shift_types) -> GeneratedSchedule`

  Возвращает матрицу ячеек + метрики **без записи на диск**.

* Адаптировать текущие функции ядра, убрать зависимость от CLI/файлового вывода; рендер XLSX — функция, принимающая матрицу и возвращающая `BytesIO`.

4. **API и страницы**

* `/editor` — Jinja-страница с сеткой (похожей на xlsx-отчёт).
* JSON-эндпоинты:

  * `GET /api/schedule?month=YYYY-MM` — JSON матрицы.
  * `POST /api/schedule/generate?month=YYYY-MM` — прогон генератора (используя **предыдущий** календарный месяц как контекст алгоритма).
  * `POST /api/schedule/draft` — `{ edits: [{emp_id,day,op,new_value,new_office,delta?}] }`.
  * `POST /api/schedule/commit` — применить черновик транзакцией.
* Справочники:

  * `GET/POST/PUT/DELETE /api/employees`, `POST /api/employees/import`.
  * `GET/POST /api/calendar?year=YYYY`, `POST /api/calendar/import`, `POST /api/vacations`.
  * `GET/POST /api/shift-types` (чтение/запись `configs/shift_types.json`).
  * `GET/POST /api/settings` (чтение/запись `configs/settings.json`).
* Отчёты:

  * `GET /reports?month=YYYY-MM` — список.
  * `GET /api/reports/<name>?month=YYYY-MM` — JSON/CSV/XLSX.
* Экспорт:

  * `GET /api/export/xlsx?month=YYYY-MM` — скачиваемый файл из `BytesIO`.

5. **UI детали**

* Сайдбар: `Editor`, `Employees`, `Calendar`, `Shift Types`, `Reports`, `Settings`.
* Таблица в `Editor`: рендер классов ячеек из `shift_types.json` (например, `.cell-DA.NB`).
* Мультивыделение и «сдвиг фазы» — на клиенте формируются батчи правок, отправляются `POST /api/schedule/draft`.

6. **Сиды и демо-месяц**

* При первом запуске: заполнить `employees`, `calendar_days`, добавить демо-месяц в `months` и набор `schedule_cells` (упрощённый) — для read-only отображения до первой генерации.

## Concrete Steps

Все команды исполняются из корня репозитория.

1. Подготовка окружения

   python -m venv .venv
   . .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -U pip
   pip install -r requirements.txt

2. Инициализация БД

   python -c "from graphx_web.dao.db import init_db; init_db()"
   python -c "from graphx_web.dao.db import seed_demo; seed_demo()"

Ожидаемый вывод (кратко):

```
Applied migration 0001_init.sql
Seeded employees: N
Seeded calendar_days: 365
Seeded demo month: YYYY-MM
```

3) Запуск приложения

```
export FLASK_APP=graphx_web.app:create_app
flask run
```

Ожидаем: сервер слушает `http://127.0.0.1:5000/`. Переход на `/editor?month=YYYY-MM` показывает сетку (read-only до первой генерации).

4. Генерация месяца

На странице `Editor` нажать **Generate**. Сервер вызывает `generator_adapter.generate_schedule()` и сохраняет матрицу в `schedule_cells`. Сетка обновится без перезагрузки (HTMX).

5. Черновик → Коммит

Выделить ячейки, сменить значение/«сдвинуть фазу», отправить **Commit**. Ожидается статус «Draft: 0 edits».

6. Экспорт XLSX

Нажать **Export XLSX**. Браузер скачает файл `graphx-YYYY-MM.xlsx`.

## Validation and Acceptance

* **Сервер доступен:** GET `/healthz` → `200 OK` и строка `OK`.
* **Генерация:** POST `/api/schedule/generate?month=YYYY-MM` → `200` и JSON с суммарной статистикой (количество ячеек/сотрудников/дней).
* **Редактирование:** после серии `POST /api/schedule/draft` — `GET /api/schedule?month=...` отражает черновик при серверном рендере; `POST /api/schedule/commit` применяет изменения, повторный `GET` показывает итог.
* **Справочники:** CRUD сотрудников и импорт JSON — изменения видны при следующем `GET /api/employees` и учитываются в генерации.
* **Календарь:** установка выходных/праздников/нормы часов влияет на алгоритм генерации (проверка: изменить день на праздник → перегенерировать месяц и сравнить значения соответствующих дней).
* **Экспорт:** скачанный XLSX открывается, стили соответствуют легенде.

## Idempotence and Recovery

* Повторный запуск миграций безопасен: `init_db()` проверяет версию схемы.
* Черновик — отдельная таблица: в случае ошибки коммита состояние основной сетки неизменно; черновик можно очистить.
* Экспорт XLSX не изменяет состояние БД.
* Конфиги (`settings.json`, `shift_types.json`) — валидируются на чтение; при ошибке возвращаем 400 с описанием полей.

## Artifacts and Notes

* Сгенерированный файл: `graphx-YYYY-MM.xlsx` (загружается из браузера).

* Пример JSON ячейки (в API):

  ```
  {"emp_id": 1, "day": 5, "value": "DA", "office": "NB", "meta": {"class": "cell-DA NB"}}
  ```

* Пример батча правок:

  ```
  {
    "edits": [
      {"emp_id":1,"day":5,"op":"set","new_value":"OFF"},
      {"emp_id":1,"day":6,"op":"shift_phase","delta":1}
    ]
  }
  ```

## Interfaces and Dependencies

**Python:** 3.11+
**Зависимости (requirements.txt):** Flask, Jinja2, htmx (как статик), alpine (как статик), openpyxl/xlsxwriter (под экспорт), pandas (опционально для отчётов).

**Адаптер генератора (обязательные сигнатуры):**

* `generate_schedule(month: date, *, employees: list, calendar: dict, settings: dict, shift_types: dict) -> GeneratedSchedule`
* `render_xlsx(schedule: GeneratedSchedule) -> io.BytesIO`

**DAO-контракты (минимум):**

* `schedule_dao.load_month(ym: str) -> Dict`
* `schedule_dao.save_month(ym: str, cells: List[Cell]) -> None`
* `draft_dao.append(edits: List[Edit]) -> int`
* `draft_dao.commit(month_id: int) -> int`

**HTTP API (минимум):** как описано в «API и страницы»; ответы — JSON с чёткими полями, коды 200/400/500.

**Фронт:** без сборки. Таблица — кастомный рендер с классами из легенды, либо Tabulator (одним файлом) при необходимости виртуализации.

---

# Milestones (Narrative)

**M1 — Каркас + Read-only Editor**
Собран Flask-проект, миграции/сиды, `/editor` отображает сетку за выбранный месяц из БД. Доказательство: навигация на `/editor?month=YYYY-MM` показывает таблицу.

**M2 — Генератор как библиотека**
`generator_adapter.generate_schedule()` возвращает матрицу; `/api/schedule/generate` сохраняет её в БД. Доказательство: после запроса сетка меняется.

**M3 — Черновик и коммит правок**
Добавлен `draft_edits`, батчи правок и транзакционный коммит в `schedule_cells`. Доказательство: правки отражаются после `Commit`.

**M4 — Экспорт XLSX**
Файл скачивается из браузера, стили соответствуют легенде. Доказательство: локально открыт файл, сверены цвета/подписи.

**M5 — Справочники и календари**
Employees CRUD + импорт; Calendar (праздники/норма/отпуска) + импорт. Доказательство: генерация учитывает изменения.

**M6 — Легенда и Настройки**
Редакторы `shift_types.json` и `settings.json`. Доказательство: смена цвета/подписи видна в UI, параметры влияют на генерацию.

**M7 — Отчёты и метрики**
Панель отчётов и минимум две метрики (часы по сотруднику/офису). Доказательство: видимые значения совпадают с расчётом.

---

# Notes for Agents (ExecPlans Compliance)

* Этот план самодостаточен и должен выполняться **точно по тексту**; не запрашивайте у пользователя «следующие шаги», переходите к следующей вехе и обновляйте `Progress`. Требование и скелет ExecPlans описаны в Cookbook и блоге о ExecPlans. ([cookbook.openai.com][1])

* Любые неоднозначности решайте внутри плана, фиксируя в `Decision Log`. Все изменения — атомарные, с проверяемым результатом.

---

# Changelog (for this plan)

* 2025-10-27: Initial draft for GraphX Web MVP (architecture, DB schema, endpoints, milestones).

