# JET options (admin interface)

JET_SIDE_MENU_COMPACT = True
JET_DEFAULT_THEME = 'jdav-green'
JET_CHANGE_FORM_SIBLING_LINKS = False

JET_SIDE_MENU_ITEMS = [
    {'app_label': 'logindata', 'permissions': ['auth'], 'items': [
        {'name': 'authgroup', 'permissions': ['auth.group'] },
        {'name': 'logindatum', 'permissions': ['auth.user']},
        {'name': 'registrationpassword', 'permissions': ['auth.user']},
    ]},
    {'app_label': 'django_celery_beat', 'permissions': ['django_celery_beat'], 'items': [
        {'name': 'crontabschedule'},
        {'name': 'clockedschedule'},
        {'name': 'intervalschedule'},
        {'name': 'periodictask'},
        {'name': 'solarschedule'},
    ]},
    {'app_label': 'ludwigsburgalpin', 'permissions': ['ludwigsburgalpin'], 'items': [
        {'name': 'termin', 'permissions': ['ludwigsburgalpin.view_termin']},
    ]},
    {'app_label': 'mailer', 'items': [
        {'name': 'message', 'permissions': ['mailer.view_message']},
        {'name': 'emailaddress', 'permissions': ['mailer.view_emailaddress']},
    ]},
    {'app_label': 'finance', 'items': [
        {'name': 'statementunsubmitted', 'permissions': ['finance.view_statementunsubmitted']},
        {'name': 'statementsubmitted', 'permissions': ['finance.view_statementsubmitted']},
        {'name': 'statementconfirmed', 'permissions': ['finance.view_statementconfirmed']},
        {'name': 'ledger', 'permissions': ['finance.view_ledger']},
        {'name': 'bill', 'permissions': ['finance.view_bill', 'finance.view_bill_admin']},
        {'name': 'transaction', 'permissions': ['finance.view_transaction']},
    ]},
    {'app_label': 'members', 'items': [
        {'name': 'member', 'permissions': ['members.view_member']},
        {'name': 'membernotelist', 'permissions': ['members.view_membernotelist']},
        {'name': 'freizeit', 'permissions': ['members.view_freizeit']},
        {'name': 'klettertreff', 'permissions': ['members.view_klettertreff']},
    ]},
    {'label': 'Gruppenverwaltung', 'app_label': 'members', 'permissions': ['members.view_group'], 'items': [
        {'name': 'group', 'permissions': ['members.view_group']},
        {'name': 'activitycategory', 'permissions': ['members.view_activitycategory']},
        {'name': 'trainingcategory', 'permissions': ['members.view_trainingcategory']},
    ]},
    {'label': 'Neue Mitglieder', 'app_label': 'members', 'permissions': ['members.view_memberunconfirmedproxy'], 'items': [
        {'name': 'memberunconfirmedproxy', 'permissions': ['members.view_memberunconfirmedproxy']},
        {'name': 'memberwaitinglist', 'permissions': ['members.view_memberwaitinglist']},
    ]},
    {'app_label': 'material', 'permissions': ['material'], 'items': [
        {'name': 'materialcategory', 'permissions': ['material.view_materialcategory']},
        {'name': 'materialpart', 'permissions': ['material.view_materialpart']},
    ]},
    {'label': 'Externe Links', 'items' : [
        { 'label': 'Nextcloud', 'url': CLOUD_LINK },
        { 'label': 'DAV 360', 'url': DAV_360_LINK },
        { 'label': 'Julei-Wiki', 'url': WIKI_LINK },
    ]},
]
