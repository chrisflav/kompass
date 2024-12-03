# contact data

SEKTION = "Heidelberg"
SEKTION_STREET = "Harbigweg 20"
SEKTION_TOWN = "69124 Heidelberg"
SEKTION_TELEPHONE = "06221 284076"
SEKTION_TELEFAX = "06221 437338"
SEKTION_CONTACT_MAIL = "geschaeftsstelle@alpenverein-heidelberg.de"
SEKTION_BOARD_MAIL = "vorstand@alpenverein-heidelberg.de"
SEKTION_CRISIS_INTERVENTION_MAIL = "krisenmanagement@alpenverein-heidelberg.de"
SEKTION_IBAN = "DE22 6729 0000 0000 1019 40"
SEKTION_ACCOUNT_HOLDER = "Deutscher Alpenverein Sektion Heidelberg 1869"

RESPONSIBLE_MAIL = "jugendreferat@jdav-hd.de"
DIGITAL_MAIL = "digitales@jdav-hd.de"

# LJP

V32_HEAD_ORGANISATION = """JDAV Baden-Württemberg
Rotebühlstraße 59A
70178 Stuttgart

info@jdav-bw.de
0711 - 49 09 46 00"""

LJP_CONTRIBUTION_PER_DAY = 25

# echo

ECHO_PASSWORD_BIRTHDATE_FORMAT = '%d.%m.%Y'
ECHO_GRACE_PERIOD = 30

# misc

CONGRATULATE_MEMBERS_MAX = 10
MAX_AGE_GOOD_CONDUCT_CERTIFICATE_MONTHS = 24
ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER = ('alpenverein-heidelberg.de', )

# mail mode

SEND_FROM_ASSOCIATION_EMAIL = os.environ.get('SEND_FROM_ASSOCIATION_EMAIL', '0') == '1'

# finance

ALLOWANCE_PER_DAY = 22
MAX_NIGHT_COST = 11

CLOUD_LINK = 'https://nc.cloud-jdav-hd.de'
DAV_360_LINK = 'https://dav360.de'
WIKI_LINK = 'https://davbgs.sharepoint.com/sites/S-114-O-JDAV-Jugendreferat'

# Admin setup

ADMINS = (('admin', 'christian@merten-moser.de'),)

# Waiting list configuration parameters, all numbers are in days

GRACE_PERIOD_WAITING_CONFIRMATION = 30
WAITING_CONFIRMATION_FREQUENCY = 90
CONFIRMATION_REMINDER_FREQUENCY = 30
MAX_REMINDER_COUNT = 3

# testing

TEST_MAIL = "post@flavigny.de"

REGISTRATION_FORM_DOWNLOAD_LINK = 'https://nc.cloud-jdav-hd.de'

DOMAIN = os.environ.get('DOMAIN', 'example.com')

STARTPAGE_REDIRECT_URL = 'https://jdav-hd.de'
ROOT_SECTION = os.environ.get('ROOT_SECTION', 'wir')
RECENT_SECTION = 'aktuelles'
REPORTS_SECTION = 'berichte'
