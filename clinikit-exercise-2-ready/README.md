# CliniKit AI Trainee Assessment — Exercise 2

This project predicts whether a patient will miss an appointment (`no_show=1`).
It uses the public **Medical Appointment No Shows** dataset: 110,527 appointments
from Brazil. CliniKit did not supply a dataset, so this substitution is stated
explicitly. Results describe this historical dataset and are not clinical claims.

## Run

Python 3.10 or newer:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python download_data.py
python train.py
python -m unittest discover -s tests -v
#predict:
python predict.py --json "{\"age\":35,\"waiting_days\":14,\"scheduled_hour\":10,\"scholarship\":0,\"hypertension\":0,\"diabetes\":0,\"alcoholism\":0,\"handicap\":0,\"sms_received\":1,\"gender\":\"Female\",\"neighbourhood\":\"CENTRO\",\"appointment_weekday\":\"Monday\"}"
```

`download_data.py` uses KaggleHub and may ask you to authenticate with Kaggle.
Alternatively, download the CSV from the dataset page, rename it
`noshowappointments.csv`, and place it in `data/`. The CSV is excluded from Git.

## Data source and license

- [Kaggle dataset: Medical Appointment No Shows](https://www.kaggle.com/datasets/joniarroba/noshowappointments)
- Owner shown by Kaggle: JoniHoppen; Kaggle metadata credits Joni Hoppen and
  Aquarela Analytics.
- Kaggle API metadata reports **CC BY-NC-SA 4.0**. Follow the dataset page and
  [license conditions](https://creativecommons.org/licenses/by-nc-sa/4.0/).
- The dataset contains 14 columns and 110,527 appointment records. A public
  [data dictionary](https://rkabacoff.github.io/qacData/reference/appointments.html)
  documents the same row count, variables, source, and target values.

The raw data contains old identifiers. This project drops `PatientId` and
`AppointmentID` before modelling and does not commit the CSV or print identifiers.

## Exploration and preparation

The training run found:

| Check | Result |
|---|---:|
| Raw rows | 110,527 |
| Clean rows | 110,521 |
| Duplicated complete rows | 0 |
| Missing values | 0 |
| Attended (`0`) | 88,207 |
| No-show (`1`) | 22,314 (20.19%) |
| Invalid age removed | 1 |
| Negative waiting time removed | 5 |

`ScheduledDay` and `AppointmentDay` are converted to datetimes. The code derives:

- `waiting_days`: days from scheduling to appointment;
- `scheduled_hour`: hour at which the appointment was scheduled;
- `appointment_weekday`: weekday of the appointment.

The recorded appointment time is midnight for the data, so it cannot represent
the actual appointment hour. The model does not pretend otherwise. `Handcap`
values above zero become a single `handicap` indicator. Numeric features are
median-imputed and standardized; categorical features are imputed and one-hot
encoded inside a scikit-learn pipeline. The current data has no missing values,
but the pipeline can accept missing input later.

Identifiers and raw timestamps are excluded. `Neighbourhood` is used as the
appointment location. Its patterns may not transfer to another clinic and must
be re-evaluated before deployment.

## Split and model selection

A random split can make future prediction look easier and mixes appointments
from the same dates across train and test. This project uses appointment dates:

| Split | Dates | Rows | No-show rate |
|---|---|---:|---:|
| Train | 2016-04-29 to 2016-05-19 | 63,532 | 20.95% |
| Validation | 2016-05-20 to 2016-05-31 | 20,539 | 20.08% |
| Test | 2016-06-01 to 2016-06-08 | 26,450 | 18.46% |

Three models are compared at threshold 0.5 on validation data:

| Model | Accuracy | Precision (no-show) | Recall (no-show) | F1 | ROC-AUC | PR-AUC |
|---|---:|---:|---:|---:|---:|---:|
| Dummy majority | 0.799 | 0.000 | 0.000 | 0.000 | 0.500 | 0.201 |
| Logistic regression | 0.614 | 0.300 | 0.695 | 0.419 | 0.679 | 0.301 |
| Random forest | 0.575 | 0.303 | 0.860 | 0.448 | 0.729 | 0.338 |

The random forest is selected because it has the highest validation PR-AUC.
It captures non-linear relationships while remaining practical on this tabular
dataset. Logistic regression remains a useful, more interpretable comparison.

The threshold is selected on validation data to maximize F2. F2 gives recall
twice the weight of precision because a cheap reminder can be sent to a broad
risk group and missing a likely no-show loses the intervention opportunity.
This business assumption must be changed if outreach is expensive or intrusive.

## Untouched test results

At the validation-selected threshold `0.3376`:

| Metric | Test result |
|---|---:|
| Accuracy | 0.497 |
| Precision for no-show | 0.260 |
| Recall for no-show | 0.937 |
| F1 for no-show | 0.407 |
| ROC-AUC | 0.720 |
| PR-AUC | 0.320 |

Confusion matrix (`[[TN, FP], [FN, TP]]`):

```text
[[8569, 12999],
 [ 308,  4574]]
```

The model detects 4,574 of 4,882 missed appointments, but it also flags 12,999
appointments that were attended. This is a high-recall screening policy with a
large outreach workload. The 79.9% validation accuracy of the dummy model is
misleading because it predicts every patient will attend and catches zero
no-shows. PR-AUC is useful because the positive class is uncommon; ROC-AUC
measures ranking across thresholds; precision and recall describe operational
costs at the chosen threshold.

These results are moderate and credible for the available fields. They should
not be presented as evidence of performance at CliniKit.

## Variables with strongest model influence

Random-forest impurity importance, grouped across one-hot categories:

| Feature | Importance |
|---|---:|
| Waiting days | 0.657 |
| Age | 0.083 |
| Neighbourhood | 0.080 |
| SMS received | 0.068 |
| Scheduled hour | 0.052 |

Importance shows what the model used, not causation. Correlated variables and
high-cardinality categories can distort impurity importance. Production analysis
should add permutation importance or SHAP on held-out data and review subgroup
performance with clinic experts.

## Example predictions

`artifacts/example_predictions.csv` records three actual test examples. To make
a new prediction, supply every feature:

```bash
python predict.py --json "{\"age\":35,\"waiting_days\":14,\"scheduled_hour\":10,\"scholarship\":0,\"hypertension\":0,\"diabetes\":0,\"alcoholism\":0,\"handicap\":0,\"sms_received\":1,\"gender\":\"Female\",\"neighbourhood\":\"CENTRO\",\"appointment_weekday\":\"Monday\"}"
```

The returned probability is a model score. It should not be shown to patients
as a medical assessment.

## Product integration

At appointment creation, the scheduling backend would construct the validated
feature object and call a versioned prediction service. The service loads the
saved pipeline, returns a risk score and model version, and the workflow uses a
clinic-approved threshold to schedule a reminder or staff follow-up. The actual
appointment outcome later feeds monitored retraining data.

Before real use: train on recent local data; confirm that every feature exists
at prediction time; protect access and logs; define retention; measure drift,
calibration, subgroup performance, workload and intervention outcomes; use a
human-reviewed workflow; and offer reminders consistently. Retraining and
threshold changes require versioning and evaluation on later untouched dates.

## Files

| File | Purpose |
|---|---|
| `train.py` | Exploration, cleaning, split, training, evaluation and artifacts |
| `predict.py` | One example inference interface |
| `download_data.py` | KaggleHub downloader |
| `artifacts/metrics.json` | Exact results and classification report |
| `artifacts/eda.png` | Target and feature exploration |
| `artifacts/confusion_matrix.png` | Test errors |
| `artifacts/feature_importance.csv` | Grouped feature influence |
| `artifacts/example_predictions.csv` | Three held-out examples |
| `artifacts/model.joblib` | Fitted pipeline and threshold |
| `LEARNING_GUIDE.md` | Explanation and technical discussion preparation |

AI assistance was used while developing and reviewing this assessment. Read the
learning guide, run the code, and be prepared to explain or modify it.
