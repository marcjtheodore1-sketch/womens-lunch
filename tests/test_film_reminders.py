import os
import unittest
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['ENABLE_EMAIL'] = 'false'

import app as film_app


class FilmReminderTests(unittest.TestCase):
    def setUp(self):
        self.app = film_app.app
        self.context = self.app.app_context()
        self.context.push()
        film_app.db.drop_all()
        film_app.db.create_all()
        self.app.config.update(
            TESTING=True,
            PUBLIC_BASE_URL='https://activities.example.org',
        )
        self.session = film_app.FilmSession(
            session_date=date(2026, 10, 21),
            arrival_time=time(17, 0),
            film_start_time=time(17, 30),
            end_time=time(20, 0),
            max_attendees=15,
            film_title='Test Film',
        )
        film_app.db.session.add(self.session)
        film_app.db.session.flush()
        self.booking = film_app.FilmBooking(
            film_session_id=self.session.id,
            full_name='Alex Example',
            email='alex@example.org',
            is_adult=True,
            access_needs='Private access detail',
            cancel_token='alex-token',
        )
        cancelled = film_app.FilmBooking(
            film_session_id=self.session.id,
            full_name='Cancelled Person',
            email='cancelled@example.org',
            is_adult=True,
            cancel_token='cancelled-token',
            cancelled_at=datetime(2026, 10, 1),
        )
        film_app.db.session.add_all([self.booking, cancelled])
        film_app.db.session.commit()

    def tearDown(self):
        film_app.db.session.remove()
        film_app.db.drop_all()
        self.context.pop()

    def test_each_stage_sends_once_to_active_booking(self):
        deliveries = []

        def record_send(email, subject, html, calendar_content=None):
            deliveries.append((email, subject, html, calendar_content))
            return True

        london = ZoneInfo('Europe/London')
        with patch.object(film_app, 'send_rich_email', side_effect=record_send):
            fourteen_day = film_app.send_due_film_reminders(
                datetime(2026, 10, 7, 17, 0, tzinfo=london)
            )
            duplicate = film_app.send_due_film_reminders(
                datetime(2026, 10, 7, 17, 5, tzinfo=london)
            )
            seven_day = film_app.send_due_film_reminders(
                datetime(2026, 10, 14, 17, 0, tzinfo=london)
            )
            twenty_four_hour = film_app.send_due_film_reminders(
                datetime(2026, 10, 20, 17, 0, tzinfo=london)
            )

        self.assertEqual(fourteen_day['sent'], 1)
        self.assertEqual(duplicate['sent'], 0)
        self.assertEqual(duplicate['skipped'], 1)
        self.assertEqual(seven_day['sent'], 1)
        self.assertEqual(twenty_four_hour['sent'], 1)
        self.assertEqual([item[0] for item in deliveries], ['alex@example.org'] * 3)
        self.assertEqual(film_app.FilmReminderDelivery.query.count(), 3)
        self.assertTrue(all(item[3] for item in deliveries))

        first_html = deliveries[0][2]
        self.assertIn('in two weeks', first_html)
        self.assertIn('Wednesday 21st October 2026', first_html)
        self.assertIn('https://activities.example.org/film-club/cancel/alex-token', first_html)
        self.assertNotIn('Private access detail', first_html)
        self.assertNotIn('Cancelled Person', first_html)

    def test_24_hour_stage_does_not_start_early(self):
        london = ZoneInfo('Europe/London')
        before = datetime(2026, 10, 20, 16, 59, tzinfo=london)
        at_threshold = datetime(2026, 10, 20, 17, 0, tzinfo=london)
        self.assertEqual(
            film_app.film_reminder_stage_for_time(self.session, before)['kind'],
            '7_days',
        )
        self.assertEqual(
            film_app.film_reminder_stage_for_time(self.session, at_threshold)['kind'],
            '24_hours',
        )

    def test_disabled_stage_is_managed_per_session(self):
        film_app.db.session.add(film_app.FilmReminderPreference(
            film_session_id=self.session.id,
            fourteen_day_enabled=False,
            seven_day_enabled=True,
            twenty_four_hour_enabled=True,
        ))
        film_app.db.session.commit()
        london = ZoneInfo('Europe/London')
        with patch.object(film_app, 'send_rich_email') as send:
            totals = film_app.send_due_film_reminders(
                datetime(2026, 10, 7, 17, 0, tzinfo=london)
            )
        self.assertEqual(totals['disabled'], 1)
        self.assertEqual(totals['sent'], 0)
        send.assert_not_called()

    def test_failed_delivery_is_retried_and_not_marked_sent(self):
        run_at = datetime(
            2026, 10, 14, 17, 0, tzinfo=ZoneInfo('Europe/London')
        )
        with patch.object(film_app, 'send_rich_email', return_value=False):
            failed = film_app.send_due_film_reminders(run_at)
        self.assertEqual(failed['failed'], 1)
        self.assertEqual(film_app.FilmReminderDelivery.query.count(), 0)

        with patch.object(film_app, 'send_rich_email', return_value=True):
            retried = film_app.send_due_film_reminders(run_at)
        self.assertEqual(retried['sent'], 1)
        self.assertEqual(film_app.FilmReminderDelivery.query.count(), 1)

    def test_admin_page_shows_schedule_and_delivery_controls(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['admin_logged_in'] = True
            session['_csrf_token'] = 'test-csrf'
        response = client.get('/admin/film-club?tab=emails')
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Attendee reminders', html)
        self.assertIn('Two weeks before', html)
        self.assertIn('One week before', html)
        self.assertIn('24 hours before', html)
        self.assertIn('Run due reminders now', html)


if __name__ == '__main__':
    unittest.main()
