"""Explainable clinic routing baseline. All data and actions are fictional."""
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

DOCTORS = ('George', 'Karim')
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


def normalize(message):
    text = ' '.join(message.lower().replace('’', "'").split())
    # Deliberately small, auditable typo dictionary; not general spell correction.
    for old, new in {'tmrw': 'tomorrow', 'tmr': 'tomorrow', 'apointment': 'appointment',
                     'appointmnt': 'appointment', 'reshedule': 'reschedule',
                     'cancell': 'cancel', 'pls': 'please'}.items():
        text = re.sub(r'\b' + old + r'\b', new, text)
    return text


@dataclass
class Request:
    intent: str = 'other'
    doctor: str | None = None
    preferred_date: str | None = None
    preferred_time: str | None = None
    time_relation: str = 'exact'
    appointment_id: str | None = None
    original_date: str | None = None
    do_not_act: bool = False
    issue: str | None = None


def extract(message, now):
    """Convert supported English into slots. Uncertain inputs stay uncertain."""
    text = normalize(message)
    r = Request()
    r.do_not_act = bool(re.search(
        r"\b(don't|do not|not yet|might|maybe|perhaps|not sure|without|never|hold off|wait)\b", text))
    if re.search(r'\b(human|receptionist|someone|somebody)\b|\bcall me\b', text):
        r.intent = 'human_handoff'
    elif re.search(r'\b(hours|opening|close|opens|closing)\b|\bwhen.*open\b', text):
        r.intent = 'clinic_hours'
    elif re.search(r'\b(reschedule|move|change)\b', text):
        r.intent = 'reschedule_appointment'
    elif re.search(r'\bcancel\b', text):
        r.intent = 'cancel_appointment'
    elif re.search(r'\b(book|appointment|see|visit)\b', text):
        r.intent = 'book_appointment'
    elif re.search(r'\b(available|availability|anything|free slot)\b', text):
        r.intent = 'check_availability'
    if re.search(r'\bcancel\b.*\b(book|reschedule|move)\b|\b(book|reschedule|move)\b.*\bcancel\b', text):
        r.issue = 'Please make one appointment request at a time.'
    doctors = re.findall(r'\b(?:dr\.?|doctor)\s+([a-z]+)', text)
    if len(set(doctors)) > 1:
        r.issue = 'Which one doctor do you want?'
    elif doctors:
        r.doctor = doctors[0].title()
        if r.doctor not in DOCTORS:
            r.issue = 'The mock clinic lists Dr. George and Dr. Karim. Which one do you want?'
    ident = re.search(r'\bapt-\d+\b', text)
    if ident:
        r.appointment_id = ident[0].upper()
    # For a move, parse the destination separately from the original date.
    date_text = text
    move = re.search(r'\bfrom (.+?) to (.+)', text)
    if move and r.intent == 'reschedule_appointment':
        r.original_date = move[1]
        date_text = move[2]
    tokens = re.findall(r'\b(?:\d{4}-\d{2}-\d{2}|today|tomorrow|' + '|'.join(WEEKDAYS) + r')\b', date_text)
    if len(tokens) > 1:
        r.issue = 'Please give one destination date in YYYY-MM-DD format.'
    elif tokens:
        token = tokens[0]
        if token == 'today':
            day = now.date()
        elif token == 'tomorrow':
            day = now.date() + timedelta(days=1)
        elif token in WEEKDAYS:
            offset = (WEEKDAYS.index(token) - now.weekday()) % 7
            day = now.date() + timedelta(days=offset)
            if 'next ' + token in date_text:
                # "next Friday" is ambiguous between common conventions.
                r.issue = 'For "next" weekday, please give the exact date (YYYY-MM-DD).'
        else:
            try:
                day = datetime.strptime(token, '%Y-%m-%d').date()
            except ValueError:
                r.issue = 'That date is invalid. Use YYYY-MM-DD.'
                day = None
        if day:
            r.preferred_date = day.isoformat()
    elif 'next week' in date_text:
        r.issue = 'Which exact day next week? Please use YYYY-MM-DD.'
    # Parse a single clock time. Bare 4 / after 5 must not silently mean PM.
    times = list(re.finditer(r'\b(?:at|after|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', date_text))
    if not times:
        times = list(re.finditer(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', date_text))
    if len(times) > 1:
        r.issue = 'Please specify one time or a single after/before time.'
    elif times:
        match = times[0]
        hour, minute = int(match[1]), int(match[2] or 0)
        suffix = match[3]
        r.time_relation = 'after' if match[0].startswith('after') else 'before' if match[0].startswith('before') else 'exact'
        if minute > 59 or hour > 23 or (suffix and not 1 <= hour <= 12):
            r.issue = 'That time is invalid. Use e.g. 4 PM or 16:00.'
        elif not suffix and not match[2] and 1 <= hour <= 12:
            r.preferred_time = match[0]
            r.issue = 'Do you mean AM or PM? Please repeat the time, e.g. at 4 PM.'
        else:
            if suffix:
                hour = hour % 12 + (12 if suffix == 'pm' else 0)
            r.preferred_time = f'{hour:02}:{minute:02}'
    else:
        for period in ('morning', 'afternoon', 'evening'):
            if period in date_text:
                r.preferred_time = period
                break
    return r


class MockClinic:
    """Single-process, in-memory tool layer; patient identity is preconfigured."""
    def __init__(self, now):
        self.now = now
        self.appointments = {}
        self.next_id = 3
        future = now.date() + timedelta(days=(0 - now.weekday()) % 7 or 7)
        self.appointments['APT-001'] = dict(patient='demo-patient', doctor='Karim', date=future.isoformat(), time='11:00')
        self.appointments['APT-002'] = dict(patient='other-patient', doctor='George', date=future.isoformat(), time='09:00')
        self.handoffs = []

    def check_availability(self, r):
        day = datetime.strptime(r.preferred_date, '%Y-%m-%d').date()
        if day.weekday() == 6 or not 0 <= (day - self.now.date()).days <= 30:
            return []
        slots = []
        for doctor in ([r.doctor] if r.doctor else DOCTORS):
            for clock in ('09:00', '11:00', '14:00', '16:00', '17:30', '18:00'):
                if datetime.fromisoformat(f'{day}T{clock}') <= self.now:
                    continue
                wanted = r.preferred_time
                if wanted in ('morning', 'afternoon', 'evening'):
                    low, high = {'morning': ('09:00', '12:00'), 'afternoon': ('12:00', '17:00'), 'evening': ('17:00', '19:00')}[wanted]
                    if not low <= clock < high:
                        continue
                elif wanted:
                    if r.time_relation == 'exact' and clock != wanted:
                        continue
                    if r.time_relation == 'after' and clock <= wanted:
                        continue
                    if r.time_relation == 'before' and clock >= wanted:
                        continue
                if any(a['doctor'] == doctor and a['date'] == str(day) and a['time'] == clock for a in self.appointments.values()):
                    continue
                slots.append(dict(doctor=doctor, date=str(day), time=clock))
        return slots

    def owned(self, appointment_id, patient):
        a = self.appointments.get(appointment_id)
        return a if a and a['patient'] == patient else None

    def create_appointment(self, r, patient):
        if not self.check_availability(r):
            raise ValueError('The selected slot is no longer available. Please choose another.')
        ident = f'APT-{self.next_id:03}'
        self.next_id += 1
        self.appointments[ident] = dict(patient=patient, doctor=r.doctor, date=r.preferred_date, time=r.preferred_time)
        return ident

    def reschedule_appointment(self, r, patient):
        old = self.owned(r.appointment_id, patient)
        if not old:
            raise ValueError('No matching appointment for this demo patient.')
        if not self.check_availability(r):
            raise ValueError('The selected slot is no longer available. Original appointment kept.')
        old.update(doctor=r.doctor, date=r.preferred_date, time=r.preferred_time)
        return r.appointment_id

    def cancel_appointment(self, r, patient):
        if not self.owned(r.appointment_id, patient):
            raise ValueError('No matching appointment for this demo patient.')
        del self.appointments[r.appointment_id]
        return r.appointment_id

    def handoff_to_human(self, patient):
        ident = f'H-{len(self.handoffs) + 1:03}'
        self.handoffs.append(dict(id=ident, patient=patient))
        return ident


class Assistant:
    def __init__(self, now=None):
        # The CLI supplies Beirut wall time. Tests inject a fixed wall time.
        self.clinic = MockClinic(now or datetime.now())
        self.patient = 'demo-patient'
        self.context = None
        self.pending = None

    def result(self, r, action, response, **extra):
        return dict(structured=asdict(r), action=action, response=response, **extra)

    def handle(self, message):
        text = normalize(message).strip(' .!?')
        if text == 'confirm':
            if not self.pending:
                return self.result(Request(), 'ask_for_more_information', 'No action is awaiting confirmation. Please make a complete request.')
            r = self.pending
            self.pending = self.context = None  # Consume once, including failures.
            try:
                tool_name = 'create_appointment' if r.intent == 'book_appointment' else r.intent
                tool = getattr(self.clinic, tool_name)
                ident = tool(r, self.patient)
            except ValueError as exc:
                return self.result(r, 'ask_for_more_information', str(exc))
            return self.result(r, tool_name, f'Mock action completed: {tool_name}; appointment {ident}.', appointment_id=ident)
        # Any other message invalidates the old confirmation proposal.
        self.pending = None
        if text in ('no', 'stop', 'never mind', 'nevermind'):
            self.context = None
            return self.result(Request(), 'no_action', 'Request cleared. No appointment was changed.')
        r = extract(message, self.clinic.now)
        if r.intent == 'other' and self.context and any((r.doctor, r.preferred_date, r.preferred_time, r.appointment_id)):
            previous = self.context
            r.intent = previous.intent
            for field in ('doctor', 'preferred_date', 'appointment_id', 'original_date'):
                if getattr(r, field) is None:
                    setattr(r, field, getattr(previous, field))
            if r.preferred_time is None:
                r.preferred_time, r.time_relation = previous.preferred_time, previous.time_relation
            r.do_not_act = r.do_not_act or previous.do_not_act
        self.context = None
        if r.intent == 'human_handoff':
            ticket = self.clinic.handoff_to_human(self.patient)
            return self.result(r, 'handoff_to_human', f'Mock handoff ticket {ticket} created. No real call or message was sent.')
        if r.intent == 'clinic_hours':
            return self.result(r, 'get_clinic_hours', 'Mock clinic hours: Monday–Saturday, 09:00–19:00 Beirut time; closed Sunday.')
        if r.intent == 'other':
            return self.result(r, 'ask_for_more_information', 'Would you like to book, reschedule, cancel, check hours or availability, or speak with a human?')
        self.context = r
        if r.issue:
            self.context = None
            return self.result(r, 'ask_for_more_information', r.issue + ' Please repeat the full corrected request.' + (' No appointment will be changed.' if r.do_not_act else ''))
        if r.do_not_act:
            self.context = None
            if r.preferred_date and r.intent in ('book_appointment', 'check_availability'):
                slots = self.clinic.check_availability(r)
                return self.result(r, 'check_availability', 'Information only; nothing booked or held. Make a fresh booking request if you decide to proceed.', slots=slots)
            return self.result(r, 'no_action', 'No appointment changed. Make a fresh request when you decide to proceed.')
        if r.intent in ('cancel_appointment', 'reschedule_appointment'):
            if not r.appointment_id:
                return self.result(r, 'ask_for_more_information', 'What is your appointment reference? Demo reference: APT-001.')
            old = self.clinic.owned(r.appointment_id, self.patient)
            if not old:
                self.context = None
                return self.result(r, 'ask_for_more_information', 'No matching appointment for this demo patient. Check the reference or request a human.')
            if r.doctor and r.doctor != old['doctor']:
                return self.result(r, 'ask_for_more_information', 'The doctor does not match that appointment. Please clarify in a new request.')
            r.doctor = old['doctor']
            if r.intent == 'cancel_appointment':
                return self.propose(r, f"Cancel {r.appointment_id} with Dr. {old['doctor']} on {old['date']} at {old['time']}?")
        if not r.preferred_date:
            return self.result(r, 'ask_for_more_information', 'Which date? Use tomorrow, a weekday, or YYYY-MM-DD.')
        if not 0 <= (datetime.fromisoformat(r.preferred_date).date() - self.clinic.now.date()).days <= 30:
            return self.result(r, 'ask_for_more_information', 'Choose a date from today through the next 30 days in this mock clinic.')
        slots = self.clinic.check_availability(r)
        exact = r.preferred_time and re.fullmatch(r'\d{2}:\d{2}', r.preferred_time) and r.time_relation == 'exact'
        if r.intent == 'check_availability' or not r.doctor or not exact or not slots:
            response = 'Available mock slots listed below. Choose a doctor and exact time; include AM/PM or use 24-hour time.' if slots else 'No matching mock slots. Please choose another date or time.'
            return self.result(r, 'check_availability', response, slots=slots)
        return self.propose(r, f"{r.intent.replace('_', ' ').capitalize()} with Dr. {r.doctor} on {r.preferred_date} at {r.preferred_time} (Beirut time)" + (f' for {r.appointment_id}?' if r.appointment_id else '?'))

    def propose(self, r, summary):
        self.pending = r
        return self.result(r, 'request_confirmation', summary + ' Type exactly confirm to apply this mock action, or no to discard it.')
