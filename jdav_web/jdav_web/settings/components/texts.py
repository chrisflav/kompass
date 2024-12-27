# mail texts

CONFIRM_MAIL_TEXT = """Hallo {name},

du hast bei der JDAV %(SEKTION)s eine E-Mail Adresse hinterlegt. Da bei uns alle Kommunikation
per Email funktioniert, brauchen wir eine Bestätigung {whattoconfirm}. Dazu klicke bitte einfach auf
folgenden Link:

{link}

Viele Grüße
Deine JDAV %(SEKTION)s""" % { 'SEKTION': SEKTION }

NEW_UNCONFIRMED_REGISTRATION = """Hallo {name},

für deine Gruppe {group} liegt eine neue unbestätigte Reservierung vor. Die Person hat bereits ihre
E-Mailadressen bestätigt und ihr Anmeldeformular hochgeladen. Bitte prüfe die Registrierung eingehend und
bestätige falls möglich. Zu der Registrierung kommst du hier:

{link}

Viele Grüße
Dein KOMPASS"""

GROUP_TIME_AVAILABLE_TEXT = """Die Gruppenstunde findet jeden {weekday} von {start_time} bis {end_time} Uhr statt."""

GROUP_TIME_UNAVAILABLE_TEXT = """Bitte erfrage die Gruppenzeiten bei der Gruppenleitung ({contact_email})."""

INVITE_TEXT = """Hallo {{name}},

wir haben gute Neuigkeiten für dich. Es ist ein Platz in der Jugendgruppe {group_name} {group_link}freigeworden.
{group_time}

Bitte kontaktiere die Gruppenleitung ({contact_email}) für alle weiteren Absprachen.

Wenn du nach der Schnupperstunde beschließt der Gruppe beizutreten, benötigen wir noch ein paar
Informationen und eine schriftliche Anmeldebestätigung von dir. Das kannst du alles über folgenden Link erledigen:

{{link}}

Du siehst dort auch die Daten, die du bei deiner Eintragung auf die Warteliste angegeben hast. Bitte
überprüfe, ob die Daten noch stimmen und ändere sie bei Bedarf ab.

Falls du zu dem obigen Termin keine Zeit hast oder dich ganz von der Warteliste abmelden möchtest,
lehne bitte diese Einladung unter folgendem Link ab:

{{invitation_reject_link}}

Bei Fragen, wende dich gerne an %(RESPONSIBLE_MAIL)s.

Viele Grüße
Deine JDAV %(SEKTION)s""" % { 'SEKTION': SEKTION, 'RESPONSIBLE_MAIL': RESPONSIBLE_MAIL,
                              'REGISTRATION_FORM_DOWNLOAD_LINK': REGISTRATION_FORM_DOWNLOAD_LINK }


LEAVE_WAITINGLIST_TEXT = """Hallo {name},

du hast dich erfolgreich von der Warteliste abgemeldet. Falls du zu einem späteren
Zeitpunkt wieder der Warteliste beitreten möchtest, kannst du das über unsere Webseite machen.

Falls du dich nicht selbst abgemeldet hast, wende dich bitte umgehend an %(RESPONSIBLE_MAIL)s.

Viele Grüße
Deine JDAV %(SEKTION)s""" % { 'SEKTION': SEKTION, 'RESPONSIBLE_MAIL': RESPONSIBLE_MAIL }


WAIT_CONFIRMATION_TEXT = """Hallo {name},

leider können wir dir zur Zeit noch keinen Platz in einer Jugendgruppe anbieten. Da wir
sehr viele Interessenten haben und wir möglichst vielen die Möglichkeit bieten möchten, an
einer Jugendgruppe teilhaben zu können, fragen wir regelmäßig alle Personen auf der
Warteliste ab, ob sie noch Interesse haben.

Wenn du weiterhin auf der Warteliste bleiben möchtest, klicke auf den folgenden Link:

{link}

Das ist Erinnerung Nummer {reminder} von {max_reminder_count}. Nach Erinnerung Nummer {max_reminder_count} wirst
du automatisch entfernt.

Viele Grüße
Deine JDAV %(SEKTION)s""" % { 'SEKTION': SEKTION }


UNSUBSCRIBE_CONFIRMATION_TEXT = """Klicke auf den Link, um dich vom Newsletter der JDAV %(SEKTION)s abzumelden

{link}""" % { 'SEKTION': SEKTION }


NOTIFY_MOST_ACTIVE_TEXT = """Hallo {name}!

Herzlichen Glückwunsch, du hast im letzten Jahr zu den {congratulate_max} aktivsten
Mitgliedern der JDAV %(SEKTION)s gehört! Um genau zu sein beträgt dein Aktivitäts Wert
des letzten Jahres {score} Punkte. Das entspricht {level} Kletterer:innen. Damit warst du
im letzten Jahr das {position}aktivste Mitglied der JDAV %(SEKTION)s.


Auf ein weiteres aktives Jahr in der JDAV %(SEKTION)s.

Dein:e Jugendreferent:in""" % { 'SEKTION': SEKTION }


ECHO_TEXT = """Hallo {name},

um unsere Daten auf dem aktuellen Stand zu halten und sicherzugehen, dass du
weiterhin ein Teil unserer Jugendarbeit bleiben möchtest, brauchen wir eine
kurze Bestätigung von dir. Dafür besuche einfach diesen Link:

{link}

Dort kannst du deine Daten nach Eingabe eines Passworts überprüfen und ggf. ändern. Dein
Passwort ist dein Geburtsdatum. Wäre dein Geburtsdatum zum Beispiel der 4. Januar 1942,
so wäre dein Passwort: 04.01.1942

Falls du nicht innerhalb von 30 Tagen deine Daten bestätigst, gehen wir davon aus, dass du nicht mehr Teil
unserer Jugendarbeit sein möchtest. Dein Platz wird dann weitervergeben, deine Daten aus unserer Datenbank
gelöscht und du erhälst in Zukunft keine Mails mehr von uns.

Bei Fragen, wende dich gerne an %(RESPONSIBLE_MAIL)s.

Viele Grüße
Deine JDAV %(SEKTION)s""" % { 'SEKTION': SEKTION, 'RESPONSIBLE_MAIL': RESPONSIBLE_MAIL }


PREPEND_INCOMPLETE_REGISTRATION_TEXT = """WICHTIGE MITTEILUNG

Deine Anmeldung ist aktuell nicht vollständig. Bitte fülle umgehend das
Anmeldeformular aus und lasse es Deine*r Jugendleiter*in zukommen! Dieses
kannst Du unter folgendem Link herunterladen:

%(REGISTRATION_FORM_DOWNLOAD_LINK)s

****************

""" % { 'REGISTRATION_FORM_DOWNLOAD_LINK': REGISTRATION_FORM_DOWNLOAD_LINK }


MAIL_FOOTER = """


****************

Diese Email wurde über die Webseite der JDAV %(SEKTION)s
verschickt. Wenn Du in Zukunft keine Emails mehr erhalten möchtest,
kannst Du hier den Newsletter deabonnieren:

{link}""" % { 'SEKTION': SEKTION }


INVITE_AS_USER_TEXT = """Hallo {name},

du bist Jugendleiter*in in der Sektion %(SEKTION)s. Die Verwaltung unserer Jugendgruppen,
Ausfahrten und Finanzen erfolgt in unserer Online Plattform Kompass. Deine Stammdaten sind
dort bereits hinterlegt. Damit du dich auch anmelden kannst, folge bitte dem folgenden Link
und wähle ein Passwort.

{link}

Bei Fragen, wende dich gerne an %(RESPONSIBLE_MAIL)s.

Viele Grüße
Deine JDAV %(SEKTION)s""" % { 'SEKTION': SEKTION, 'RESPONSIBLE_MAIL': RESPONSIBLE_MAIL }


UPLOAD_REGISTRATION_FORM_TEXT = """Hallo {name},

vielen Dank für deine Anmeldung in der JDAV %(SEKTION)s. Bevor es richtig losgehen kann, brauchen
wir noch die Bestätigung deiner Daten und die Zustimmung zu unseren Teilnahmebedingungen.

Dafür kannst du das für dich vorausgefüllte Anmeldeformular unter folgendem Link herunterladen,
durchlesen und, falls du zustimmst, das unterschriebene Formular wieder dort hochladen.

{link}

Bist du noch nicht volljährig? Dann muss eine erziehungsberechtigte Person das Formular unterschreiben.

Bei Fragen, wende dich gerne an %(RESPONSIBLE_MAIL)s.

Viele Grüße
Deine JDAV %(SEKTION)s""" % { 'SEKTION': SEKTION, 'RESPONSIBLE_MAIL': RESPONSIBLE_MAIL }


ADDRESS = """JDAV %(SEKTION)s
%(STREET)s
%(PLACE)s""" % { 'SEKTION': SEKTION, 'STREET': SEKTION_STREET, 'PLACE': SEKTION_TOWN }
