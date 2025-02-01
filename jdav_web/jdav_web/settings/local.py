# contact data

SEKTION = get_var('section', 'name', default='Heyo')
SEKTION_STREET = get_var('section', 'street', default='Street')
SEKTION_TOWN = get_var('section', 'town', default='12345 Town')
SEKTION_TELEPHONE = get_var('section', 'telephone', default='0123456789')
SEKTION_TELEFAX = get_var('section', 'telefax', default=SEKTION_TELEPHONE)
SEKTION_CONTACT_MAIL = get_var('section', 'contact_mail', default='info@example.org')
SEKTION_BOARD_MAIL = get_var('section', 'board_mail', default=SEKTION_CONTACT_MAIL)
SEKTION_CRISIS_INTERVENTION_MAIL = get_var('section', 'crisis_intervention_mail',
                                           default=SEKTION_BOARD_MAIL)
SEKTION_IBAN = get_var('section', 'iban', default='Foo 123')
SEKTION_ACCOUNT_HOLDER = get_var('section', 'account_holder',
                                 default='Foo')

RESPONSIBLE_MAIL = get_var('section', 'responsible_mail', default='foo@example.org')
DIGITAL_MAIL = get_var('section', 'digital_mail', default='bar@example.org')

# LJP

V32_HEAD_ORGANISATION = get_var('LJP', 'v32_head_organisation', default='not configured')
LJP_CONTRIBUTION_PER_DAY = get_var('LJP', 'contribution_per_day', default=25)

# echo

# used to generate the personalized echo password
ECHO_PASSWORD_BIRTHDATE_FORMAT = get_var('echo', 'password_birthdate_format', default='%d.%m.%Y')
# grace period in days after which echo keys expire
ECHO_GRACE_PERIOD = get_var('echo', 'grace_period', default=30)

# Waiting list configuration parameters, all numbers are in days

GRACE_PERIOD_WAITING_CONFIRMATION = get_var('waitinglist', 'grace_period_confirmation', default=30)
WAITING_CONFIRMATION_FREQUENCY = get_var('waitinglist', 'confirmation_frequency', default=90)
CONFIRMATION_REMINDER_FREQUENCY = get_var('waitinglist', 'confirmation_reminder_frequency', default=30)
MAX_REMINDER_COUNT = get_var('waitinglist', 'max_reminder_count', default=3)

# misc

# the maximal number of members that get sent congratulations for highest activity on aprils fools day
CONGRATULATE_MEMBERS_MAX = get_var('misc', 'congratulate_members_max', default=10)
# expiry duration of a good conduct certificate in months
MAX_AGE_GOOD_CONDUCT_CERTIFICATE_MONTHS = get_var('misc', 'max_age_good_conduct_certificate_months', default=24)
# accepted email domains for inviting users
ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER = get_var('misc', 'allowed_email_domains_for_invite_as_user',
                                                   default=['example.org'])
# send all mails from the assocation's contact mail or from personal association mails
SEND_FROM_ASSOCIATION_EMAIL = get_var('misc', 'send_from_association_email', default=False)
# domain for association email and generated urls
DOMAIN = get_var('misc', 'domain', default='example.org')

# finance

ALLOWANCE_PER_DAY = get_var('finance', 'allowance_per_day', default=22)
MAX_NIGHT_COST = get_var('finance', 'max_night_cost', default=11)

# links

CLOUD_LINK = get_var('links', 'cloud', default='https://startpage.com')
DAV_360_LINK = get_var('links', 'dav_360', default='https://dav360.de')
WIKI_LINK = get_var('links', 'wiki', default='https://wikipedia.org')
DOCS_LINK = get_var('links', 'docs', default='https://github.com/chrisflav/kompass')
REGISTRATION_FORM_DOWNLOAD_LINK = get_var('links', 'registration_form', default='https://startpage.com')

# startpage

STARTPAGE_REDIRECT_URL = get_var('startpage', 'redirect_url', default='')
ROOT_SECTION = get_var('startpage', 'root_section', default='about')
RECENT_SECTION = get_var('startpage', 'recent_section', default='recent')
REPORTS_SECTION = get_var('startpage', 'reports_section', default='reports')

# testing

TEST_MAIL = get_var('testing', 'mail', default='test@localhost')
