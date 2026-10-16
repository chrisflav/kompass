"""Making a regression test prove that it still guards something.

Three tests in the rules engine's first round passed while testing nothing of
the production path, and all three had the same shape: *the test exercised the
harness rather than the code*. A ``no_queries`` test called the rule inside a
guard the test itself had opened, which passes whether or not the production
code opens one. A loader-race test's fixture executed faster than a thread
switch, so six threads serialised by luck and it passed against a faithful
reimplementation of the racy loader it was written against. A gate test
re-read ``live_approval_states`` from an instance whose cached property was
already warm, so the ``patch`` it wrapped the call in changed nothing
observable. Two were caught only by a reviewer neutering each fix by hand; the
third only because the coverage gate noticed two uncovered lines.

**The recipe**, and it is worth repeating for anything added around the
approval gate, the query guard or the loader: *neuter the fix, then run the
test and watch it go red.* Delete the ``with no_queries():``, move the call
back outside the ``try``, drop the ``satisfied`` the frozen row carries, warm
the cached property first — then run it. A test that still passes is not
testing what its name says it tests.

**What the recipe found the second time.** The audit went through the
regression tests around the approval gate, the query guard and the loader,
neutered the fix each one guards — 26 of them — and ran it. Four fixes went
unnoticed by every test in the suite, and all four for the same reason: a
*second* mechanism in the production code made the first one unobservable.

* ``create_cursor`` in ``GUARDED_METHODS``: while a connection is live the
  driver object has been taken away, so the backend's factory refuses on its
  way down whether or not it is on the list. Pinned now with no live
  connection to take away.
* the guard around ``ruleset.permissions`` in ``statement_context``: nothing
  asked a ruleset to query from it.
* the version bound in ``_rows_from_the_same_rules``: the frozen rows being
  the spine kept the existing test green, because the ruleset it falls back
  to names a differently *named* step. Pinned now with two versions that name
  the same step over different groups.
* ``import_module`` in the loader: ``_LOAD_LOCK`` serialises a whole load, so
  the concurrency test passed against a faithful reimplementation of the racy
  publish-then-exec loader it was written against. Pinned now with the lock
  lifted.

The area attracts this for reasons that are not going away: there is a cached
property, there are two resolution paths (the record and the gate) that are
*supposed* to disagree, and there is heavy patching. The two helpers here make
the recipe cheap, and each encodes one of the two rules the failures above come
down to:

* :func:`gate_of` — ask the gate of a **freshly read row**, never of an
  instance the test has already touched.
* :func:`guard_lifted` — assert **both directions**. A guard test that only
  asserts the refusal cannot tell a working guard from a call that never
  happened or a query that would have failed anyway. Lifting the guard at the
  line that installs it and watching the same call go through says which, and
  it is the recipe above as code: the ``with`` block *is* the neutered fix.
"""

from contextlib import contextmanager
from contextlib import ExitStack
from contextlib import nullcontext
from unittest.mock import patch

from finance.models import Statement


def gate_of(statement):
    """The approval gate, asked of a row read fresh from the database.

    ``Statement.live_approval_states`` is cached per instance, because a page
    asks it three times. So patching the resolution and then asking an
    instance that has already answered reads the cache: the assertion passes,
    the patch did nothing, and the gate was never exercised. Going through
    here costs one query and cannot do that.
    """
    return Statement.objects.get(pk=statement.pk).live_approval_states


@contextmanager
def guard_lifted(*modules):
    """Run the block with the query guard neutered where ``modules`` open it.

    :func:`finance.engine.guard.no_queries` is imported by name, so it is
    lifted per importing module rather than globally — which is the point, not
    an inconvenience: the argument names the exact line whose absence the test
    is claiming to detect.
    """
    with ExitStack() as stack:
        for module in modules:
            stack.enter_context(patch(f"{module}.no_queries", nullcontext))
        yield
