"""Compile every `.po` in the project to the `.mo` Django actually reads.

`manage.py compilemessages` shells out to gettext's `msgfmt`, which a minimal container does
not carry, and the catalogues are not committed (`*.mo` is in .gitignore) — so without this a
test that asserts a German string sees the English msgid and fails for a reason that has
nothing to do with the change under test. That is one real failure in `contrib` today.

Used only as the fallback: where `msgfmt` exists, `.agent/validation.sh` calls Django, so the
compiler that produced the catalogues in CI is the one that produced them here.
"""

import pathlib
import sys

import polib

root = pathlib.Path(__file__).resolve().parent.parent / "jdav_web"
catalogues = sorted(root.glob("**/locale/*/LC_MESSAGES/*.po"))

if not catalogues:
    sys.exit("no .po files found under jdav_web/ — has the layout moved?")

for po_path in catalogues:
    mo_path = po_path.with_suffix(".mo")
    polib.pofile(str(po_path)).save_as_mofile(str(mo_path))
    print(f"compiled {po_path.relative_to(root)}")
