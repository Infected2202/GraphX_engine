# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
import calendar
import hashlib
from typing import Dict, List, Tuple, Optional, Iterable

# Ключи типов смен (должны совпадать с config)
DAY_A, DAY_B = "day_a", "day_b"
NIGHT_A, NIGHT_B = "night_a", "night_b"
M8_A, M8_B = "m8_a", "m8_b"
E8_A, E8_B = "e8_a", "e8_b"
N4_A, N4_B = "n4_a", "n4_b"
N8_A, N8_B = "n8_a", "n8_b"
VAC_WD8, VAC_WE0 = "vac_wd8", "vac_we0"
OFF = "off"

@dataclass
class ShiftType:
    key: str
    code: str
    office: Optional[str]
    start: Optional[str]
    end: Optional[str]
    hours: int
    is_working: bool
    label: str

@dataclass
class Employee:
    id: str
    name: str
    is_trainee: bool = False
    mentor_id: Optional[str] = None
    ytd_overtime: int = 0
    seed4: int = 0           # фаза 0..3 (Д, Н, В, В)

@dataclass
class Assignment:
    employee_id: str
    date: date
    shift_key: str
    effective_hours: int
    source: str  # 'template' | 'autofix' | 'override'
    recolored_from_night: bool = False

class Generator:
    def __init__(self, config: Dict):
        self.cfg = config
        self.shift_types: Dict[str, ShiftType] = {
            k: ShiftType(
                key=k,
                code=v["code"],
                office=v["office"],
                start=v.get("start"),
                end=v.get("end"),
                hours=int(v["hours"]),
                is_working=bool(v["is_working"]),
                label=v["label"],
            )
            for k, v in self.cfg["shift_types"].items()
        }

    # ---------- Даты ----------
    @staticmethod
    def ym_to_year_month(ym: str) -> Tuple[int, int]:
        y, m = ym.split("-")
        return int(y), int(m)

    @staticmethod
    def month_bounds(year: int, month: int) -> Tuple[date, date]:
        first = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        last = date(year, month, last_day)
        return first, last

    @staticmethod
    def iter_month_days(year: int, month: int) -> Iterable[date]:
        d0, d1 = Generator.month_bounds(year, month)
        d = d0
        while d <= d1:
            yield d
            d += timedelta(days=1)

    # ---------- Сиды ----------
    @staticmethod
    def stable_hash_int(s: str) -> int:
        return int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16)

    def seed_employee(self, e: Employee) -> None:
        h = self.stable_hash_int(e.id)
        e.seed4 = h % 4

    # ---------- Ротация ----------
    def rotation_epoch_for(self, year: int) -> date:
        policy = self.cfg.get("rotation_epoch_policy", "new_year_reset")
        if policy == "new_year_reset":
            return date(year, 1, 1)
        # fallback: 1-е число текущего месяца
        return date(year, 1, 1)

    @staticmethod
    def phase_for_day(seed4: int, days_from_epoch: int) -> int:
        # 0: DAY, 1: NIGHT, 2: OFF, 3: OFF
        return (seed4 + days_from_epoch) % 4

    # ---------- Генерация месяца ----------
    def generate_month(self, month_spec: Dict, carry_in: Optional[List[Assignment]] = None) -> Tuple[List[Employee], Dict[date, List[Assignment]], List[Assignment]]:
        ym = month_spec["month_year"]
        y, m = self.ym_to_year_month(ym)
        first, last = self.month_bounds(y, m)
        epoch = self.rotation_epoch_for(y)
        norm = int(month_spec["norm_hours_month"]) if month_spec.get("norm_hours_month") else 0

        # Сотрудники
        employees = [
            Employee(
                id=rec["id"], name=rec["name"],
                is_trainee=bool(rec.get("is_trainee", False)),
                mentor_id=rec.get("mentor_id"),
                ytd_overtime=int(rec.get("ytd_overtime", 0)),
            )
            for rec in self.cfg["employees"]
        ]
        for e in employees:
            self.seed_employee(e)

        vacations: Dict[str, List[date]] = month_spec.get("vacations", {})
        # Инициализация расписания
        schedule: Dict[date, List[Assignment]] = {d: [] for d in self.iter_month_days(y, m)}

        # Для корректного чередования офиса считаем work_turn (кол-во рабочих выходов) ДО первого числа
        work_turn_before: Dict[str, int] = {e.id: 0 for e in employees}
        for e in employees:
            d = epoch
            while d < first:
                ph = self.phase_for_day(e.seed4, (d - epoch).days)
                if ph in (0, 1):  # DAY or NIGHT
                    work_turn_before[e.id] += 1
                d += timedelta(days=1)

        # Применяем carry-in (обычно N8* на 1-е число)
        if carry_in:
            for a in carry_in:
                if a.date in schedule:
                    schedule[a.date] = [x for x in schedule[a.date] if x.employee_id != a.employee_id]
                    schedule[a.date].append(a)
                # важно: перенос N8* НЕ увеличивает work_turn в этот день (это продолжение ночи прошлого месяца)

        # Построение шаблона по дням
        carry_out: List[Assignment] = []  # N8* на 1-е след. месяца

        for d in self.iter_month_days(y, m):
            for e in employees:
                # если на этот день уже стоит carry-in (например N8A) — пропускаем генерацию
                if any(a.employee_id == e.id for a in schedule[d]):
                    continue

                # Отпуск приоритетнее шаблона
                if d in vacations.get(e.id, []):
                    key = VAC_WD8 if d.weekday() < 5 else VAC_WE0
                    st = self.shift_types[key]
                    schedule[d].append(Assignment(e.id, d, key, st.hours, source="template"))
                    continue

                ph = self.phase_for_day(e.seed4, (d - epoch).days)

                if ph == 0:  # DAY
                    # Офис зависит от общего числа рабочих выходов ДО сегодняшнего дня
                    turn = work_turn_before[e.id]
                    key = DAY_A if (turn % 2 == 0) else DAY_B
                    st = self.shift_types[key]
                    schedule[d].append(Assignment(e.id, d, key, st.hours, source="template"))
                    work_turn_before[e.id] += 1

                elif ph == 1:  # NIGHT
                    turn = work_turn_before[e.id]
                    key = NIGHT_A if (turn % 2 == 0) else NIGHT_B
                    # Если последняя дата месяца — ставим N4* и готовим N8* в следующий месяц
                    if d == last:
                        key4 = N4_A if key == NIGHT_A else N4_B
                        st4 = self.shift_types[key4]
                        schedule[d].append(Assignment(e.id, d, key4, st4.hours, source="template"))
                        # carry-out в след. месяц: N8*
                        key8 = N8_A if key == NIGHT_A else N8_B
                        st8 = self.shift_types[key8]
                        carry_out.append(Assignment(e.id, date(last.year + (1 if last.month == 12 else 0), (1 if last.month == 12 else last.month + 1), 1), key8, st8.hours, source="template"))
                    else:
                        st = self.shift_types[key]
                        schedule[d].append(Assignment(e.id, d, key, st.hours, source="template"))
                    work_turn_before[e.id] += 1

                else:  # OFF
                    st = self.shift_types[OFF]
                    schedule[d].append(Assignment(e.id, d, OFF, st.hours, source="template"))

        # Управление перелимитом часов (короткие смены, приоритет в выходные)
        self.enforce_hours_caps(employees, schedule, norm)

        return employees, schedule, carry_out

    # ---------- Ограничение часов (M8/E8 с приоритетом выходных) ----------
    def enforce_hours_caps(self, employees: List[Employee], schedule: Dict[date, List[Assignment]], norm_month: int):
        monthly_cap = norm_month + int(self.cfg.get("monthly_overtime_max", 0))
        yearly_cap = int(self.cfg.get("yearly_overtime_max", 0))

        def month_hours(eid: str) -> int:
            return sum(r.effective_hours for rows in schedule.values() for r in rows if r.employee_id == eid)

        def yearly_ok(e: Employee, after_hours: int) -> bool:
            overtime = max(0, after_hours - norm_month)
            return (e.ytd_overtime + overtime) <= yearly_cap

        # Сопоставление DAY→короткая (выходные — вечер E8*, будни — утро M8*)
        def short_key_for(dd: date, day_key: str) -> Optional[str]:
            is_weekend = dd.weekday() >= 5
            if day_key == DAY_A:
                return E8_A if is_weekend else M8_A
            if day_key == DAY_B:
                return E8_B if is_weekend else M8_B
            return None

        for e in employees:
            cur = month_hours(e.id)
            if cur <= monthly_cap and yearly_ok(e, cur):
                continue
            # Сначала рассматриваем выходные
            candidates: List[Tuple[date, Assignment]] = []
            for dd in sorted(schedule.keys(), key=lambda x: (x.weekday() < 5, x)):  # выходные сначала
                for rr in schedule[dd]:
                    if rr.employee_id == e.id and rr.shift_key in (DAY_A, DAY_B):
                        candidates.append((dd, rr))
            for dd, rr in candidates:
                skey = short_key_for(dd, rr.shift_key)
                if not skey:
                    continue
                st = self.shift_types[skey]
                rr.shift_key = skey
                rr.effective_hours = st.hours
                rr.source = rr.source if rr.source != "template" else "autofix"
                cur = month_hours(e.id)
                if cur <= monthly_cap and yearly_ok(e, cur):
                    break

    # ---------- Вспомогательное: коды смен ----------
    def code_of(self, shift_key: str) -> str:
        return self.shift_types[shift_key].code