"""Exercise lunch booking changes against an isolated database, without email."""
import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch


TEST_DATABASE = tempfile.mktemp(prefix='lagc-lunch-test-', suffix='.sqlite')
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DATABASE}'
os.environ['ENABLE_EMAIL'] = 'false'

import app as app_module


class WomensLunchBookingTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, SECRET_KEY='lunch-test')
        self.client = app_module.app.test_client()
        with app_module.app.app_context():
            app_module.db.drop_all()
            app_module.db.create_all()
            lunch = app_module.LunchDate(
                lunch_date=date.today() + timedelta(days=7),
                is_bookable=True,
                max_attendees=12,
            )
            app_module.db.session.add(lunch)
            app_module.db.session.commit()
            self.lunch_id = lunch.id

    def book(self, email_results=None, **changes):
        payload = {
            'lunch_date_id': self.lunch_id,
            'first_name': 'Test',
            'last_name': 'Attendee',
            'email': 'attendee@example.org',
            'is_first_time': True,
        }
        payload.update(changes)
        # Capture both confirmation and admin notification. Never send a test email.
        with patch.object(app_module, 'send_confirmation_email', side_effect=email_results or [True, True]) as sender:
            response = self.client.post('/api/book', json=payload)
        return response, sender

    def test_failed_emails_preserve_booking_and_report_failure(self):
        response, sender = self.book(email_results=[False, False])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['confirmation_email_sent'])
        self.assertFalse(response.json['admin_email_sent'])
        self.assertEqual(sender.call_count, 2)
        with app_module.app.app_context():
            booking = app_module.Booking.query.one()
            self.assertEqual(booking.confirmation_email_status, 'failed')
            self.assertEqual(booking.admin_email_status, 'failed')
        with self.client.session_transaction() as browser_session:
            browser_session['admin_logged_in'] = True
        self.assertEqual(self.client.get('/api/admin/bookings').json[0]['confirmation_email_status'], 'failed')
        duplicate, _ = self.book()
        self.assertEqual(duplicate.status_code, 409)

    def test_delivery_results_are_tracked_separately(self):
        response, _ = self.book(email_results=[True, False])
        self.assertTrue(response.json['confirmation_email_sent'])
        self.assertFalse(response.json['admin_email_sent'])
        with app_module.app.app_context():
            booking = app_module.Booking.query.one()
            self.assertEqual(booking.confirmation_email_status, 'accepted')
            self.assertEqual(booking.admin_email_status, 'failed')

    def test_disabled_email_is_not_reported_as_sent(self):
        with patch.dict(app_module.app.config, ENABLE_EMAIL=False), patch.object(app_module.smtplib, 'SMTP') as smtp:
            self.assertFalse(app_module.send_confirmation_email('attendee@example.org', 'Booking', '<p>Booking</p>'))
            smtp.assert_not_called()

    def test_authentication_failure_does_not_send_message(self):
        with patch.dict(app_module.app.config, ENABLE_EMAIL=True, SMTP_USER='sender@example.org', SMTP_PASSWORD='invalid', SMTP_FROM='sender@example.org', SMTP_PORT=587), patch.object(app_module.smtplib, 'SMTP') as smtp:
            connection = smtp.return_value
            connection.login.side_effect = app_module.smtplib.SMTPAuthenticationError(535, b'Credentials rejected')
            self.assertFalse(app_module.send_confirmation_email('attendee@example.org', 'Booking', '<p>Booking</p>'))
            connection.send_message.assert_not_called()
            self.assertEqual(smtp.call_args.kwargs['timeout'], 15)
            self.assertTrue(connection.starttls.call_args.kwargs['context'].check_hostname)

    def test_accepted_email_uses_tls_and_checks_recipient_acceptance(self):
        with patch.dict(app_module.app.config, ENABLE_EMAIL=True, SMTP_USER='sender@example.org', SMTP_PASSWORD='application-password', SMTP_FROM='sender@example.org', SMTP_PORT=587), patch.object(app_module.smtplib, 'SMTP') as smtp:
            connection = smtp.return_value
            connection.send_message.return_value = {}
            self.assertTrue(app_module.send_confirmation_email('attendee@example.org', 'Booking', '<p>Booking</p>'))
            connection.starttls.assert_called_once()
            connection.send_message.return_value = {'attendee@example.org': (550, b'Rejected')}
            self.assertFalse(app_module.send_confirmation_email('attendee@example.org', 'Booking', '<p>Booking</p>'))

    def test_delivery_migration_preserves_legacy_rows_and_unknown_status(self):
        from sqlalchemy import text
        with app_module.app.app_context():
            app_module.db.drop_all()
            app_module.db.session.execute(text('CREATE TABLE booking (id INTEGER PRIMARY KEY, additional_info TEXT)'))
            app_module.db.session.execute(text("INSERT INTO booking (id, additional_info) VALUES (1, 'Existing booking')"))
            app_module.db.session.commit()
            added = app_module.ensure_booking_columns()
            self.assertIn('confirmation_email_status', added)
            self.assertIn('admin_email_status', added)
            self.assertEqual(app_module.db.session.execute(text('SELECT additional_info, confirmation_email_status, admin_email_status FROM booking')).one(), ('Existing booking', None, None))
            self.assertEqual(app_module.ensure_booking_columns(), [])

    def test_activities_transport_uses_existing_sender_and_lunch_reply_address(self):
        with patch.dict(app_module.app.config, ENABLE_EMAIL=True, LUNCH_EMAIL_TRANSPORT='activities', ACTIVITIES_SMTP_HOST='smtp.example.org', ACTIVITIES_SMTP_PORT=587, ACTIVITIES_SMTP_USER='activities@example.org', ACTIVITIES_SMTP_PASSWORD='existing-password', ACTIVITIES_SMTP_FROM='activities@example.org', ADMIN_EMAIL='lunch@example.org'), patch.object(app_module.smtplib, 'SMTP') as smtp:
            connection = smtp.return_value
            connection.send_message.return_value = {}
            self.assertTrue(app_module.send_confirmation_email('attendee@example.org', 'Booking', '<p>Booking</p>'))
            connection.login.assert_called_once_with('activities@example.org', 'existingpassword')
            message = connection.send_message.call_args.args[0]
            self.assertEqual(message['From'], 'activities@example.org')
            self.assertEqual(message['Reply-To'], 'lunch@example.org')
            self.assertEqual(message['To'], 'attendee@example.org')

    def test_food_only_preference_reaches_database_confirmation_and_admin(self):
        response, sender = self.book(main_course='Vegetarian pie', dietary_requirements='No nuts')
        self.assertEqual(response.status_code, 200)
        confirmation = response.json['confirmation_message']
        self.assertIn('Food preference: Vegetarian pie', confirmation)
        self.assertIn('No nuts', confirmation)
        self.assertIn('The charity will not purchase alcohol', confirmation)
        self.assertIn('Meet us directly at the pub at 12pm', confirmation)
        self.assertNotIn('Holy Sepulchre', confirmation)
        self.assertIn('Penderel’s Oak', confirmation)
        self.assertIn('283-288 High Holborn, London WC1V 7HP', confirmation)
        self.assertIn('https://www.jdwetherspoon.com/pub-menus/penderels-oak-holborn/', confirmation)
        self.assertIn('wheelchair-accessible toilet on the ground floor', confirmation)
        self.assertNotIn('Cittie of Yorke', confirmation)
        self.assertEqual(sender.call_count, 2)
        self.assertIn('Food: Vegetarian pie', sender.call_args_list[1].args[2])
        with app_module.app.app_context():
            booking = app_module.Booking.query.one()
            self.assertEqual(booking.main_course, 'Vegetarian pie')
            self.assertEqual(booking.drink, '')
            self.assertEqual(booking.meeting_preference, 'pub')
        with self.client.session_transaction() as browser_session:
            browser_session['admin_logged_in'] = True
        admin_booking = self.client.get('/api/admin/bookings').json[0]
        self.assertEqual(admin_booking['main_course'], 'Vegetarian pie')
        self.assertEqual(admin_booking['drink'], '')

    def test_preferences_are_optional_and_old_church_payload_meets_at_pub(self):
        response, unused_sender = self.book(meeting_preference='church')
        self.assertEqual(response.status_code, 200)
        with app_module.app.app_context():
            booking = app_module.Booking.query.one()
            self.assertEqual(booking.meeting_preference, 'pub')
            self.assertEqual(booking.main_course, '')

    def test_attendee_text_is_escaped_in_confirmation(self):
        response, unused_sender = self.book(
            first_name='<script>test</script>',
            main_course='<img src=x onerror=alert(1)>',
            drink='Tea & juice',
            dietary_requirements='<b>No nuts</b>',
        )
        self.assertEqual(response.status_code, 200)
        confirmation = response.json['confirmation_message']
        self.assertNotIn('<script>', confirmation)
        self.assertNotIn('<img src=x', confirmation)
        self.assertIn('Tea &amp; juice', confirmation)
        self.assertIn('&lt;b&gt;No nuts&lt;/b&gt;', confirmation)

    def test_oversized_preference_is_rejected_without_creating_booking(self):
        for field in ('main_course', 'drink'):
            with self.subTest(field=field):
                response, sender = self.book(**{field: 'x' * 201})
                self.assertEqual(response.status_code, 400)
                sender.assert_not_called()
                with app_module.app.app_context():
                    self.assertEqual(app_module.Booking.query.count(), 0)

    def test_booking_page_offers_preferences_and_no_church_choice(self):
        page = self.client.get('/womens-lunch/book').get_data(as_text=True)
        self.assertIn('id="main-course"', page)
        self.assertIn('id="drink"', page)
        self.assertIn('The charity will not purchase alcohol', page)
        self.assertNotIn('meeting-preference', page)
        self.assertNotIn('Holy Sepulchre', page)
        self.assertIn('Penderel’s Oak', page)
        self.assertIn('283-288 High Holborn, London WC1V 7HP', page)
        self.assertIn('https://www.jdwetherspoon.com/pub-menus/penderels-oak-holborn/', page)
        self.assertIn('wheelchair-accessible toilet on the ground floor', page)
        self.assertNotIn('Cittie of Yorke', page)

    def test_activities_gateway_names_the_new_venue(self):
        page = self.client.get('/').get_data(as_text=True)
        self.assertIn('Penderel’s Oak, Holborn', page)
        self.assertNotIn('Cittie of Yorke', page)


if __name__ == '__main__':
    unittest.main()
