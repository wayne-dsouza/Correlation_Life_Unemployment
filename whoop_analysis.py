"""
Starter analysis for the CSVs produced by whoop_connector.py.

Run `python whoop_connector.py` first, then `python whoop_analysis.py`
to get a daily summary table and a sleep-vs-recovery scatter plot.
"""

import pandas as pd
import matplotlib.pyplot as plt

sleep = pd.read_csv("whoop_data/sleep.csv", parse_dates=["start", "end"])
recovery = pd.read_csv("whoop_data/recovery.csv")
cycles = pd.read_csv("whoop_data/cycles.csv", parse_dates=["start"])

# Join recovery onto the sleep it was scored from, ignoring naps
sleep = sleep[~sleep["nap"]]
merged = recovery.merge(sleep, left_on="sleep_id", right_on="id", suffixes=("_recovery", "_sleep"))
merged["date"] = merged["end"].dt.date

daily = merged[[
    "date",
    "score.recovery_score",
    "score.resting_heart_rate",
    "score.hrv_rmssd_milli",
    "score.sleep_performance_percentage",
    "score.sleep_efficiency_percentage",
    "score.stage_summary.total_in_bed_time_hours",
]].rename(columns=lambda c: c.replace("score.", "").replace("stage_summary.", ""))

print(daily.to_string(index=False))
print("\nCorrelations with recovery score:")
print(daily.drop(columns="date").corr()["recovery_score"].round(2))

plt.scatter(daily["total_in_bed_time_hours"], daily["recovery_score"], alpha=0.6)
plt.xlabel("Time in Bed (hours)")
plt.ylabel("Recovery Score (%)")
plt.title("Sleep vs. Recovery")
plt.show()
