# Power BI — design & build guide

> Power BI model and report working plan.
> Follow this in Power BI Desktop, then publish to Power BI Services.

---

## 1. What is being built and why (PL-300 "Model the data" mapping)

`data/transit_history.csv` is one row per observed departure:

| Column      | Type     | Meaning                                          |
| ----------- | -------- | ------------------------------------------------ |
| `Timestamp` | dateTime | when the departure was observed (UTC)            |
| `Line`      | text     | line label (U8, S9, M1, …)                       |
| `Direction` | text     | terminus / destination                           |
| `DelaySec`  | int      | delay in seconds (0 = on time, negative = early) |

The dashboard answers four questions, each mapped to a measure:

| Question                         | Measure                                   |
| -------------------------------- | ----------------------------------------- |
| Which line ruins my commute?     | `Avg Delay (Mins)` by `Line`              |
| When is it worst?                | `Avg Delay (Mins)` by `Hour` / `RushHour` |
| Is today worse than normal?      | `Delay vs City Average`                   |
| Which direction is the friction? | `On-Time %` by `Direction`                |

| Skill                                     | Where it's shown |
| ----------------------------------------- | ---------------- |
| Star vs. snowflake schema                 | §2.1             |
| Calculated columns vs. measures           | §2.2             |
| Measures table                            | §2.3             |
| DAX (`CALCULATE`, `ALL`, `DIVIDE`, `VAR`) | §3.3             |
| Format strings                            | §3.3             |
| Sort-by column                            | §3.2             |
| Create a common date table                | §3.4             |
| Time intelligence measures (`DATEADD`)    | §3.4             |
| Relationships (fact → date)               | existing model   |

---

## 2. The modeling decisions (read first)

### 2.1 Star schema

- **Fact:** `transit_history` (the departures).
- **Dimension:** `Date` — an explicit date table (see §3.4), replacing the auto date table; enables time intelligence (year/quarter/month/day).

`Line`, `Direction`, `Hour`, `RushHour`, `DayType`, `DelayBucket` are **low-cardinality descriptive attributes** kept on the fact as _degenerate dimensions_ — the right call when a "dimension" is just a label with no other attributes. A separate 24-row `Time` table is a valid upgrade, but it adds a join for no analytical gain here; we deliberately keep the model small and readable.

### 2.2 Measures vs. calculated columns (the core PL-300 distinction)

- **Calculated column** — computed _per row_ in _row context_, stored at refresh. Use for attributes you slice/filter by.
- **Measure** — computed _on demand_ in _filter context_, never stored. Use for anything you aggregate.

So `Hour`, `RushHour`, `DayType`, `DelayBucket` are **columns** (they describe each row and go on axes/legends/filters); `Total Departures`, `Avg Delay (Mins)`, `On-Time %` are **measures** (they aggregate rows).

### 2.3 The measures table

All measures live in one table called `Measures` (no columns).
One home for all measures = maintainable, discoverable, and a clean signal in Model view.

### 2.4 Format strings & sort-by

- Percentages → `0.0%`; minutes → `0.0`; counts → `#,##0`; "vs city average" → signed `+0.0;-0.0;0.0`.
- Text buckets (`Anticipated`/`On time`/`Late`/`Very late`, `Rush hour`/`Off-peak`) get a **sort-by column** so they sort logically, never alphabetically.

---

## 3. Step-by-step in Power BI Desktop

### 3.1 Create the `Measures` table

1. **Home** → **Enter data**.
2. Click **Load** (accept the empty table). A table named `Table` appears.
3. In the **Fields** pane, right-click it → **Rename** → `Measures`.
4. Right-click its leftover `Column1` → **Delete column**. The table now has no columns.
   - _(Alt: **Modeling** → **New table** → `Measures = {BLANK()}`, then hide the `[Value]` column.)_

### 3.2 Add the calculated columns (on `transit_history`)

Select `transit_history`, then **Table tools** → **New column**. Enter each expression, set its **data type**, and where noted its **sort-by** via **Column tools → Sort by column**.

| Column            | DAX                                                                                                                                                                   | Data type    | Sort by           |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | ----------------- |
| `Hour`            | `HOUR('transit_history'[Timestamp])`                                                                                                                                  | Whole number | —                 |
| `RushHour`        | `IF(OR(AND('transit_history'[Hour] >= 6, 'transit_history'[Hour] <= 9), AND('transit_history'[Hour] >= 15, 'transit_history'[Hour] <= 18)), "Rush hour", "Off-peak")` | Text         | `RushHourSort`    |
| `RushHourSort`    | `IF(OR(AND('transit_history'[Hour] >= 6, 'transit_history'[Hour] <= 9), AND('transit_history'[Hour] >= 15, 'transit_history'[Hour] <= 18)), 1, 2)`                    | Whole number | —                 |
| `DayType`         | `IF(WEEKDAY('transit_history'[Timestamp], 2) <= 5, "Weekday", "Weekend")`                                                                                             | Text         | `DayTypeSort`     |
| `DayTypeSort`     | `IF(WEEKDAY('transit_history'[Timestamp], 2) <= 5, 1, 2)`                                                                                                             | Whole number | —                 |
| `DelayBucket`     | `IF('transit_history' [DelaySec] = 0,"On time",IF('transit_history' [DelaySec] < 0,"Anticipated",IF('transit_history' [DelaySec] <= 300,"Late","Very late")))`        | Text         | `DelayBucketSort` |
| `DelayBucketSort` | `IF('transit_history'[DelaySec] < 0, 1, IF('transit_history'[DelaySec] = 0, 2, IF('transit_history'[DelaySec] <= 300, 3, 4)))`                                        | Whole number | —                 |

> **Sort-by (exam item):** select `DelayBucket` → **Column tools → Sort by column → DelayBucketSort** so `Anticipated / On time / Late / Very late` order correctly. Repeat for `RushHour` → `RushHourSort` and `DayType` → `DayTypeSort`.

> Bucket thresholds: Anticipated = `DelaySec < 0`, On time = `DelaySec = 0`, Late = `1–300`, Very late = `> 300` (Late/Very late boundary matches `Severe Delay %`; the `On-Time %` measure counts `DelaySec ≤ 0` as on-time).

### 3.3 Add the measures (on `Measures`)

Right-click the `Measures` table → **New measure**, type the DAX, then set the **format string** in **Measure tools → Format**.

| Measure                      | DAX                                                                                                                          | Format             |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| `Total Departures`           | `COUNTROWS('transit_history')`                                                                                               | `#,##0`            |
| `Delayed Departures`         | `CALCULATE([Total Departures], 'transit_history'[DelaySec] > 0)`                                                             | `#,##0`            |
| `On-Time Departures`         | `CALCULATE([Total Departures], 'transit_history'[DelaySec] <= 0)`                                                            | `#,##0`            |
| `Avg Delay (Sec)`            | `DIVIDE(SUM('transit_history'[DelaySec]), [Total Departures], 0)`                                                            | `0`                |
| `Avg Delay (Mins)`           | `DIVIDE([Avg Delay (Sec)], 60, 0)`                                                                                           | `0.0`              |
| `On-Time %`                  | `DIVIDE([On-Time Departures], [Total Departures], 0)`                                                                        | `0.0%`             |
| `Severe Delay %`             | `VAR Severe = CALCULATE([Total Departures], 'transit_history'[DelaySec] > 300) RETURN DIVIDE(Severe, [Total Departures], 0)` | `0.0%`             |
| `Lines Tracked`              | `DISTINCTCOUNT('transit_history'[Line])`                                                                                     | `#,##0`            |
| `Delay vs City Average`      | `VAR CityAvg = CALCULATE([Avg Delay (Mins)], ALL('transit_history')) RETURN [Avg Delay (Mins)] - CityAvg`                    | `+0.0;-0.0;0.0`    |
| `On-Time % vs City Average`  | `VAR CityPct = CALCULATE([On-Time %], ALL('transit_history')) RETURN [On-Time %] - CityPct`                                  | `+0.0%;-0.0%;0.0%` |
| `Rush-Hour Avg Delay (Mins)` | `CALCULATE([Avg Delay (Mins)], 'transit_history'[RushHour] = "Rush hour")`                                                   | `0.0`              |
| `Off-Peak Avg Delay (Mins)`  | `CALCULATE([Avg Delay (Mins)], 'transit_history'[RushHour] = "Off-peak")`                                                    | `0.0`              |
| `Rush-Hour Premium (Mins)`   | `[Rush-Hour Avg Delay (Mins)] - [Off-Peak Avg Delay (Mins)]`                                                                 | `+0.0;-0.0;0.0`    |

> `Rush-Hour Premium (Mins)` = the "story" number: rush hour minus off-peak.

### 3.4 Date table (replace the auto date table)

The model currently relies on Power BI's hidden _auto_ date table (the `LocalDateTable` in the TMDL). For the exam — "create a common date table" + "implement time intelligence measures" — replace it with an explicit, visible `Date` dimension.

1. **Modeling → New table:**
   ```dax
   Date = CALENDAR(MIN('transit_history'[Timestamp]), MAX('transit_history'[Timestamp]))
   ```
2. Select the `Date` column → **Column tools → Mark as date table → Date** (this builds the Year → Quarter → Month → Day hierarchy for you).
3. **Model view → relationship:** `transit_history[Timestamp]` → `Date[Date]`, one-to-many, single direction (replaces the auto relationship).
4. _(Optional)_ add `Weekday`/`IsWeekend` here only if you move the weekday story off the fact table; otherwise keep the `DayType` calculated column from §3.2.

**Time intelligence (one example, proves the skill):**

```dax
Avg Delay Previous Day =
CALCULATE([Avg Delay (Mins)], DATEADD('Date'[Date], -1, DAY))
```

> M alternative: build the same table in Power Query with `List.Dates` — the exam accepts either; DAX is fewer steps here. Keep it minimal: the date table + one time-intelligence measure covers both skills without bloating the model.

---

## 4. Verify & commit

Checklist before committing the PBIP:

- [ ] Model loads with no errors.
- [ ] `transit_history` shows the 7 new columns.
- [ ] `Measures` table exists with 13 measures and no columns.
- [ ] `On-Time %` returns a value in `[0,1]` (format `0.0%`).
- [ ] A table visual of `Line` + `Avg Delay (Mins)` sorts lines by delay.
- [ ] `DelayBucket` orders as `Anticipated → On time → Late → Very late` (sort-by works).
- [ ] `RushHour` shows `Rush hour` before `Off-peak`.
- [ ] `Date` is marked as date table and related to `transit_history[Timestamp]`.

Expected `.tmdl` changes after saving: a new `tables/Measures.tmdl`, new `column`/`measure` entries in `transit_history.tmdl`, and a `ref table Measures` in `model.tmdl`.

---

## 5. Dashboard storyboard & design language

Each row answers one commuter question, completing the story the dashboard tells:

- _Which line ruins my commute?_ → line ranking
- _When is it worst?_ → rush-hour curve
- _Is today worse than normal?_ → time intelligence vs. city average
- _Which direction is the friction?_ → on-time vs. late by direction

| Row                    | Content                                                 | Visual                                   |
| ---------------------- | ------------------------------------------------------- | ---------------------------------------- |
| KPI row                | Total departures, avg delay, on-time %, severe-delay %  | Cards with conditional color             |
| Story row, left (60%)  | "Rush-hour effect": avg delay by hour of day            | Line/area chart + average reference line |
| Story row, right (40%) | "Directional friction": on-time vs delayed by direction | Donut / 100% stacked bar                 |
| Category row           | "Usual suspects": avg delay per line, sorted desc       | Bar chart, green->red gradient           |
| Detail row             | Line -> Direction with volumes & reliability            | Matrix + conditional data bars           |

### Design language

Treat the dashboard like architecture (one clear idea per view, negative space, a deliberate palette) rather than decoration:

- **Identity:** Berlin transit (BVG yellow `#F0D722`) as the accent on the dark `ReportThemeDark` base.
- **Palette:** accent yellow + neutral dark slate + a green -> amber -> red gradient for `DelaySec`.
- **Type:** a single clean sans (Segoe UI / Inter / DIN-style, fitting the transit theme), 2-3 weights max.
- **Grid:** one consistent margin/column grid across all pages; each visual gets breathing room.

### Pipeline health page

A second page over `logs/runs.csv`: runs over time, ok/empty/skip split, rows-per-run, and gap detection — turning the pipeline's own reliability into a story alongside the transit data.

---

## 6. Portfolio talking points

- A deliberate **star schema**, not a flat table with measures scattered on it.
- **Measures live in one `Measures` table**; derived attributes are **calculated columns with sort-by columns**. Both demonstrate tool knowledge altogether.
- The **"vs city average"** and **"rush-hour premium"** measures demonstrate contextual thinking.

---

## 7. Security: Row-Level Security

A convincing RLS implementation needs a real "who-sees-what" boundary.
The plan is: one dimension (`Station`) segments **both** the fact (departures) and the run-log (pipeline health), so the story is coherent: _"a station operator sees only their station's departures and only their station's pipeline runs."_

1. **ETL:** add `Station` to `data/transit_history.csv` (the workflow already accepts a `station` input, so multi-station is half-built).
2. **Model:** add `Station` to `transit_history` (M query `Columns=5` + a `Station` column) and to a `runs` table over `logs/runs.csv`.
3. **RLS role** `Station Operator`, filtered on **both** tables:
   - `'transit_history'[Station] = USERPRINCIPALNAME()` (dynamic) — or a fixed value like `"Alexanderplatz"` for a static demo.
   - `'runs'[Station] = …` (same rule).
