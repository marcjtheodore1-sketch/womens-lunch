import os
import unittest
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['ENABLE_EMAIL'] = 'false'

import app as film_app


class FilmBriefingTests(unittest.TestCase):
    def setUp(self):
        self.app = film_app.app
        self.context = self.app.app_context()
        self.context.push()
        film_app.db.drop_all()
        film_app.db.create_all()
        self.app.config.update(
            TESTING=True,
            FILM_CLUB_LEAD_NAME='Itzi',
            FILM_CLUB_LEAD_EMAIL='itzi@example.org',
            FILM_BRIEFING_SEND_HOUR=18,
        )

        self.session = film_app.FilmSession(
            session_date=date(2026, 9, 16),
            arrival_time=time(17, 0),
            film_start_time=time(17, 30),
            end_time=time(20, 0),
            max_attendees=1,
            film_title='Test Film',
        )
        other_session = film_app.FilmSession(
            session_date=date(2026, 10, 21), max_attendees=15
        )
        film_app.db.session.add_all([self.session, other_session])
        film_app.db.session.flush()
        film_app.db.session.add_all([
            film_app.FilmVolunteer(
                film_session_id=self.session.id,
                volunteer_name='Jasper',
                volunteer_email='jasper@example.org',
            ),
            film_app.FilmVolunteer(
                film_session_id=other_session.id,
                volunteer_name='Other-date volunteer',
                volunteer_email='other@example.org',
            ),
        ])
        active = film_app.FilmBooking(
            film_session_id=self.session.id,
            full_name='Alex & Sam',
            email='attendee@example.org',
            is_adult=True,
            access_needs='Low lighting <please>',
            seating_preferences='Near the exit',
            comfort_information='May step outside',
            dietary_requirements='Nut allergy',
            cancel_token='active-token',
        )
        cancelled = film_app.FilmBooking(
            film_session_id=self.session.id,
            full_name='Cancelled Person',
            email='cancelled@example.org',
            is_adult=True,
            access_needs='Do not include',
            cancel_token='cancelled-token',
            cancelled_at=datetime(2026, 9, 10),
        )
        film_app.db.session.add_all([active, cancelled])
        film_app.db.session.flush()
        film_app.db.session.add(film_app.FilmBookingSupport(
            film_booking_id=active.id,
            attendee_phone='07123 456789',
            attending_with_others=True,
            additional_attendee_count=1,
            companion_details='Support worker Pat',
            has_carer_or_support_worker=True,
            carer_name='Pat',
            carer_organisation='Support Org',
            carer_mobile='07999 123456',
            responsibility_details='Pat remains responsible for support',
            support_boundary_acknowledged=True,
        ))
        film_app.db.session.commit()

    def tearDown(self):
        film_app.db.session.remove()
        film_app.db.drop_all()
        self.context.pop()

    def test_home_makes_full_status_and_date_clear(self):
        response = self.app.test_client().get('/film-club')
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('fully-booked', html)
        self.assertIn('class="booking-status full"', html)
        self.assertIn('Fully booked', html)
        self.assertIn('datetime="2026-09-16"', html)
        self.assertIn('Wednesday', html)
        self.assertIn('September', html)

    def test_due_job_uses_only_lead_and_session_rota_and_is_idempotent(self):
        sent = []

        def record_send(email, subject, html, calendar_content=None):
            sent.append((email, subject, html))
            return True

        run_at = datetime(2026, 9, 15, 18, 0, tzinfo=ZoneInfo('Europe/London'))
        with patch.object(film_app, 'send_rich_email', side_effect=record_send):
            first = film_app.send_due_film_briefings(run_at)
            second = film_app.send_due_film_briefings(run_at)

            film_app.db.session.add(film_app.FilmVolunteer(
                film_session_id=self.session.id,
                volunteer_name='New volunteer',
                volunteer_email='new@example.org',
            ))
            film_app.db.session.commit()
            third = film_app.send_due_film_briefings(run_at)

        self.assertEqual(first, {'sessions': 1, 'sent': 2, 'failed': 0, 'skipped': 0})
        self.assertEqual(second, {'sessions': 1, 'sent': 0, 'failed': 0, 'skipped': 2})
        self.assertEqual(third, {'sessions': 1, 'sent': 1, 'failed': 0, 'skipped': 2})
        self.assertEqual(
            [item[0] for item in sent],
            ['itzi@example.org', 'jasper@example.org', 'new@example.org'],
        )
        self.assertNotIn('other@example.org', [item[0] for item in sent])

        briefing = sent[0][2]
        self.assertIn('Alex &amp; Sam', briefing)
        self.assertIn('Low lighting &lt;please&gt;', briefing)
        self.assertIn('Near the exit', briefing)
        self.assertIn('May step outside', briefing)
        self.assertIn('Nut allergy', briefing)
        self.assertIn('Support worker Pat', briefing)
        self.assertIn('Pat remains responsible for support', briefing)
        self.assertNotIn('Cancelled Person', briefing)
        self.assertNotIn('attendee@example.org', briefing)

    def test_job_waits_until_the_configured_london_evening_hour(self):
        run_at = datetime(2026, 9, 15, 17, 59, tzinfo=ZoneInfo('Europe/London'))
        with patch.object(film_app, 'send_rich_email') as send:
            totals = film_app.send_due_film_briefings(run_at)
        self.assertEqual(totals, {'sessions': 0, 'sent': 0, 'failed': 0, 'skipped': 0})
        send.assert_not_called()

    def test_failed_delivery_is_not_recorded_and_can_be_retried(self):
        run_at = datetime(2026, 9, 15, 19, 0, tzinfo=ZoneInfo('Europe/London'))
        with patch.object(film_app, 'send_rich_email', return_value=False):
            failed = film_app.send_due_film_briefings(run_at)
        self.assertEqual(failed, {'sessions': 1, 'sent': 0, 'failed': 2, 'skipped': 0})
        self.assertEqual(film_app.FilmBriefingRecipient.query.count(), 0)

        with patch.object(film_app, 'send_rich_email', return_value=True):
            retried = film_app.send_due_film_briefings(run_at)
        self.assertEqual(retried, {'sessions': 1, 'sent': 2, 'failed': 0, 'skipped': 0})
        self.assertEqual(film_app.FilmBriefingRecipient.query.count(), 2)


if __name__ == '__main__':
    unittest.main()
