import unittest
from datetime import datetime
from assistant import Assistant, extract
from main import EXAMPLES

NOW = datetime(2026, 9, 14, 8)


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.bot = Assistant(NOW)

    def test_all_assessment_examples_do_not_mutate_appointments(self):
        expected = ['book_appointment', 'reschedule_appointment', 'cancel_appointment',
                    'clinic_hours', 'check_availability', 'book_appointment',
                    'book_appointment', 'book_appointment', 'human_handoff', 'book_appointment']
        for message, intent in zip(EXAMPLES, expected):
            with self.subTest(message=message):
                bot = Assistant(NOW)
                before = repr(bot.clinic.appointments)
                result = bot.handle(message)
                self.assertEqual(result['structured']['intent'], intent)
                self.assertEqual(repr(bot.clinic.appointments), before)

    def test_booking_requires_confirmation_and_cannot_replay(self):
        self.assertEqual(self.bot.handle('Book Dr. George tomorrow at 4 PM')['action'], 'request_confirmation')
        self.assertEqual(len(self.bot.clinic.appointments), 2)
        self.assertEqual(self.bot.handle('confirm')['action'], 'create_appointment')
        self.assertEqual(len(self.bot.clinic.appointments), 3)
        self.assertEqual(self.bot.handle('confirm')['action'], 'ask_for_more_information')
        self.assertEqual(len(self.bot.clinic.appointments), 3)

    def test_dont_book_blocks_even_subsequent_confirm(self):
        for phrase in ("don't book yet", 'do not confirm', 'maybe', 'not yet', 'without booking'):
            with self.subTest(phrase=phrase):
                bot = Assistant(NOW)
                bot.handle('Book Dr. George tomorrow at 4 PM ' + phrase)
                self.assertIsNone(bot.pending)
                bot.handle('confirm')
                self.assertEqual(len(bot.clinic.appointments), 2)

    def test_withdrawal_and_unrelated_message_invalidate_confirmation(self):
        for message in ('no', "don't do that", 'What are your hours?', 'hello'):
            bot = Assistant(NOW)
            bot.handle('Book Dr. George tomorrow at 4 PM')
            bot.handle(message)
            bot.handle('confirm')
            self.assertEqual(len(bot.clinic.appointments), 2)

    def test_multi_turn_booking(self):
        self.bot.handle('I need an appointment tomorrow afternoon')
        self.assertEqual(self.bot.handle('Dr. George at 4 PM')['action'], 'request_confirmation')
        self.bot.handle('confirm')
        self.assertEqual(self.bot.clinic.appointments['APT-003']['time'], '16:00')

    def test_reschedule_preserves_id_and_waits_for_confirmation(self):
        original = dict(self.bot.clinic.appointments['APT-001'])
        self.bot.handle('Move my appointment from Monday to Wednesday')
        self.bot.handle('APT-001')
        self.assertEqual(self.bot.handle('at 4 PM')['action'], 'request_confirmation')
        self.assertEqual(self.bot.clinic.appointments['APT-001'], original)
        self.bot.handle('confirm')
        self.assertEqual(self.bot.clinic.appointments['APT-001']['date'], '2026-09-16')

    def test_cancel_flow(self):
        self.bot.handle('Cancel my appointment with Dr. Karim')
        self.assertEqual(self.bot.handle('APT-001')['action'], 'request_confirmation')
        self.bot.handle('confirm')
        self.assertNotIn('APT-001', self.bot.clinic.appointments)

    def test_other_patient_reference_is_not_authorization(self):
        self.bot.handle('Cancel APT-002')
        self.bot.handle('confirm')
        self.assertIn('APT-002', self.bot.clinic.appointments)

    def test_slot_rechecked_at_confirmation(self):
        self.bot.handle('Book Dr. George tomorrow at 4 PM')
        self.bot.clinic.appointments['APT-099'] = dict(patient='other', doctor='George', date='2026-09-15', time='16:00')
        result = self.bot.handle('confirm')
        self.assertIn('no longer available', result['response'])
        self.assertNotIn('APT-003', self.bot.clinic.appointments)

    def test_ambiguous_or_invalid_requests_never_propose(self):
        for message in ('Book Dr. George tomorrow at 4', 'Book Dr. Unknown tomorrow at 4 PM',
                        'Book Dr. George 2026-02-30 at 4 PM', 'Book Dr. George tomorrow at 25:00',
                        'Book Dr. George tomorrow at 13 PM', 'Book Dr. George next Friday at 4 PM',
                        'Book Dr. George Monday or Tuesday at 4 PM', 'cancel and book tomorrow'):
            with self.subTest(message=message):
                bot = Assistant(NOW)
                self.assertEqual(bot.handle(message)['action'], 'ask_for_more_information')
                self.assertIsNone(bot.pending)

    def test_after_filter(self):
        slots = self.bot.handle('Anything available tomorrow after 5 PM?')['slots']
        self.assertTrue(slots)
        self.assertTrue(all(s['time'] > '17:00' for s in slots))

    def test_typo_normalization(self):
        r = extract('pls book an apointment Dr. George tmrw at 4 pm', NOW)
        self.assertEqual((r.intent, r.doctor, r.preferred_date, r.preferred_time),
                         ('book_appointment', 'George', '2026-09-15', '16:00'))

    def test_hours_handoff_and_unknown(self):
        self.assertEqual(self.bot.handle('clinic hours?')['action'], 'get_clinic_hours')
        self.assertEqual(self.bot.handle('Can somebody call me?')['action'], 'handoff_to_human')
        self.assertEqual(len(self.bot.clinic.handoffs), 1)
        self.assertEqual(self.bot.handle('xyz')['action'], 'ask_for_more_information')

    def test_closed_past_and_outside_horizon(self):
        self.assertEqual(self.bot.handle('Book Dr. George Sunday at 4 PM')['slots'], [])
        for day in ('2026-09-01', '2026-12-01'):
            self.assertEqual(self.bot.handle(f'Book Dr. George {day} at 4 PM')['action'], 'ask_for_more_information')


if __name__ == '__main__':
    unittest.main()
