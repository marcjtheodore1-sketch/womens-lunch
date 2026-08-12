import os
import tempfile
import unittest
from datetime import date


TEST_DATABASE = tempfile.mktemp(prefix='lagc-film-nomination-', suffix='.sqlite')
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DATABASE}'
os.environ['ENABLE_EMAIL'] = 'false'

import app as app_module


class FilmNominationAdminTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, SECRET_KEY='test-secret')
        with app_module.app.app_context():
            app_module.db.drop_all()
            app_module.db.create_all()
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as browser_session:
            browser_session['admin_logged_in'] = True
            browser_session['_csrf_token'] = 'test-csrf'

    def add_session_and_nomination(self, session_title=None, nomination_title='The Matrix'):
        with app_module.app.app_context():
            film_session = app_module.FilmSession(
                session_date=date(2030, 9, 18),
                film_title=session_title,
                max_attendees=15,
                is_bookable=True,
            )
            nomination = app_module.FilmNomination(
                nominator_name='Test nominator',
                nominator_email='nominator@example.org',
                film_title=nomination_title,
                why_this_film='A useful test nomination.',
            )
            app_module.db.session.add_all([film_session, nomination])
            app_module.db.session.commit()
            return film_session.id, nomination.id

    def post_nomination(self, nomination_id, session_id, status='selected'):
        return self.client.post(
            f'/admin/film-club/nomination/{nomination_id}',
            data={
                '_csrf_token': 'test-csrf',
                'status': status,
                'selected_session_id': str(session_id),
            },
            follow_redirects=True,
        )

    def test_same_existing_title_links_without_resending(self):
        session_id, nomination_id = self.add_session_and_nomination(
            session_title='The matrix', nomination_title='The Matrix'
        )
        original_notifier = app_module.notify_bookers_of_film_title
        app_module.notify_bookers_of_film_title = lambda unused: self.fail(
            'An unchanged title must not resend announcements.'
        )
        try:
            response = self.post_nomination(nomination_id, session_id)
        finally:
            app_module.notify_bookers_of_film_title = original_notifier

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No duplicate announcement email was sent.', response.data)
        with app_module.app.app_context():
            nomination = app_module.db.session.get(app_module.FilmNomination, nomination_id)
            self.assertEqual(nomination.status, 'selected')
            self.assertEqual(nomination.selected_session_id, session_id)

    def test_different_existing_title_is_not_overwritten(self):
        session_id, nomination_id = self.add_session_and_nomination(
            session_title='Existing Film', nomination_title='Different Film'
        )
        response = self.post_nomination(nomination_id, session_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'nothing was overwritten', response.data)
        with app_module.app.app_context():
            film_session = app_module.db.session.get(app_module.FilmSession, session_id)
            nomination = app_module.db.session.get(app_module.FilmNomination, nomination_id)
            self.assertEqual(film_session.film_title, 'Existing Film')
            self.assertEqual(nomination.status, 'new')
            self.assertIsNone(nomination.selected_session_id)

    def test_new_title_is_published_and_announced_once(self):
        session_id, nomination_id = self.add_session_and_nomination()
        calls = []
        original_notifier = app_module.notify_bookers_of_film_title
        app_module.notify_bookers_of_film_title = lambda film_session: (
            calls.append(film_session.id) or (1, 0, False)
        )
        try:
            response = self.post_nomination(nomination_id, session_id)
        finally:
            app_module.notify_bookers_of_film_title = original_notifier

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [session_id])
        with app_module.app.app_context():
            film_session = app_module.db.session.get(app_module.FilmSession, session_id)
            self.assertEqual(film_session.film_title, 'The Matrix')

    def test_duplicate_booking_email_receives_one_announcement(self):
        session_id, _ = self.add_session_and_nomination(session_title='The Matrix')
        with app_module.app.app_context():
            app_module.db.session.add_all([
                app_module.FilmBooking(
                    film_session_id=session_id,
                    full_name='First booking',
                    email='same@example.org',
                    is_adult=True,
                    cancel_token='token-one',
                ),
                app_module.FilmBooking(
                    film_session_id=session_id,
                    full_name='Second booking',
                    email='SAME@example.org',
                    is_adult=True,
                    cancel_token='token-two',
                ),
            ])
            app_module.db.session.commit()

            deliveries = []
            original_sender = app_module.send_rich_email
            app_module.send_rich_email = lambda address, subject, html: (
                deliveries.append(address) or True
            )
            try:
                sent, failed, skipped = app_module.notify_bookers_of_film_title(
                    app_module.db.session.get(app_module.FilmSession, session_id)
                )
            finally:
                app_module.send_rich_email = original_sender

            self.assertEqual((sent, failed), (1, 0))
            self.assertEqual(deliveries, ['same@example.org'])
            self.assertEqual(
                app_module.FilmTitleRecipient.query.filter_by(
                    film_session_id=session_id, film_title='The Matrix'
                ).count(),
                1,
            )

    def test_every_film_booking_creates_contact_with_consent_status(self):
        with app_module.app.app_context():
            opted_in = app_module.FilmBooking(
                film_session_id=self.add_session_and_nomination()[0],
                full_name='Consenting attendee',
                email='Consent@Example.org',
                is_adult=True,
                future_updates_opt_in=True,
                cancel_token='contact-token-one',
            )
            opted_out = app_module.FilmBooking(
                film_session_id=opted_in.film_session_id,
                full_name='Private attendee',
                email='private@example.org',
                is_adult=True,
                future_updates_opt_in=False,
                cancel_token='contact-token-two',
            )
            app_module.db.session.add_all([opted_in, opted_out])
            app_module.db.session.flush()

            app_module.record_film_booking_contact(opted_in)
            app_module.record_film_booking_contact(opted_out)
            app_module.db.session.commit()

            contacts = {
                item.email: item for item in app_module.FilmContact.query.all()
            }
            self.assertEqual(len(contacts), 2)
            self.assertTrue(contacts['consent@example.org'].can_invite)
            self.assertFalse(contacts['private@example.org'].can_invite)

    def test_sync_backfills_all_contacts_without_duplicates(self):
        with app_module.app.app_context():
            session_id, _ = self.add_session_and_nomination()
            app_module.db.session.add_all([
                app_module.FilmBooking(
                    film_session_id=session_id,
                    full_name='Earlier attendee',
                    email='earlier@example.org',
                    is_adult=True,
                    future_updates_opt_in=True,
                    cancel_token='backfill-token-one',
                ),
                app_module.FilmBooking(
                    film_session_id=session_id,
                    full_name='Repeat attendee',
                    email='EARLIER@example.org',
                    is_adult=True,
                    future_updates_opt_in=True,
                    cancel_token='backfill-token-two',
                ),
                app_module.FilmBooking(
                    film_session_id=session_id,
                    full_name='Did not consent',
                    email='no-consent@example.org',
                    is_adult=True,
                    future_updates_opt_in=False,
                    cancel_token='backfill-token-three',
                ),
            ])
            app_module.db.session.commit()

            app_module.sync_film_booking_contacts()
            app_module.db.session.commit()
            app_module.sync_film_booking_contacts()
            app_module.db.session.commit()

            contacts = {
                item.email: item for item in app_module.FilmContact.query.all()
            }
            self.assertEqual(len(contacts), 2)
            self.assertTrue(contacts['earlier@example.org'].can_invite)
            self.assertFalse(contacts['no-consent@example.org'].can_invite)

            # A later administrator decision must survive future app starts.
            contacts['earlier@example.org'].can_invite = False
            app_module.db.session.commit()
            app_module.sync_film_booking_contacts()
            app_module.db.session.commit()
            self.assertFalse(
                app_module.FilmContact.query.filter_by(
                    email='earlier@example.org'
                ).one().can_invite
            )

    def test_awss_sync_backfills_all_registrants_and_preserves_admin_choice(self):
        with app_module.app.app_context():
            workplace_session = app_module.WorkplaceSession(
                session_date=date(2031, 9, 27),
                max_attendees=15,
                is_bookable=True,
            )
            app_module.db.session.add(workplace_session)
            app_module.db.session.flush()
            app_module.db.session.add_all([
                app_module.WorkplaceBooking(
                    workplace_session_id=workplace_session.id,
                    full_name='First AWSS attendee',
                    email='AWSS@example.org',
                    phone='07000000001',
                    is_adult=True,
                    cancel_token='awss-contact-one',
                ),
                app_module.WorkplaceBooking(
                    workplace_session_id=workplace_session.id,
                    full_name='Repeat AWSS attendee',
                    email='awss@EXAMPLE.org',
                    phone='07000000002',
                    is_adult=True,
                    cancel_token='awss-contact-two',
                ),
            ])
            app_module.db.session.commit()

            self.assertEqual(app_module.sync_workplace_booking_contacts(), 1)
            app_module.db.session.commit()
            contact = app_module.WorkplaceContact.query.one()
            self.assertEqual(contact.email, 'awss@example.org')
            self.assertTrue(contact.can_invite)

            contact.can_invite = False
            app_module.db.session.commit()
            self.assertEqual(app_module.sync_workplace_booking_contacts(), 0)
            app_module.db.session.commit()
            self.assertFalse(app_module.WorkplaceContact.query.one().can_invite)


if __name__ == '__main__':
    unittest.main()
