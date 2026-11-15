# Demo run results

```text
NeuroHive 1.0 v1.0.0 | experimental intensity: 35%
========================================================================
STATUS: SUCCESS
Simulation ticks: 41
Replications: 2/2
Commissioned hives: NH-A, NH-B, NH-C
Recoverable faults: 1

MATERIAL BALANCE
  aluminium      used= 68 remaining= 12
  polymer        used= 14 remaining=  6
  copper         used= 22 remaining= 18
  electronics    used= 18 remaining= 10
  motors         used=  8 remaining=  2
  battery        used=  2 remaining=  1

AGENT UTILISATION
  FAB-01  fabricator   tasks= 6 busy_ticks= 18
  FAB-02  fabricator   tasks= 6 busy_ticks= 21
  SYS-01  systems      tasks= 8 busy_ticks= 24
  ASM-01  assembler    tasks= 2 busy_ticks= 10
  ASM-02  assembler    tasks= 0 busy_ticks=  0
  QA-01   inspector    tasks= 4 busy_ticks= 10

Note: simulated outputs are model results, not physical validation.

JSON report written to: /mnt/data/NeuroHive_1_0/demo_run.json
```

The full machine-readable event trace is in `demo_run.json`.
