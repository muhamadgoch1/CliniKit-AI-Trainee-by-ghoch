"""Run: python main.py --demo, or python main.py for an interactive session."""
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from assistant import Assistant

EXAMPLES = [
    'Can I see Dr. George tomorrow afternoon?',
    'Move my appointment from Monday to Wednesday.',
    'Cancel my appointment with Dr. Karim.',
    'What time does the clinic close?',
    'Do you have anything available after 5 tomorrow?',
    'I want to see my doctor again for the same problem.',
    "Book me Friday at 4 but don't confirm anything yet.",
    'I need an appointment sometime next week.',
    'Can somebody from the clinic call me?',
    "I might want to see Dr. George tomorrow at 4, but don't book anything yet.",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Run assessment examples and complete action flows')
    parser.add_argument('--now', help='Override Beirut wall time, e.g. 2026-09-14T08:00:00')
    args = parser.parse_args()
    if args.now:
        now = datetime.fromisoformat(args.now)
        if now.tzinfo:
            parser.error('--now must be a local wall time without an offset')
    elif args.demo:
        now = datetime(2026, 9, 14, 8)
    else:
        now = datetime.now(ZoneInfo('Asia/Beirut')).replace(tzinfo=None)
    print(f'FICTIONAL CLINIC DEMO — Beirut reference time: {now.isoformat()}')
    if args.demo:
        for message in EXAMPLES:
            print(json.dumps(dict(message=message, result=Assistant(now).handle(message)), indent=2))
        for conversation in [
            ['Book Dr. George tomorrow at 4 PM', 'confirm', 'confirm'],
            ['Move my appointment from Monday to Wednesday', 'APT-001', 'at 4 PM', 'confirm'],
            ['Cancel my appointment with Dr. Karim', 'APT-001', 'confirm'],
            ["Book Dr. George tomorrow at 4 PM but don't book yet", 'confirm'],
        ]:
            bot = Assistant(now)
            print('\nNEW CONVERSATION')
            for message in conversation:
                print(json.dumps(dict(message=message, result=bot.handle(message)), indent=2))
        return
    bot = Assistant(now)
    print('Demo patient: demo-patient. Appointment reference: APT-001.')
    print('Commands: confirm, no, quit. State resets when this program exits.')
    while True:
        try:
            message = input('\nYou: ')
        except (EOFError, KeyboardInterrupt):
            break
        if message.strip().lower() == 'quit':
            break
        print(json.dumps(bot.handle(message), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
