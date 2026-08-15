# London Autism Group Charity Activities

A single Flask/PythonAnywhere service for the charity's Autistic Women's Lunch
and monthly Autistic Film Club.
It also hosts the charity's monthly Autistic Workplace Support Sessions.

## Features

- **Monthly Lunch Bookings**: Max 12 attendees per lunch
- **Menu Selection**: Attendees choose their meal and drink when booking
- **Budget**: £20 per person (main + non-alcoholic drink)
- **Venue**: Cittie of Yorke, Holborn
- **Booking Window**: Only the next upcoming lunch is bookable
- **Admin Panel**: Manage dates, view bookings, archive past events
- **Email Notifications**: Automatic confirmation emails
- **Activities Gateway**: Root page links to both activity websites
- **Autistic Film Club**: Six-month schedule, 15-place registration, film nominations and cancellations
- **Calendar Invitations**: Google Calendar link and universal `.ics` attachment
- **Film Club Support Planning**: Companion/carer details, responsibility information and party-size capacity counting
- **Film Club Admin**: Film Club-only bookings, nominations, rota, safeguarding guidance and CSV export
- **Optional Invitations**: A manual, one-use-per-session invitation tool for low numbers
- **Email Automation**: Editable confirmation copy, session-specific notes and film-announcement notifications
- **Film Club News**: Optional rotating homepage ticker managed from the Film Club admin area
- **Film Club Volunteer Briefings**: Private, session-scoped attendance and support briefings sent to the lead and that date's rota on the evening before
- **Autistic Workplace Support**: Rolling last-Saturday schedule with 15-place registration
- **Flexible Attendance**: Register for one-to-one mentoring, the confidential Speaking Circle or both
- **Workplace Support Planning**: Goals, access needs and companion/carer information in a dedicated admin area
- **Workplace Support Emails**: Confirmation, selected-time calendar invitation, cancellation and editable session notes
- **Workplace Support Invitations**: Every registration is retained in the AWSS contact list; admins can send a manual, one-use-per-session invitation for low-number dates
- **Workplace Support News**: Optional admin-managed homepage news ticker

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

The app will be available at http://localhost:5002

## URLs

- `/` - LAGC activities gateway
- `/womens-lunch` - existing Women's Lunch site
- `/film-club` - Film Club schedule, booking and nominations
- `/workplace-support` - Workplace Support schedule and registration
- `/admin` and `/admin/womens-lunch` - existing Women's Lunch administration
- `/admin/film-club` - Film Club-only administration
- `/admin/workplace-support` - Workplace Support-only administration

## Admin Access

- Film Club URL: `/admin/film-club`
- Workplace Support URL: `/admin/workplace-support`
- Women's Lunch URL: `/admin/womens-lunch`
- Film Club and Women's Lunch password: supplied through `ADMIN_PASSWORD`
- Workplace Support password: supplied separately through `WORKPLACE_ADMIN_PASSWORD`
- There are no production passwords in the source

## Environment Variables

- `SECRET_KEY`: a long, random value that keeps sessions secure
- `ADMIN_PASSWORD`: private admin password
- `WORKPLACE_ADMIN_PASSWORD`: separate password for Workplace Support administration
- `ADMIN_EMAIL`: legacy/general admin mailbox; kept separate from activity alerts
- `ACTIVITIES_ADMIN_EMAIL`: receives Film Club booking/nomination/cancellation and AWSS registration/cancellation alerts (`londonautismgroupcharity@gmail.com`)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`: Women's Lunch mail configuration (`wg.lagc@gmail.com`)
- `ACTIVITIES_SMTP_HOST`, `ACTIVITIES_SMTP_PORT`, `ACTIVITIES_SMTP_USER`, `ACTIVITIES_SMTP_PASSWORD`, `ACTIVITIES_SMTP_FROM`: Film Club and AWSS mail configuration (`miles.lagc@gmail.com`)
- `FILM_CLUB_LEAD_NAME`, `FILM_CLUB_LEAD_EMAIL`: the Film Club lead who receives every pre-event briefing (Itzi)
- `FILM_BRIEFING_SEND_HOUR`: earliest London-time hour at which the evening-before job sends (default `18`)
- `ENABLE_EMAIL`: set to `true` to enable email sending
- `COOKIE_SECURE`: set to `true` on the HTTPS production site

Copy the names from `.env.example` into the PythonAnywhere web app environment.
Do not upload a real `.env` file. Rotate the previously embedded Gmail app
password before enabling email.

## Deployment

The live PythonAnywhere checkout is:

```text
/home/londonautismgroupcharity/womens-lunch
```

The production database, email credentials, secret key and admin passwords are
stored only on PythonAnywhere. They are deliberately excluded from Git.

### Publishing a change to GitHub

From a local checkout, including when working with Codex or Claude:

```bash
git pull --ff-only origin main
# Make and test the changes.
git status
git diff
git add <the-files-you-intended-to-change>
git commit -m "Describe the change"
git push origin main
```

Do not commit `.env`, `instance/`, database files, deployment archives or the
Python virtual environment.

### Deploying the GitHub version to PythonAnywhere

Open a Bash console on PythonAnywhere and run:

```bash
cd /home/londonautismgroupcharity/womens-lunch
git status
git pull --ff-only origin main
```

If `requirements.txt` changed, also run:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Finally, open the PythonAnywhere **Web** tab and press **Reload** for
`londonautismgroupcharity.pythonanywhere.com`.

Use the included `wsgi.py` for local or conventional WSGI hosting. The live
PythonAnywhere WSGI file additionally supplies the private production
environment variables and must not be replaced with a public file.

### Film Club evening-before scheduled task

Run the idempotent Flask command each evening at or after the configured hour,
using the same environment as the web app:

```bash
cd /home/londonautismgroupcharity/womens-lunch
source venv/bin/activate
flask --app app send-film-briefings
```

The command uses `Europe/London`, selects only sessions occurring the following
day, and records each successful session/recipient delivery. It is therefore
safe for the scheduler to retry. A rota change made before it runs is included;
rerunning it that evening also delivers to a newly added volunteer without
resending to recipients already recorded.
