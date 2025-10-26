# GraphX Engine (modular edition)

This repository contains a lightweight scheduling engine organised around explicit layers:

- **domain** – immutable data and helpers (`models`, `schedule`, `shift_types`).
- **rules** – algorithms that manipulate schedules (`rotor`, `shifts_ops`, `pairing`, `balancer`, `shortener`).
- **services** – orchestration layer with the `SchedulerService` facade and post-processing logic.
- **adapters** – integrations such as the SQLite repository and CSV/XLSX report writers.
- **scenarios** – runnable examples that wire the layers together.
- **tests** – `pytest`-based regression and behaviour tests.

## Quick start

```bash
pip install -r requirements.txt  # optional, only needed for openpyxl/PyYAML
pytest
python -m scenarios.run_scenario
```

The sample scenario reads `scenarios/configs/sample.json`, generates a monthly schedule, persists it to SQLite and exports reports to the `reports/` directory.
