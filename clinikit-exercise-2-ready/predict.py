"""Predict one appointment from a JSON object."""
import argparse,json,joblib,pandas as pd
ap=argparse.ArgumentParser(); ap.add_argument("--model",default="artifacts/model.joblib"); ap.add_argument("--json",required=True); a=ap.parse_args()
b=joblib.load(a.model); row=pd.DataFrame([json.loads(a.json)]); missing=sorted(set(b["features"])-set(row.columns))
if missing: raise SystemExit(f"Missing fields: {missing}")
p=float(b["pipeline"].predict_proba(row[b["features"]])[:,1][0])
print(json.dumps({"no_show_probability":round(p,4),"predicted_no_show":int(p>=b["threshold"]),"threshold":round(b["threshold"],4)},indent=2))
