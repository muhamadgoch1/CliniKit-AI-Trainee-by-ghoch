# CliniKit AI Trainee Assessment — Exercise 1

An explainable, rule-based conversational assistant for a fictional medical clinic.
It receives English messages, extracts structured fields, routes requests to mock
functions, and replies. It supports booking, rescheduling, cancellation, opening
hours, availability, human handoff, and clarification. This is an assessment
prototype, not a production service. Exercise 2 is not included: the dataset was
not supplied with the assessment email.

## Run (Python 3.10 or newer)

Extract the ZIP, open a terminal in this folder, then run:

```bash
python -m pip install -r requirements.txt
python main.py --demo
python main.py
python -m unittest discover -s tests -v
```

On Windows, use `py` instead of `python` if needed. No API key, model download,
database, or paid service is needed. The only external dependency is `tzdata`,
which supports Beirut timezone lookup on systems without timezone data.

`--demo` uses Monday, September 14, 2026 at 08:00 Beirut time for reproducible
results. Interactive mode reads current Beirut time. You can freeze the clock:

```bash
python main.py --now 2026-09-14T08:00:00
```

Type messages into the interactive terminal. `confirm` executes the displayed
proposal; `no` discards it; `quit` exits. All data resets on restart.

## Try these conversations

Each example below starts in a fresh session with the frozen clock above.

**Booking**

```text
Book Dr. George tomorrow at 4 PM
confirm
```

First response: `request_confirmation`. Second response: `create_appointment`.
A repeat `confirm` cannot create another appointment.

**Missing information and rescheduling**

```text
Move my appointment from Monday to Wednesday
APT-001
at 4 PM
confirm
```

The assistant asks for the appointment reference, lists available Wednesday
slots, proposes 16:00, then updates the same appointment after confirmation.

**Cancellation**

```text
Cancel my appointment with Dr. Karim
APT-001
confirm
```

**Tentative request**

```text
Book Dr. George tomorrow at 4 PM but don't book yet
confirm
```

Only availability is returned; no proposal exists for `confirm` to execute.

**Ambiguous clock time**

```text
Book Dr. George tomorrow at 4
Book Dr. George tomorrow at 4 PM
confirm
```

The first message asks AM or PM. For an invalid or ambiguous message, repeat the
full corrected request; the old context is discarded deliberately.

## Approach and technical decisions

1. **Normalize** casing, apostrophes, whitespace, and a small explicit typo list.
2. **Identify intent** with ordered regular-expression rules. Rescheduling and
   cancellation take precedence over generic appointment words.
3. **Extract slots** into a `Request` dataclass: doctor, destination date, time,
   time relation, appointment reference, original-date text, uncertainty flag,
   and any parsing issue. Missing information remains `None` (`null` in JSON).
4. **Apply policy** in `Assistant.handle`. Read-only requests can run immediately;
   incomplete requests ask a question or show slots. Appointment changes need a
   complete proposal and a separate exact `confirm` turn.
5. **Execute mock tools** in `MockClinic`. Responses use tool results; the
   assistant does not claim an appointment was changed before execution.

This is a rule-based conversational baseline, not an LLM or a trained intent
classifier. I chose it for reproducibility, inspectable decisions, no credentials,
and the assessment's small scope. The tradeoff is limited language coverage.
A production improvement would replace `extract()` with an evaluated intent/slot
model or schema-constrained LLM while retaining independent validation and
confirmation in the policy layer. The assessment permits mocked functions and
does not mandate an LLM (assessment PDF, pp. 1–2).

## Structured output

For `Book Dr. George tomorrow at 4 PM`, at the frozen clock:

```json
{
  "intent": "book_appointment",
  "doctor": "George",
  "preferred_date": "2026-09-15",
  "preferred_time": "16:00",
  "time_relation": "exact",
  "appointment_id": null,
  "original_date": null,
  "do_not_act": false,
  "issue": null
}
```

The outer response additionally contains `action`, a patient-facing `response`,
and, when relevant, available `slots` or an `appointment_id`.
Intent is the patient's goal; action is the system's next step. A booking intent
can therefore produce clarification, availability lookup, or confirmation.

## Incorrect-action prevention

- Every appointment mutation needs a separate exact `confirm` message.
- Negation/uncertainty keywords block a proposal; explicit “don't book yet”
  cannot be overridden by a following bare `confirm`.
- Any non-confirm message invalidates the old proposal. A fresh valid proposal
  may then be created from the new message.
- Proposals are consumed once, including when execution fails.
- Cancellation/rescheduling require a reference owned by the configured demo
  patient; a reference alone is not treated as authentication.
- A named doctor must match the existing appointment when modifying it.
- Availability is checked again at execution, so a slot taken after a proposal
  is rejected; a failed reschedule keeps the original appointment.
- Unknown doctors, invalid dates/times, multiple detected dates/doctors, and
  detected combined cancellation/booking requests trigger clarification.

These are tested safeguards for this prototype, not proof of general natural
language safety. Regex rules can miss unsupported paraphrases and negation.

## Mock assumptions and limits

- Entirely fictional clinic hours: Monday–Saturday 09:00–19:00; Sunday closed.
- Doctors: George and Karim. Candidate slots: 09:00, 11:00, 14:00, 16:00,
  17:30, 18:00. Search horizon: today through 30 days ahead.
- Morning means 09:00–12:00, afternoon 12:00–17:00, evening 17:00–19:00.
- Times are Beirut wall time. There is no UTC persistence or DST transition
  handling; production would need timezone-aware storage and validation.
- A bare weekday means its next occurrence, including today. “Next Friday”
  requests an exact date because the expression is ambiguous. “Next week” also
  asks for an exact date. Bare hours such as “4” require AM/PM; `at 16:00` works.
- APT-001 belongs to `demo-patient`, with Dr. Karim at 11:00 on the next Monday
  strictly after the reference date. APT-002 belongs to a different fake patient.
- The appointment reference is authoritative for modifications; `original_date`
  is extracted for explanation but is not used to search or verify the original
  appointment. The displayed proposal identifies the actual target. Production
  should reconcile all supplied details with the stored appointment.
- Slot selection follow-ups work when the previous request was merely missing
  information. Parsing errors discard context and require a full corrected
  request. Explicit new intents start a new request.
- Only a limited English grammar and typo dictionary are supported. Doctor-name
  misspellings, arbitrary date formats, complex conditions/multiple intents,
  multilingual input, and long conversations are not fully handled.
- Handoff creates an in-memory ticket; no staff member is contacted.
- No real authentication, persistent storage, concurrent booking protection,
  medical triage, or diagnosis is implemented. Use fictional inputs only.

## Results and evaluation

See `demo_output.txt` for actual output for all nine example messages, the
additional “don't book yet” case, and four multi-turn flows. See
`test_results.txt` for the automated test run.

The suite has 14 tests with additional parameterized cases. It covers example
intent routing, no premature appointment mutation, successful confirmed booking,
rescheduling and cancellation, replay prevention, withdrawal, slot conflicts,
patient ownership, time filtering, malformed inputs, typo normalization, hours,
handoff, and unavailable dates. All 14 passed in the recorded Python 3.12 run.
This is functional verification on authored examples, not measured accuracy on
an independent natural-language dataset.

For a larger evaluation, collect separately labeled utterances and measure intent
precision/recall per class, slot extraction correctness, next-action correctness,
conversation completion, clarification rate, and unauthorized-action frequency.
Include unseen paraphrases and adversarial ambiguous requests.

## Production integration and improvements

Expose the assistant through an authenticated message endpoint, keep conversation
state per patient, and replace mock tools with the clinic scheduling API. Validate
all extracted fields against a schema and live clinic records. Use transactional
slot reservation, idempotency keys, expiration of confirmations, authorization,
and an audit trail. Keep patient information out of unnecessary logs. Add real
staff escalation, approved clinical escalation workflows, monitoring, and a
representative multilingual evaluation set before expanding language coverage.

## Files

| File | Purpose |
|---|---|
| `assistant.py` | Parsing, routing, confirmation state, and mock tools |
| `main.py` | Interactive CLI and reproducible demos |
| `tests/test_assistant.py` | Behavioral and state-transition tests |
| `requirements.txt` | Runtime dependency |
| `demo_output.txt` | Recorded results for both single and multi-turn messages |
| `test_results.txt` | Recorded test run |
| `LEARNING_GUIDE.md` | Walkthrough and technical-discussion preparation |

## Submission

The invitation email requests an accessible **GitHub repository link**. Upload
this folder's contents to your repository, review them, and later add Exercise 2.
The ZIP is a delivery package for the candidate, not a replacement for the email's
GitHub submission requirement. Do not claim that Exercise 2 is complete.

AI assistance was used to develop and review this baseline. Before submitting,
run it, inspect the implementation, and be able to explain and modify its rules.

## Sources

- Supplied *CliniKit AI Trainee Assessment*, pp. 1–3: requirements, mocked actions,
  ambiguity example, explanation and submission requirements.
- [Python regular expressions](https://docs.python.org/3/library/re.html)
- [Python dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [Python datetime](https://docs.python.org/3/library/datetime.html)
- [Python zoneinfo](https://docs.python.org/3/library/zoneinfo.html)
- [Python unittest](https://docs.python.org/3/library/unittest.html)
