"""Train and evaluate no-show classifiers on the Kaggle Brazil dataset."""
import argparse, json
from pathlib import Path
import joblib, matplotlib.pyplot as plt, numpy as np, pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, average_precision_score,
    classification_report, confusion_matrix, f1_score, precision_recall_curve,
    precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEED = 42
NUM = ["age", "waiting_days", "scheduled_hour", "scholarship", "hypertension",
       "diabetes", "alcoholism", "handicap", "sms_received"]
CAT = ["gender", "neighbourhood", "appointment_weekday"]
FEATURES = NUM + CAT

def load_prepare(path):
    raw = pd.read_csv(path)
    required = {"Gender","ScheduledDay","AppointmentDay","Age","Neighbourhood","Scholarship",
                "Hipertension","Diabetes","Alcoholism","Handcap","SMS_received","No-show"}
    if missing := sorted(required - set(raw.columns)):
        raise ValueError(f"Missing columns: {missing}")
    d = raw.copy()
    d["ScheduledDay"] = pd.to_datetime(d.ScheduledDay, utc=True, errors="coerce")
    d["AppointmentDay"] = pd.to_datetime(d.AppointmentDay, utc=True, errors="coerce")
    d["waiting_days"] = (d.AppointmentDay.dt.normalize()-d.ScheduledDay.dt.normalize()).dt.days
    d["scheduled_hour"] = d.ScheduledDay.dt.hour
    d["appointment_weekday"] = d.AppointmentDay.dt.day_name()
    d["no_show"] = d["No-show"].map({"No":0,"Yes":1})
    d = d.rename(columns={"Age":"age","Gender":"gender","Neighbourhood":"neighbourhood",
        "Scholarship":"scholarship","Hipertension":"hypertension","Diabetes":"diabetes",
        "Alcoholism":"alcoholism","Handcap":"handicap","SMS_received":"sms_received"})
    bad_date=d[["ScheduledDay","AppointmentDay"]].isna().any(axis=1)
    bad_age=d.age.isna()|d.age.lt(0)|d.age.gt(115)
    bad_wait=d.waiting_days.isna()|d.waiting_days.lt(0)
    bad_target=d.no_show.isna(); bad=bad_date|bad_age|bad_wait|bad_target
    d=d.loc[~bad].copy(); d["handicap"]=d.handicap.gt(0).astype(int)
    d["gender"]=d.gender.map({"F":"Female","M":"Male"}).fillna("Unknown")
    d=d.sort_values(["AppointmentDay","ScheduledDay"],kind="stable").reset_index(drop=True)
    audit={"raw_rows":len(raw),"clean_rows":len(d),"removed_rows":int(bad.sum()),
      "removed_invalid_date":int(bad_date.sum()),"removed_invalid_age":int(bad_age.sum()),
      "removed_negative_wait":int(bad_wait.sum()),"duplicate_rows":int(raw.duplicated().sum()),
      "missing_values_raw":{k:int(v) for k,v in raw.isna().sum().items() if v},
      "class_counts":{str(k):int(v) for k,v in d.no_show.value_counts().sort_index().items()},
      "no_show_rate":float(d.no_show.mean()),"date_min":str(d.AppointmentDay.min().date()),
      "date_max":str(d.AppointmentDay.max().date())}
    return d,audit

def split_time(d):
    dates=np.array(sorted(d.AppointmentDay.dt.date.unique()))
    test_start=dates[int(len(dates)*.8)]; earlier=dates[dates<test_start]
    val_start=earlier[int(len(earlier)*.8)]
    tr=d[d.AppointmentDay.dt.date<val_start]
    va=d[(d.AppointmentDay.dt.date>=val_start)&(d.AppointmentDay.dt.date<test_start)]
    te=d[d.AppointmentDay.dt.date>=test_start]
    def desc(x): return {"rows":len(x),"start":str(x.AppointmentDay.min().date()),"end":str(x.AppointmentDay.max().date()),"no_show_rate":float(x.no_show.mean())}
    return tr,va,te,{"train":desc(tr),"validation":desc(va),"test":desc(te)}

def prep():
    num=Pipeline([("impute",SimpleImputer(strategy="median")),("scale",StandardScaler())])
    cat=Pipeline([("impute",SimpleImputer(strategy="most_frequent")),("onehot",OneHotEncoder(handle_unknown="ignore"))])
    return ColumnTransformer([("num",num,NUM),("cat",cat,CAT)])

def models():
    return {
      "dummy_most_frequent":Pipeline([("prep",prep()),("model",DummyClassifier(strategy="most_frequent"))]),
      "logistic_regression":Pipeline([("prep",prep()),("model",LogisticRegression(max_iter=1000,class_weight="balanced",random_state=SEED))]),
      "random_forest":Pipeline([("prep",prep()),("model",RandomForestClassifier(n_estimators=250,max_depth=14,min_samples_leaf=8,class_weight="balanced_subsample",n_jobs=-1,random_state=SEED))])}

def metrics(y,p,t=.5):
    pred=(p>=t).astype(int)
    return {"threshold":float(t),"accuracy":float(accuracy_score(y,pred)),
      "precision_no_show":float(precision_score(y,pred,zero_division=0)),
      "recall_no_show":float(recall_score(y,pred,zero_division=0)),
      "f1_no_show":float(f1_score(y,pred,zero_division=0)),"roc_auc":float(roc_auc_score(y,p)),
      "pr_auc":float(average_precision_score(y,p)),"confusion_matrix":confusion_matrix(y,pred).tolist()}

def f2_threshold(y,p):
    precision,recall,thresholds=precision_recall_curve(y,p)
    f2=5*precision[:-1]*recall[:-1]/np.maximum(4*precision[:-1]+recall[:-1],1e-12)
    return float(thresholds[int(np.nanargmax(f2))])

def importance(pipe):
    names=pipe.named_steps["prep"].get_feature_names_out(); model=pipe.named_steps["model"]
    vals=np.abs(model.coef_[0]) if hasattr(model,"coef_") else model.feature_importances_
    rows=[]
    for name,val in zip(names,vals):
        clean=name.split("__",1)[-1]
        source=next((c for c in CAT if clean==c or clean.startswith(c+"_")),clean)
        rows.append((source,float(val)))
    return pd.DataFrame(rows,columns=["feature","importance"]).groupby("feature",as_index=False).importance.sum().sort_values("importance",ascending=False)

def plots(d,out,y,pred):
    fig,ax=plt.subplots(1,3,figsize=(14,4))
    d.no_show.value_counts().sort_index().rename({0:"Attended",1:"No-show"}).plot.bar(ax=ax[0],color=["#3977a8","#d66745"]); ax[0].set_title("Target distribution"); ax[0].tick_params(axis="x",rotation=0)
    q=d.assign(wait_bin=pd.cut(d.waiting_days,[-1,0,3,7,14,30,np.inf],labels=["0","1–3","4–7","8–14","15–30","31+"]))
    q.groupby("wait_bin",observed=False).no_show.mean().plot.bar(ax=ax[1],color="#d66745"); ax[1].set_title("No-show rate by waiting days"); ax[1].tick_params(axis="x",rotation=0)
    d.groupby("appointment_weekday").no_show.mean().reindex(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]).dropna().plot.bar(ax=ax[2],color="#5f9e6e"); ax[2].set_title("No-show rate by weekday"); ax[2].tick_params(axis="x",rotation=35)
    fig.tight_layout(); fig.savefig(out/"eda.png",dpi=160); plt.close(fig)
    ConfusionMatrixDisplay.from_predictions(y,pred,display_labels=["Attended","No-show"],cmap="Blues"); plt.title("Chronological test set"); plt.tight_layout(); plt.savefig(out/"confusion_matrix.png",dpi=160); plt.close()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default="data/noshowappointments.csv"); ap.add_argument("--output",default="artifacts"); a=ap.parse_args()
    out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
    d,audit=load_prepare(a.data); tr,va,te,split=split_time(d)
    fitted={}; comparison={}
    for name,pipe in models().items():
        pipe.fit(tr[FEATURES],tr.no_show); p=pipe.predict_proba(va[FEATURES])[:,1]
        comparison[name]=metrics(va.no_show,p); fitted[name]=pipe
    selected=max((n for n in comparison if not n.startswith("dummy")),key=lambda n:comparison[n]["pr_auc"])
    threshold=f2_threshold(va.no_show,fitted[selected].predict_proba(va[FEATURES])[:,1])
    final=clone(models()[selected]).fit(pd.concat([tr[FEATURES],va[FEATURES]]),pd.concat([tr.no_show,va.no_show]))
    prob=final.predict_proba(te[FEATURES])[:,1]; pred=(prob>=threshold).astype(int); test=metrics(te.no_show,prob,threshold)
    imp=importance(final); imp.to_csv(out/"feature_importance.csv",index=False)
    idx=[0,len(te)//2,len(te)-1]; ex=te[FEATURES].iloc[idx].copy(); ex["actual_no_show"]=te.no_show.iloc[idx].to_numpy(); ex["predicted_probability"]=prob[idx]; ex["predicted_no_show"]=pred[idx]; ex.to_csv(out/"example_predictions.csv",index=False)
    result={"data_audit":audit,"temporal_split":split,"validation_model_comparison_at_0.5":comparison,
      "selection_rule":"Highest validation PR-AUC excluding dummy baseline","selected_model":selected,
      "threshold_rule":"Validation threshold maximizing F2 (recall weighted 2x)","selected_threshold":threshold,
      "untouched_test_metrics":test,"test_classification_report":classification_report(te.no_show,pred,target_names=["attended","no_show"],output_dict=True,zero_division=0),
      "top_features":imp.head(10).to_dict("records")}
    (out/"metrics.json").write_text(json.dumps(result,indent=2)); joblib.dump({"pipeline":final,"threshold":threshold,"features":FEATURES},out/"model.joblib")
    plots(d,out,te.no_show,pred); print(json.dumps(result,indent=2))

if __name__=="__main__": main()
