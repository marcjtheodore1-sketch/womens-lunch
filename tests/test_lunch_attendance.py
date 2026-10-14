"""Attendance evidence, timing and shared-admin saves against an isolated DB."""
import csv
import io
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['ENABLE_EMAIL'] = 'false'
import app as lunch_app


class LunchAttendanceTests(unittest.TestCase):
    def setUp(self):
        self.context = lunch_app.app.app_context()
        self.context.push()
        lunch_app.app.config.update(TESTING=True, SECRET_KEY='attendance-tests')
        lunch_app.db.drop_all()
        lunch_app.db.create_all()
        self.client = lunch_app.app.test_client()
        with self.client.session_transaction() as admin:
            admin['admin_logged_in'] = True
            admin['_csrf_token'] = 'attendance-csrf'
        self.lunch = lunch_app.LunchDate(lunch_date=date(2026, 10, 3))
        lunch_app.db.session.add(self.lunch)
        lunch_app.db.session.flush()
        self.booking = self.add_booking()

    def tearDown(self):
        lunch_app.db.session.remove()
        lunch_app.db.drop_all()
        self.context.pop()

    def add_booking(self, **values):
        defaults = dict(lunch_date_id=self.lunch.id, first_name='Alex', last_name='Example', email='alex@example.org', main_course='', drink='')
        defaults.update(values)
        booking = lunch_app.Booking(**defaults)
        lunch_app.db.session.add(booking)
        lunch_app.db.session.commit()
        return booking

    def save(self, **values):
        payload = dict(status='attended', note='', version=0)
        payload.update(values)
        return self.client.post(f'/api/admin/lunch-attendance/booking/{self.booking.id}', json=payload, headers={'X-CSRF-Token': 'attendance-csrf'})

    def test_unchecked_is_unknown_and_cancelled_rows_are_retained(self):
        self.add_booking(email='early@example.org', cancelled_at=datetime(2026, 10, 2, 11))
        self.add_booking(email='late@example.org', cancelled_at=datetime(2026, 10, 2, 11, 0, 1))
        response = self.client.get(f'/api/admin/lunch-attendance/{self.lunch.id}')
        self.assertEqual(response.json['counts'], dict(unrecorded=1, attended=0, no_show=0, cancelled=1, late_cancelled=1))
        self.assertEqual(len(response.json['records']), 3)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_save_correct_clear_and_audit_without_email_or_booking_changes(self):
        with patch.object(lunch_app, 'send_confirmation_email') as mail:
            first = self.save(status='no_show', note='Did not arrive')
            self.assertEqual(first.status_code, 200)
            second = self.save(status='attended', note='Arrived later', version=1)
            self.assertEqual(second.json['version'], 2)
            cleared = self.save(status=None, note='', version=2)
            self.assertEqual(cleared.json['status'], 'unrecorded')
            mail.assert_not_called()
        changes = self.client.get(f'/api/admin/lunch-attendance/booking/{self.booking.id}/changes').json
        self.assertEqual(len(changes), 3)
        self.assertEqual(changes[1]['note'], 'Arrived later')
        self.assertIsNone(lunch_app.db.session.get(lunch_app.Booking, self.booking.id).cancelled_at)

    def test_stale_edit_does_not_overwrite_another_host(self):
        self.assertEqual(self.save(note='Saved by first host').status_code, 200)
        self.assertEqual(self.save(status='no_show', note='Stale edit').status_code, 409)
        record = self.client.get(f'/api/admin/lunch-attendance/{self.lunch.id}').json['records'][0]
        self.assertEqual(record['status'], 'attended')
        self.assertEqual(record['note'], 'Saved by first host')
        self.assertEqual(lunch_app.LunchAttendanceChange.query.count(), 1)

    def test_cancelled_person_is_not_counted_as_missing_and_clear_restores_automatic(self):
        self.booking.cancelled_at = datetime(2026, 10, 3, 9)
        lunch_app.db.session.commit()
        self.assertEqual(self.save(status='no_show').status_code, 400)
        self.assertEqual(self.save(status='cancelled', note='Told Claire two days before').json['status'], 'cancelled')
        self.assertEqual(self.save(status=None, version=1).json['status'], 'late_cancelled')

    def test_future_and_during_lunch_absences_are_blocked_using_london_time(self):
        self.lunch.lunch_date = date(2099, 10, 3)
        lunch_app.db.session.commit()
        self.assertEqual(self.save().status_code, 400)
        self.lunch.lunch_date = date(2026, 10, 3)
        lunch_app.db.session.commit()
        with patch.object(lunch_app, 'datetime', wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 10, 3, 11, 30, tzinfo=timezone.utc)
            self.assertEqual(self.save(status='no_show').status_code, 400)
            self.assertEqual(self.save(status='attended').status_code, 200)

    def test_cancellation_window_handles_bst_change(self):
        self.lunch.lunch_date = date(2026, 10, 25)  # First lunch after clocks go back.
        self.booking.cancelled_at = datetime(2026, 10, 24, 12)  # Exactly 24 real hours.
        lunch_app.db.session.commit()
        self.assertEqual(lunch_app.lunch_attendance_status(self.booking), 'cancelled')
        self.booking.cancelled_at += timedelta(seconds=1)
        self.assertEqual(lunch_app.lunch_attendance_status(self.booking), 'late_cancelled')

    def test_auth_csrf_and_payload_validation(self):
        anonymous = lunch_app.app.test_client()
        for path in ['/dates', '/history', f'/{self.lunch.id}', f'/{self.lunch.id}/export', f'/booking/{self.booking.id}/changes']:
            self.assertEqual(anonymous.get('/api/admin/lunch-attendance' + path).status_code, 302)
        self.assertEqual(anonymous.post(f'/api/admin/lunch-attendance/booking/{self.booking.id}', json={}).status_code, 302)
        self.assertEqual(self.client.post(f'/api/admin/lunch-attendance/booking/{self.booking.id}', json={}).status_code, 400)
        for payload in [dict(status=[]), dict(status=False), dict(status='unrecorded'), dict(note='x' * 1001), dict(version=True), dict(version=-1)]:
            self.assertEqual(self.save(**payload).status_code, 400)

    def test_history_normalises_email_keeps_unknown_and_excludes_future(self):
        self.add_booking(email=' ALEX@EXAMPLE.ORG ', attendance_status='no_show')
        future = lunch_app.LunchDate(lunch_date=date(2099, 1, 1))
        old = lunch_app.LunchDate(lunch_date=date(2020, 1, 1))
        lunch_app.db.session.add_all([future, old])
        lunch_app.db.session.commit()
        self.add_booking(lunch_date_id=future.id, attendance_status='no_show')
        self.add_booking(lunch_date_id=old.id, attendance_status='no_show')
        history = self.client.get('/api/admin/lunch-attendance/history').json
        self.assertEqual(len(history['people']), 1)
        self.assertEqual(history['people'][0]['counts']['no_show'], 1)
        self.assertEqual(history['people'][0]['counts']['unrecorded'], 1)
        self.assertEqual(len(history['people'][0]['records']), 2)

    def test_export_protects_spreadsheet_formulas_and_includes_cancellations(self):
        self.booking.first_name = '=1+1'
        self.booking.attendance_note = '+formula'
        self.booking.cancelled_at = datetime(2026, 10, 3, 9)
        lunch_app.db.session.commit()
        response = self.client.get(f'/api/admin/lunch-attendance/{self.lunch.id}/export')
        rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual(rows[1][1], "'=1+1 Example")
        self.assertEqual(rows[1][3], 'Late cancellation')
        self.assertEqual(rows[1][4], "'+formula")
        self.assertIn('10:00:00+01:00', rows[1][5])

    def test_migration_keeps_existing_booking_and_adds_unknown_attendance(self):
        from sqlalchemy import text
        lunch_app.db.drop_all()
        lunch_app.db.session.execute(text('CREATE TABLE booking (id INTEGER PRIMARY KEY, additional_info TEXT)'))
        lunch_app.db.session.execute(text("INSERT INTO booking VALUES (1, 'Keep existing details')"))
        lunch_app.db.session.commit()
        added = lunch_app.ensure_booking_columns()
        self.assertIn('attendance_status', added)
        row = lunch_app.db.session.execute(text('SELECT additional_info, attendance_status, attendance_note, attendance_version FROM booking')).one()
        self.assertEqual(tuple(row), ('Keep existing details', None, None, 0))
        self.assertEqual(lunch_app.ensure_booking_columns(), [])


if __name__ == '__main__':
    unittest.main()
