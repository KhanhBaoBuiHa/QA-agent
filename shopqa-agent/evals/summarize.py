import pandas as pd

df = pd.read_csv("evals/results/runs.csv")
df["api_error"] = df["status"].astype(str).str.startswith("error")
ok = df[~df["api_error"]].copy()          # bỏ lần chạy lỗi API/quota khỏi mẫu số

for c in ["detected", "false_alarm"]:
    ok[c] = ok[c].astype(str).str.lower().eq("true")

def summarize(g):
    n = len(g)
    return pd.Series({
        "runs": n,
        "avg_tests": round(g["n_tests"].mean(), 1),
        "detected": f"{g['detected'].sum()}/{n}",
        "false_alarm": f"{g['false_alarm'].sum()}/{n}",
    })

print(ok.groupby(["variant", "mode"]).apply(summarize).to_string())
print("\nLần lỗi API (loại khỏi thống kê):", int(df["api_error"].sum()), "/", len(df))