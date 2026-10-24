.. _development_manual/finance_rules:

==========================
A section's finance rules
==========================

Kompass does not know how your section settles an excursion. It knows how to
read a statement out of the database, how to run your rules against it, how to
make the money add up and how to remember which version of the rules a
statement was settled under. The rules themselves — what an allowance is, who
gets it, what the participants contribute, who has to sign — are a Python
package in your section's own configuration repository.

This page is the reference for writing that package. It is the whole contract:
:mod:`kompass.rules` is the only Kompass module a ruleset may import, and
everything it offers is documented below.

.. tip::
   There is a directory in this repository to copy rather than start from
   nothing: ``deploy/config-template/``. It holds a working ruleset, three
   worked cases, the ``mypy`` and ``ruff`` configuration and a CI workflow.
   Its ``README.md`` is the section's half of this page.

   And there is a real one beside it: ``deploy/ludwigsburg/`` is the Sektion
   Ludwigsburg's own configuration, written out of its signed documents. It is
   worth reading for the shape of a ruleset that is not a template — two
   policies in force at once behind a ``choice``, the trip's figures derived
   with :attr:`~kompass.rules.Input.source` so that one declaration serves a
   trip and a purchase, signatures routed by office, and twenty cases that pin
   the figures.


What a ruleset is
=================

A ruleset is a class deriving from :class:`~kompass.rules.Ruleset`, instantiated
once and exported as ``ruleset``::

    # rules/__init__.py
    from kompass.rules import PARTICIPANTS, Ruleset, SECTION

    class TownRules(Ruleset):
        name = "town"
        context_version = 1
        balance = (PARTICIPANTS, SECTION, "participant_contribution")

        ...

    ruleset = TownRules()

It answers four questions about one statement, and nothing else:

:meth:`~kompass.rules.Ruleset.inputs`
    Which extra data does a person have to supply? The form is *derived* from
    these declarations, so a question is asked because a rule reads its answer.
:meth:`~kompass.rules.Ruleset.transfers`
    Who owes whom how much, and what is wrong with the statement?
:meth:`~kompass.rules.Ruleset.checks`
    What must hold before the statement may be handed in?
:meth:`~kompass.rules.Ruleset.approval`
    Who has to sign it off, and who may not?

Each one is given a :class:`~kompass.rules.RuleContext` — every fact about the
statement a rule is allowed to know, as frozen values.

There is a fifth method, and it matters to anyone whose questions depend on
the answers already given: the live form asks
:meth:`~kompass.rules.Ruleset.relevant_inputs`, not
:meth:`~kompass.rules.Ruleset.inputs`. Its default implementation re-runs
``inputs`` against the answers so far, which is why a ruleset that branches
inside ``inputs`` already works.

The two have different jobs, and it is worth saying which is authoritative for
what, because a ruleset that overrides ``relevant_inputs`` is overriding only
one of them:

``inputs`` **says what may be read.** It is the whole vocabulary: every key a
rule may ask for, every key an answer may be *stored* under, and the list the
case runner, the fuzzer and the deleted-member cleanup all go through. A rule
that reads a key ``inputs`` never declared raises
:class:`~kompass.rules.RuleError`.

``relevant_inputs`` **says what is being asked.** It is the form, and it is the
set an answer has to be in to count. A question it leaves out is off the form,
``clean`` refuses an answer for it, and — since this was settled (taxis
**#579**) — the rules read it as *unanswered*: the type's empty value, exactly
as if nobody had filled it in yet, whatever is still stored under the key.

So **what the form does not ask, the rules read as unanswered.** Retiring a
question therefore stops it moving money, which is the point: before, the
stored answer went on reaching the rules from behind a form that no longer
showed it and a ``clean`` that no longer accepted it, and the only way out was
an admin editing JSON. Reading a retired key is *not* an error — it reads
empty — because a traceback about a question nobody can see is worse than a
zero a rule can handle.

**Narrow, do not widen.** ``relevant_inputs`` chooses among the questions
``inputs`` declared, and two things follow that are worth stating plainly:

* A key only ``relevant_inputs`` names has nowhere to be stored and nowhere to
  be read, so it is an **error on the statement** — not a question that
  quietly never gets an answer.
* A key they both name is served with the declaration ``inputs`` gave it: same
  label, same type, same bound, same ``source``. So a ruleset that overrides
  one method and not the other cannot end up with a form that says an answer
  is the person's to give while the engine supplies one anyway.

``relevant_inputs`` is given the answers **typed**, as this says, and
``inputs`` is not: it is asked while the context is still being built, before
anything knows which key is money and which is a person, so a declaration that
branches on an answer there reads it with :meth:`~kompass.rules.Inputs.raw`.
That is the difference between the two in practice, and it is why branching
belongs in ``relevant_inputs`` when it can.

**A first question that gates the rest** needs nothing beyond this. A ruleset
whose later questions have no meaning until an earlier one is answered —
Ludwigsburg settles under one of two travel-cost policies, and until it is said
which, a night is neither a receipt nor a flat rate and a kilometre has no rate
at all — returns *that question alone* from ``relevant_inputs`` and nothing
else. Everything follows from the paragraphs above: the form is that one
question, the rules read every other key as unanswered, and ``PATCH`` refuses
an answer to any of them. There is no flag on a declaration saying "this one
comes first", because a gate is not a property of a question: it is what a
ruleset does with the answers it has so far.

Give the gate a ``step`` of its own and the SPA lays it out as the opening step
of the form — a labelled group, with a line saying the rest is waiting on it,
and no payout preview, since every figure in one would be a reading of an
answer nobody has been asked for yet. That reading is "the form came back as a
single *named* step", so it needs no new field either: a ruleset that names no
steps comes back as one step labelled ``""`` and is laid out as the flat list
it has always been.

What a gate does **not** touch is what is already stored. A
:attr:`~kompass.rules.Field.seed` is written out of ``inputs`` when the
excursion is set, not out of the form, so the prefilled row of a table the gate
is hiding is written anyway, waits there, and is served intact by the form the
answer reveals.

**One thing it cannot narrow, and that is where the division of labour bites:
a column.** ``relevant_inputs`` chooses among keys, and the cells of a ``rows``
question are part of that question's declaration rather than keys of their own.
So a ruleset that wants a table's ``fields`` to depend on an answer — a
passenger count only one of two travel-cost regimes pays a surcharge for —
declares it in ``inputs``, branching there on the answer read with ``raw``.
What happens to a cell the declaration then stops naming is
:ref:`development_manual/finance_rules/retired_cell`.


How a ruleset reaches a running instance
========================================

Every Kompass instance is the stock image with one directory mounted read-only
at ``/app/config`` (``KOMPASS_CONFIG_DIR_PATH``), the same directory
``settings.toml`` is read from. A ruleset is a package in that directory, named
from the settings:

.. code-block:: toml

   [finance]
   ruleset = "rules"   # a package directory under KOMPASS_CONFIG_DIR_PATH

``manage.py importruleset`` runs when the ``master`` container starts — one of
the five the image runs, and the only one whose entrypoint imports; the SPA,
the Celery worker, the beat and the LMTP containers do not — on demand from
the admin, and, with ``[finance] ruleset_poll_minutes``, from a periodic task. It
reads every ``*.py`` under the package, hashes the sources together with the
section's finance parameters, and stores that as a **version**. An unchanged
package hashes to the version that is already stored, so importing twice costs
a hash and changes nothing.

A section's workflow is therefore: pull request in the configuration
repository → its own CI runs ``mypy``, ``ruff`` and ``checkruleset`` inside the
pinned image → merge → the host pulls the repository → import. No Kompass
release and no container restart: workers resolve the active version per
evaluation and load its sources by hash on first use.

Activation is gated on the same checks the section's CI runs. A package that
fails one of them is stored as a **draft**, the previous version stays active,
the command exits non-zero and says so loudly — and the container still
serves. A typo in a rule is not a reason to take a section's finances offline.

A statement keeps the version it was created under: its own copy of the
sources and of the parameters is snapshotted onto it, and the resolved
transfers are written down as rows. Changing a rule — or a parameter, which is
the same thing to the hash — never moves a figure that has already been
settled.

.. warning::
   **A section that deploys without a ruleset settles its statements under
   Heidelberg's rules.** When ``[finance] ruleset`` is unset, the reference
   ruleset that ships in the image applies, and that ruleset is the policy of
   the JDAV section Heidelberg: its allowance per day, its organisation fee
   for participants from 27, its LJP arithmetic, its single signature from the
   finance department.

   Nothing fails and nothing warns: the statements resolve, the books add up,
   and the figures are somebody else's. For any section that is not
   Heidelberg, writing a ruleset is not optional — it is the difference
   between settling your own rules and settling theirs.


The rules of the road
=====================

Six properties the engine enforces or depends on. Each of them is the reason
an old statement can be re-derived years later and come out the same.

Everything is a frozen value
----------------------------

The context holds no model instances, no relations to follow, no names, no
bank details, no other statements and no balances. A person is a
:class:`~kompass.rules.Member` — an id and nothing else — and the engine
resolves names and bank details after evaluation, so a ruleset cannot leak
them. What a rule cannot reach it cannot accidentally depend on.

A rule must not query the database
----------------------------------

This is enforced, not asked for: while any of the four methods runs — and
while the ruleset's own module body is executed, and while the engine reads
``name``, ``context_version``, ``valid_from`` or ``permissions`` off it — every
ordinary route to the database refuses. A query raises
``QueryDuringEvaluation``, which comes back as an error on the statement with
the traceback pointing at the line in your rules.

Everything a rule may read is in the context it was given. If a rule needs a
figure that is not there, the answer is a new context field in Kompass — an
additive change with a :data:`~kompass.rules.CONTEXT_VERSION` bump — and not a
query.

Money is :class:`~decimal.Decimal`, in whole cents
--------------------------------------------------

Never ``float``. Every amount a rule returns must have at most two decimal
places; the engine rejects anything finer rather than rounding it silently,
because how to round is the section's decision and not the engine's.
:func:`~kompass.rules.split` and :func:`~kompass.rules.pct` are the two
roundings most rules need, and :func:`~kompass.rules.quantize` is the one they
are built on. A transfer whose amount is a ``float``, or has three decimal
places, is an error on the statement rather than a payout nobody can reproduce.

Rules are deterministic
-----------------------

There is no clock in the context and no way to read one: a *call* to ``now``,
``today``, ``utcnow`` or ``fromtimestamp`` is refused by the import check, and
``random`` and ``time`` may not be imported at all. The one value that depends
on when the engine ran is :attr:`~kompass.rules.Participant.age`, which exists
because the rules it was ported from use it; a rule that must stay reproducible
prefers :attr:`~kompass.rules.Participant.age_at_start`.

A rule must also not read balances — neither a member's standing with the
section nor what another statement resolved to. The context deliberately has
none. The only result of another rule a rule may read is the transfer list it
has built itself during this evaluation, which is how the reference ruleset's
LJP contribution reads the allowance and subsidy it just produced.

``balance`` names the residual party, and it may not be a member
----------------------------------------------------------------

A ruleset does not compute the participants' contributions. It declares which
two parties the residue moves between
(:attr:`~kompass.rules.Ruleset.balance`), and the engine appends exactly one
transfer with the amount that brings the declared *destination* to zero. "The
statement adds up" is therefore not an assertion anybody can forget to make.

The declaration must be between the section and the participants. A member may
not be a balance party: a person is a payee, not a ledger, and balancing
against one makes whoever it names the sink for everything the rules did not
account for — a bill nobody wrote. The engine refuses it. It also refuses a
declaration that is the wrong way round, which closes nothing and leaves a
``0.00`` row to show for it.

A ruleset is stateless
----------------------

One instance is created when a version is loaded and that instance is shared
across every evaluation in the process, concurrently, for as long as the
version is in use. Do not keep anything on ``self`` between calls: no caches,
no counters, no "the statement I am working on". Everything a method needs is
in the context it is given, and anything stored on the instance is a figure
from somebody else's statement waiting to be used in yours.

What does not change is fine: a number read from the context
(``ctx.params.ALLOWANCE_PER_DAY``), a module-level constant
(``ORG_FEE_AGE = 27``), a class attribute the engine itself reads
(:attr:`~kompass.rules.Ruleset.balance`), a pure helper method.


What a ruleset may import
=========================

A ruleset may import:

* **itself** — relative imports inside its own package (``from .travel import
  reimbursement``),
* :mod:`kompass.rules`, and nothing else from Kompass,
* ``from __future__ import …``, which is a compiler directive,
* and these standard-library modules: ``decimal``, ``math``, ``dataclasses``,
  ``typing``, ``enum``, ``fractions``, ``itertools``, ``functools``,
  ``collections``.

Everything else is refused at import time, with a file and a line. So is any
mention of ``__import__``, ``importlib``, ``exec``, ``eval``, ``compile``,
``open``, ``os``, ``sys``, ``subprocess``, ``socket``, ``random``, ``time``,
``requests``, anything under ``django``, ``globals``, ``locals``, ``vars``,
``getattr``, ``setattr``, ``delattr`` and ``dir``; so are the dunder
attributes that walk out of a module and into the interpreter
(``__class__``, ``__globals__``, ``__builtins__``, ``__code__`` and the rest);
and so is a *call* to ``now``, ``today``, ``utcnow`` or ``fromtimestamp``.

Third-party packages are not available. The image does not have them, and a
ruleset's import closure has to be enumerable to be hashable. A section that
needs more than the list above asks for a helper in :mod:`kompass.rules`.

.. important::
   **This is a lint plus a restricted namespace. It is not a sandbox, and
   nothing here should be read as one.**

   The check is a textual scan of the ruleset's source, and the loader executes
   it with a restricted ``__builtins__``. Neither is a boundary: four lines
   that mention no banned name at all reach the interpreter's own builtins
   through a frame object, and frames, descriptors and ``__reduce__`` are each
   one hop from the next spelling. No blacklist carries that guarantee.

   What the check *is* worth is catching the accident early — a rule that
   imports half of Kompass, reads the clock or opens a file is a rule whose
   answer can change behind an old statement's back — and letting your own CI
   say the same thing with ``ruff`` before the pull request is merged. What
   carries the database guarantee is the query guard, which refuses at the
   connection however the rule got there.

   The trust boundary is unchanged by any of it: whoever can write the
   configuration directory already holds the database password and the secret
   key. Executing Python from it grants no privilege its author does not
   already have. A rule author is trusted exactly as far as the person who
   edits ``settings.toml``.


Declaring inputs
================

Every answer a rule reads has to be declared by
:meth:`~kompass.rules.Ruleset.inputs`, because the statement's form is
generated from those declarations. Reading an undeclared key raises
:class:`~kompass.rules.RuleError` rather than returning ``None``: a typo in a
rule is a bug your cases should catch, not a silent zero in somebody's
reimbursement.

.. _development_manual/finance_rules/widgets:

The widget vocabulary
---------------------

:attr:`~kompass.rules.Input.type` is presentation, not rule structure —
``money`` and ``int`` are both numbers, and the difference is the field the
person is shown.

.. list-table::
   :header-rows: 1
   :widths: 14 30 56

   * - ``type``
     - Read with
     - What it is, and what it reads as unanswered
   * - ``money``
     - :meth:`~kompass.rules.Inputs.money`
     - An amount, as a :class:`~decimal.Decimal`. Unanswered: ``0.00``.
   * - ``int``
     - :meth:`~kompass.rules.Inputs.number`
     - A whole number; :attr:`~kompass.rules.Input.max` is its largest
       acceptable value. Unanswered: ``0``.
   * - ``bool``
     - :meth:`~kompass.rules.Inputs.flag`
     - A yes/no question. Unanswered: ``False``.
   * - ``text``
     - :meth:`~kompass.rules.Inputs.text`
     - Free text. Unanswered: ``""``.
   * - ``choice``
     - :meth:`~kompass.rules.Inputs.text`
     - One of the named alternatives in :attr:`~kompass.rules.Input.choices`,
       as its ``value``. Unanswered: ``""``.
   * - ``member``
     - :meth:`~kompass.rules.Inputs.member`
     - One person out of :attr:`~kompass.rules.Input.options`. Unanswered:
       ``None``.
   * - ``member_set``
     - :meth:`~kompass.rules.Inputs.members`
     - Several people out of :attr:`~kompass.rules.Input.options`, at most
       :attr:`~kompass.rules.Input.max` of them. Unanswered: ``()``.
   * - ``rows``
     - :meth:`~kompass.rules.Inputs.rows`
     - A **repeating row**: the question asked once per row, over the cells
       :attr:`~kompass.rules.Input.fields` declares, at most
       :attr:`~kompass.rules.Input.max` rows of them. Each cell has one of the
       types above and is validated by it. Unanswered: ``()``. See
       :ref:`development_manual/finance_rules/rows`.

For ``member`` and ``member_set``, the engine re-validates a submitted answer
against the options the declaration offered, so an answer can never name
somebody the rule did not offer. A ``choice`` is re-validated against its own
:attr:`~kompass.rules.Input.choices` in exactly the same way, so an answer can
never be a value the rule did not offer either.

**And it is re-validated on the way out, not only on the way in.** A domain
shrinks without anybody editing an answer: a section withdraws one of two
alternatives, or a receipt's payer is cleared and an
:attr:`~kompass.rules.Input.options_source` set loses them. The answer stored
under that key then reads as **unanswered** — the same reading a retired
question gets, and for the same reason: what the form would refuse, the rules
do not read. ``GET …/form`` serves it as unanswered too, so a client is never
handed a value its own option list does not contain.

**And the statement says so.** Dropping the answer is only half of it: the
evaluation reports it, which makes :attr:`~finance.engine.Result.ok` false, so
nothing is materialised, nothing is frozen, ``/preflight`` stops saying ``ok``
and the admin's pages stop saying "everything is correct". Without that, the
one state with no witness appeared — a statement owing somebody money closing
at ``0.00``, the recipient still named on every page, no error, and every
``Check`` the ruleset wrote going vacuous because it reads the already-dropped
value. So removing a youth leader from a trip *blocks* the statement that was
paying them until somebody answers the question again, which is the honest
outcome.

A ``member_set`` is dropped **whole**, not member by member. A trip that loses
one of three allowance recipients stops paying all three rather than two,
because picking which two survive is a selection nobody made — and since the
statement is blocked either way, nothing is paid until the set is given again.

.. warning::
   **Which statements this can reach.** A *draft* is resolved live on every
   read, so it is affected at once. A **confirmed** statement is never resolved
   again. A statement that has been handed in but not yet confirmed is in
   between, and it is the case to know about: ``Bill.save()`` and
   ``Bill.delete()`` re-freeze it, which re-runs the rules and **supersedes**
   its rows — so a finance officer covering a receipt after submission is
   enough to re-settle it. Under this reading the re-run reports the dropped
   answer instead, which means the rows are retired rather than rewritten at a
   figure nobody chose, and the statement shows as unresolved until the answer
   is given again. That is the better of the two outcomes, but it is not
   "nothing happens": a settled-looking statement can still change until it is
   confirmed.

So one sentence holds for the whole form: **what the form serves is what the
rules read**. A client may send all of it back except the keys marked
``derived``. The one exception is an answer whose stored *type* no longer fits
its declaration, because the section retyped the key: that is served as it
stands and refused on the way back, since it is a broken answer rather than a
withdrawn one and the rules report it loudly rather than reading it as empty.

**Any key can be stored.** A statement keeps its answers in one JSON field, so
a declaration under any key a ruleset likes holds an answer and is read back by
the rules. That is a statement about *storage*, and it is the whole of what
#556 changed.

.. warning::
   **Four key names still mean something outside the engine**, and a section
   that renames them loses what they do silently.
   ``finance/models.py`` reads ``allowance_to`` and ``night_cost`` **by name**,
   out of ``Statement.inputs``, in properties the engine never sees:

   * ``allowance_to_valid`` → ``validity`` → the admin's ``confirm()`` and
     ``submit_statement``. It is the ``INVALID_ALLOWANCE_TO`` gate, and with
     the key absent it returns ``True`` vacuously — so a section whose
     allowance key is called something else keeps the gate's name on its
     screens and none of its checking.
   * ``real_night_cost`` → the statement summary's ``price_per_night``, which
     is what the printed PDF shows.

   Those are leftovers of the four columns rather than anything the rules
   engine asks for, and until they are derived from the declarations too, a
   section reusing the names keeps the behaviour and a section renaming them
   should know it is giving the behaviour up.

A declaration the engine cannot serve is refused where it is written, with
:class:`~kompass.rules.RuleError` — a ``choice`` with no choices, a
:attr:`~kompass.rules.Input.source` naming a field the context does not have, an
:attr:`~kompass.rules.Input.options_source` on a question that names no people.
Inside ``inputs`` that becomes an error on the statement with a traceback at
the line in your rules, and in your own CI it fails a case before the version
is ever activated. The alternative, which is what ``choice`` used to do, is a
question that reaches somebody's form with nothing behind it.

.. _development_manual/finance_rules/choices:

A choice names its own alternatives
-----------------------------------

A ``choice`` has to say what may be chosen, as :class:`~kompass.rules.Choice`
values. The ``value`` is what is stored and what a rule reads; the ``label`` is
what the person picking it is shown, so a section can reword the question
without touching the rules or re-settling anything::

    Input(
        "regime",
        "Nach welchem Regelwerk?",
        "choice",
        choices=(
            Choice("ehrenamt", "Ehrenamtspauschale"),
            Choice("tourenleitung", "Tourenleitung"),
        ),
    )

    # and in `transfers`
    rate = RATES[ctx.inputs.text("regime")] if ctx.inputs.text("regime") else ZERO

An unanswered ``choice`` reads as ``""``, like an unanswered ``text`` — so a
rule reading one on a form somebody is halfway through gets an empty string,
not an exception.

.. _development_manual/finance_rules/derived:

Derived inputs: a figure the statement already knows
----------------------------------------------------

Some of what a rule needs is not a question at all. The kilometres are on the
excursion; asking a person to type them again invites two numbers that disagree.
A declaration may therefore name where its value comes from::

    Input("kilometers", "Gefahrene Kilometer", "int", required=False,
          source="excursion.kilometers")

**With an excursion whose source resolves,** the engine supplies the value. The
declaration comes back with :attr:`~kompass.rules.Input.derived` set, the form
shows the figure rather than an empty field, and submitting a value for the key
is **refused** — a ``422`` keyed by that question. Wrong kilometres are
corrected on the trip.

**Without an excursion, or with nothing recorded,** it is an ordinary question
whose answer is stored like any other.

Either way the rule reads it the same way::

    kilometers = ctx.inputs.number("kilometers")

That is the whole point. Before, the same quantity lived in two places
depending on provenance — ``ctx.excursion.kilometers`` off the trip, everything
else out of ``inputs`` — so a ruleset serving statements both with and without
an excursion had to branch on ``ctx.excursion is None`` and read a different
place in each arm. One declaration and one accessor replace that.

**A derived value is not stored.** It is resolved again every time a context is
built, never written to ``Statement.inputs``. That is a decision rather than an
omission: a stored copy would be a second figure to go stale when the trip is
corrected, there would then be a question about which of the two is right, and
re-seeding it would need a rule nobody has written. There is no second copy —
the excursion is the record.

A ``source`` is ``"<root>.<field>"``, one field deep. The roots are
:data:`~kompass.rules.SOURCE_ROOTS`: ``excursion`` and ``statement``. The field
has to be a real field of what that root holds — a field of
:class:`~kompass.rules.Excursion` or of :class:`~kompass.rules.StatementInfo` —
and anything else is refused where it is written, with the list of fields that
do exist. There is no deeper path, no callable from the ruleset and no
``getattr`` chain over arbitrary objects: the engine looks up one named field of
one frozen dataclass it built itself, which is what keeps the query guard's
story intact. A figure further in than one field —
``ctx.excursion.ljp.participant_count`` — is read off the context by the rule
that wants it, which needs no declaration at all.

The value arrives as the type the field holds: ``excursion.kilometers`` is a
whole number, ``excursion.duration`` is money, ``statement.creator`` is a
:class:`~kompass.rules.Member`, ``excursion.leaders`` is a set of them. Match
the widget to the field; naming a field that holds a whole nested structure is
a mistake the form will show you as text.

A source resolves to nothing in exactly two cases: **the root is absent** (a
statement with no excursion) or **the field itself is** ``None``. A ``0``, an
empty string and an empty set are figures the statement *records*, so they are
supplied like any other — a trip whose kilometres are still at the model's
default of ``0`` serves ``0`` and refuses a correction on the form, because the
correction belongs on the trip. The only nullable fields are
:class:`~kompass.rules.StatementInfo`'s two people and
:attr:`~kompass.rules.Excursion.ljp`.

:attr:`~kompass.rules.Input.max` applies to a derived value too, and that is
worth knowing before writing ``source="excursion.leaders"`` with a bound on it.
A submitted answer over the bound is refused on the way in; a *supplied* one
cannot be, because nobody can change it here — so it is an **error on the
statement** naming the source and the bound. Five leaders against three the
section approved is a statement to fix on the excursion, and while the error
stands the statement does not resolve and no money moves. It is deliberately
not a truncation: paying three of five quietly is a figure no page explains.

``max`` means a count for a ``member_set`` and a ceiling for an ``int``, **and
nothing at all for any other type** — ``money`` included, which is the other
one you would expect a ceiling on. A money answer is bounded only by the
field's own resolution and ceiling; a section wanting its own maximum writes a
:class:`~kompass.rules.Check`, where the sentence is its own too.

A party-valued ``source`` should be stated **together with** an
:attr:`~kompass.rules.Input.options_source` (or a hand-listed
:attr:`~kompass.rules.Input.options`), and the two never both apply: when the
source resolves, the engine supplies the answer and the options go unread; when
it does not, the options are who may be picked. ``source="excursion.leaders"``
with ``options_source="bills.payers"`` is the whole of "whoever led the trip,
or whoever paid a receipt when there was no trip".

Without that second half such a question cannot be answered at all on a
statement with no excursion — the source resolves to nothing, the declaration
offers nobody, and a party-valued declaration offering nobody offers nobody. So
the rule is one sentence: **who may be picked bounds the answer when it is
asked for, and says nothing about one the engine supplies.** A supplied one
comes out of the statement's own data, which is what makes it safe without a
domain, and what bounds it is ``max``.

.. _development_manual/finance_rules/options:

Where a party-valued question's people come from
------------------------------------------------

``member`` and ``member_set`` need a domain, and a ruleset that has an excursion
can simply write one: ``options=ctx.excursion.leaders``. A statement that
settles a purchase rather than a trip has no leaders — and so, until this, no
way to pay anybody at all.

A declaration may instead name where the engine should take them from::

    Input("paid_to", "Auslagen an", "member", required=False,
          options_source="bills.payers")

The vocabulary is :data:`~kompass.rules.OPTION_SOURCES`, and it is a fixed list
rather than a path on purpose: this is the one declaration where a mistake costs
money, so every name in it is a set the *statement itself* carries.

``excursion.leaders``
    the trip's youth leaders — what a trip-shaped ruleset writes by hand.
``excursion.participants``
    everybody on the trip's member list, leaders included.
``bills.payers``
    whoever paid one of this statement's receipts. The answer for a purchase.
``statement.creator``, ``statement.submitter``
    the two people the statement names itself.

No spelling of it reaches somebody the statement does not already mention, and
"every member in the section" is not reachable. The engine fills
:attr:`~kompass.rules.Input.options` in, deduplicated and in id order, and the
submitted answer is then re-validated against it like any other. Say it once:
a declaration that both lists its options and names a source for them is
refused.

.. _development_manual/finance_rules/rows:

Repeating rows: one question, several travellers
------------------------------------------------

A statement settles a trip that several people went on, and they travelled
differently: one drove 120 km, one took the train, one cycled. Every
declaration so far asks its question **once** — one ``approach``, one
``kilometers``, one ``passengers`` — so a section whose rules pay per kilometre
could settle exactly one journey per statement.

A ``rows`` declaration asks it once per row::

    Input("reisen", "Fahrten", "rows", step="Fahrt",
          max=12,
          options_source="bills.payers",
          fields=(Field("member",     "Person",         "member"),
                  Field("approach",   "Verkehrsmittel", "choice", choices=APPROACHES),
                  Field("kilometers", "Kilometer",      "int", max=2000),
                  Field("passengers", "Mitfahrende",    "int", required=False)))

and a rule reads it back as rows::

    for journey in ctx.inputs.rows("reisen"):
        if journey.text("approach") != CAR:
            continue                        # the train is a receipt, not a rate
        driver = journey.member("member")
        if driver is None:
            continue
        rate = travel_rate(regime, journey.number("passengers"))
        transfers.append(Transfer(SECTION, driver,
                                  cents(journey.number("kilometers") * rate),
                                  "travel", rule_id="travel"))

**Why a row and not a map from person to number.** Because whether somebody
gets the rate per kilometre *at all* depends on their own mode of travel — a
private car yes, the train no, because there the receipt is the claim, and a
rental excludes travel costs entirely. The mode and the distance decide each
other, so they belong to the same traveller in the same place. Keyed by person
they come apart into two answers that can disagree about how many people there
even were, and the rule has to pair them up again.

A :class:`~kompass.rules.Row` *is* an :class:`~kompass.rules.Inputs` over one
row, so it is read with the same accessors and they raise the same way: a cell
the declaration did not name is a :class:`~kompass.rules.RuleError` listing the
fields it did.

Each cell is validated **by its own type**, through the same code the question
of that type would have gone through. A ``choice`` cell is checked against its
``choices``, an ``int`` cell against its own ``max``, and a ``member`` cell
against the people the question offers — which is
:attr:`~kompass.rules.Input.options`, filled in from
:attr:`~kompass.rules.Input.options_source` exactly as it is for a ``member`` or
a ``member_set``. The domain is stated **once, on the question**: a
:class:`~kompass.rules.Field` has no ``options`` of its own, because one column
served two different sets of people in two rows is not a thing a form can
explain. Nothing else about a cell is new: :attr:`~kompass.rules.Field.max`,
:attr:`~kompass.rules.Field.choices`, :attr:`~kompass.rules.Field.required` and
:attr:`~kompass.rules.Field.help` are the attributes of the same name on an
:class:`~kompass.rules.Input`, and ``rows`` is the one type a cell may not be.

:attr:`~kompass.rules.Input.max` on a ``rows`` question bounds **the number of
rows**. A cell's ceiling is on the cell. That is this attribute's second
qualification and it is the same sentence read twice: ``max`` bounds *the
answer* — the value of an ``int``, the count of a set of people, the count of
rows of a table — and never anything a level further in.

Three states, and all three are decided rather than left to fall out:

**An empty table is an unanswered question.** ``[]``, a key nobody ever sent
and a table the form has stopped asking for all read as ``()``, because nothing
distinguishes them and inventing a difference would need a state nothing
stores. A rule that pays per row pays nothing. Whether a table is *needed* is
:attr:`~kompass.rules.Input.required` and the ruleset's own
:class:`~kompass.rules.Check`, exactly as for every other type — the form is
filled in gradually, and a refusal on the table somebody has not reached yet
would make the first save of a draft impossible.

**A row with an empty required cell is stored.**
:attr:`~kompass.rules.Field.required` is advisory in the same way
:attr:`~kompass.rules.Input.required` is: the cell is kept empty and reads as
its type's empty value. "Für jede Fahrt braucht es ein Verkehrsmittel" is a
:class:`~kompass.rules.Check`, where the sentence is the section's own, and a
rule that pays per kilometre has to survive a distance of zero anyway, because
a person can always type one.

**A person named in two rows is accepted.** The engine does not know which
field identifies a row — no declaration says so — and more to the point it
**cannot tell a double entry from a split journey**: two rows for one person at
120 km each is as readily a there-and-back entered in two halves as it is the
same trip typed twice. Refusing would make the honest table unsayable in order
to catch a mistake it cannot reliably recognise, and deduplicating would throw
away a row somebody entered. A section that means one row per person says so in
a ``Check`` — the same answer this page already gives for a ceiling on an
amount, and for the same reason: the sentence is the section's.

A table falls out of its domain **whole**. One cell naming somebody the rules
no longer offer drops the whole table and the evaluation reports it, which is
the ``member_set`` decision one level in and for the same reason: choosing
which rows survive is a selection nobody made, and the statement is blocked
either way.

.. _development_manual/finance_rules/retired_cell:

A column that comes and goes
----------------------------

``fields`` is part of a declaration, and :meth:`~kompass.rules.Ruleset.inputs`
is given the context — so a ruleset may declare a table with different columns
depending on an answer::

    def inputs(self, ctx: RuleContext) -> list[Input]:
        regime = self.regime_of(ctx)          # read with `raw`: see above
        return [...,
                Input("reisen", "Fahrten", "rows", max=12,
                      options_source="bills.payers",
                      fields=journey_fields(regime))]

That is how a regime narrows a table, and it is deliberately *not*
``relevant_inputs``: that method chooses among keys, and a column is not a key
(see `What a ruleset is`_). A column the declaration does not name is not on
the form, no rule can read it, and nothing it holds can move money — which is
the whole of the guarantee, stated for a column rather than for a question.

Rows stored while it *was* named still carry it, and there is one reading of
that and it is the same one taxis **#579** settled a level up: **the cell is
ignored, not refused, and not thrown away.**

* A rule never sees it. The :class:`~kompass.rules.Row` a rule reads is built
  from the declaration, so a cell it does not name is not in the row at all and
  ``journey.number("passengers")`` raises :class:`~kompass.rules.RuleError`
  naming the fields the row does have. A ruleset whose columns move therefore
  reads such a cell defensively — ``if "passengers" in journey.declared()`` —
  exactly as it reads the answer it branches on.
* The domain says nothing about it. :func:`finance.engine.answers.within` judges
  the cells the declaration names, so a stored count outside a bound the column
  no longer has does not drop the table.
* ``GET …/form`` serves the row **as stored**, retired cell included, and
  ``PATCH /statements/{id}`` accepts it without checking it. So a client that
  hands back what it was served keeps the value, and one that leaves the cell
  out drops it.
* The value stays in ``Statement.inputs``. It is the answer somebody gave while
  the column was asked for, so putting the regime back finds the count again
  rather than an empty cell, and the declaration that asks for it checks it
  again then.

What is still **refused** is a cell key no version of the declaration ever
named. The two are told apart by the statement's own stored answer: nothing
reaches ``Statement.inputs`` except through ``clean``, so a key the stored rows
carry is a key some declaration asked for, and a key in neither the declaration
nor the storage is the typo it looks like — a ``422`` keyed to the row, exactly
as before.

.. _development_manual/finance_rules/seed:

Seeding a table: one row to correct, which is not a derivation
--------------------------------------------------------------

The trip records one distance and one mode. That is not the answer — the people
on it travelled differently — but it is a good first row, and retyping it is
how two figures come to disagree. A cell may therefore name where it is
**prefilled** from::

    Field("approach",   "Verkehrsmittel", "choice", choices=APPROACHES,
          seed="excursion.approach")
    Field("kilometers", "Kilometer",      "int", seed="excursion.kilometers")

:attr:`~kompass.rules.Field.seed` uses the same ``"<root>.<field>"`` vocabulary
as :attr:`~kompass.rules.Input.source` (:data:`~kompass.rules.SOURCE_ROOTS`)
and means something different in every respect that matters. The two are
deliberately not one mechanism and deliberately not one word:

.. list-table::
   :header-rows: 1
   :widths: 24 38 38

   * -
     - ``source=``
     - ``seed=``
   * - belongs to
     - the excursion
     - the person filling the form in
   * - editable
     - no — ``clean()`` refuses a value for the key
     - **yes, and that is the point**
   * - stored
     - no, re-derived on every context build
     - **yes, written once**
   * - the trip changes later
     - the value follows immediately
     - the row stays where it is

Two rules follow from "written once", and both are deliberate:

**Seeded exactly once, when the excursion is set.** Not on every context build,
and *not* whenever the table happens to be empty. Either of those turns the
prefill into a thing that fights the person: a row somebody deleted — because
nobody drove — would come back by itself, and a row somebody split into three
would be written over. So the trigger is an event and not a state, and the
event is the excursion being assigned: ``POST /statements`` with an
``excursion_id``, the excursion changing in ``PATCH /statements/{id}``, and the
admin's excursion inline opening a statement on a trip.

**Changing the excursion re-seeds.** The row described a different trip — its
distance, its mode — so keeping it would have the statement claim a journey
nobody made. This is the same reasoning an excursion swap already drops every
answer that names a person by: those people led the *other* trip. An answer
restated in the same request wins over the re-seed, so correcting the excursion
and the table together is one call.

Three smaller decisions, stated because each one is a choice:

* **A seed that resolves to nothing leaves the cell empty**, and a table none of
  whose seeds resolved gets **no row at all**. So a statement with no excursion
  starts with an empty table rather than with a row of blank cells, and clearing
  an excursion empties the table.
* **A seeded value its own cell does not offer is left empty.**
  :attr:`~kompass.rules.Excursion.approach` is one of three words Kompass uses;
  a section's ``choice`` lists its own vocabulary, and a seed is a suggestion. A
  value the form would refuse on the way back in is not written.
* **A trip whose kilometres are** ``0`` **is seeded with** ``0``.
  :attr:`~kompass.rules.Excursion.kilometers` is a non-nullable
  ``IntegerField(default=0)``, so "nobody recorded it" and "nobody drove" are
  the same value there and no mechanism can tell them apart. A ``source`` has to
  serve that zero and then refuse a correction, which is the awkward case in its
  own section above. A seed hands over the zero *and the pencil*: the person
  fixes it in the row at the cost of a keystroke. Seeding what the trip records
  is right here for exactly the reason supplying it is awkward there.

A ``rows`` declaration may not have a ``source`` at all, and the refusal says
why: a table is not one figure, and what prefills one is a seed.

.. _development_manual/finance_rules/row_errors:

Where a refusal about a cell lands
----------------------------------

A ``422`` from ``PATCH /statements/{id}`` carries ``errors``, a map from
**where** to a list of messages, and a client prints each message against the
control it names. A table is one question with a grid of controls, so keyed by
the question a refusal about one person's kilometres appears under the whole
table — which tells somebody with five journeys in front of them only that one
of them is wrong.

The keys are therefore a path:

``"night_cost"``
    the answer to that question — unchanged, and what every key not of a table
    still looks like.
``"reisen"``
    the table as a whole: too many rows, or not a list of rows.
``"reisen[1]"``
    the row at index 1, **zero-based**, in the order the request sent the rows.
``"reisen[1].kilometers"``
    the ``kilometers`` cell of that row, which is where nearly every refusal
    about a table belongs.

Zero-based because the client sent an array and indexes back into it; what a
person is shown is the client's business, and a row number in the message would
be a second numbering to keep in step with the first. A table reports **every**
cell it found wrong in one response, because a table is one answer and somebody
correcting it should see all of it; across different questions the first problem
still answers alone, as it always has.

The type has not changed — string keys, lists of messages — so nothing that
renders ``errors`` by key has to change to keep working. What changed is that a
cell error is now placeable. The admin's excursion inline, which has one field
per question and renders a table as JSON, folds the path into the message
instead: ``reisen[1].kilometers: Kilometer ist keine ganze Zahl.`` That is less
than the SPA gets and it is stated as less.

.. _development_manual/finance_rules/steps:

Steps: which questions belong together
--------------------------------------

The declarations are a flat list, so a client can only lay them out as one long
form. ``step`` is a short label that says otherwise::

    Input("regime", "Regelwerk", "choice", step="Grundlagen", choices=...)
    Input("kilometers", "Kilometer", "int", step="Fahrt", source=...)
    Input("paid_to", "Auslagen an", "member", step="Fahrt", options_source=...)

``GET …/form`` then serves ``steps`` as well as ``inputs``: a label and the
keys in it, in declaration order, with the steps in the order their labels
first appear. Every key is in exactly one step, and a ruleset that names none
comes back as a single step with an empty label — so a client can render the
grouping unconditionally.

That is all it is. There is no page state, no "next", no notion of a step being
complete: which questions belong together is the section's business, how to
present them is the client's, and a wizard in the backend would be Kompass
deciding both.


.. _development_manual/finance_rules/settlement_groups:

Which amounts may not share a bank transfer
===========================================

Kompass bundles the payout before anybody makes a payment: two amounts owed to
the same person out of the same ledger become **one** booking, with a reference
that itemises what it covers, so that one bank transfer settles both. That is
the right default — nobody wants to make four transfers to one youth leader for
one weekend — and it is wrong for money that has to be payable *separately*.

The one every section runs into is tax. A Tourenleitervergütung is an
Ehrenamtspauschale under § 3 Nr. 26 EStG; the section has to be able to point
at the payment that carried it, and adding it to the same person's mileage
produces one amount that is neither. Ludwigsburg's own note says it in one
line: „Steuerrelevante Abrechnungen werden getrennt von anderen überwiesen
aber als ein Prozess bearbeitet.“ One statement, one approval, one process —
two transfers.

So a transfer may name a **settlement group**::

    Transfer(SECTION, leader, cents(hours * FEE_PER_HOUR),
             "tour_leader_fee", rule_id="tour_leader_fee",
             label="Tourenleitervergütung",
             settlement_group="steuerrelevant")

What the engine does with it is one thing and nothing else: what may be bundled
into one booking is ``(member, ledger, settlement_group)`` instead of
``(member, ledger)``. Everything follows from that.

* A transfer that names a group **never shares a transfer with anything
  outside it**, so the example above is paid on its own.
* Two transfers that name the **same** group still travel together, which is
  why this is a token and not a ``separate`` flag: a flag can only say "this
  one stands alone", and a token can also say "these three belong together but
  not with those" at no extra cost. Two Vergütungen on one statement are one
  transfer; the mileage beside them is another.
* A transfer that names **no** group is bundled with the other ungrouped ones,
  exactly as every transfer was before this existed. **A ruleset that declares
  no settlement groups merges precisely as it did**, and nothing about an
  already-settled statement moves.

The token is the ruleset's own vocabulary — free text, at most
:data:`~kompass.rules.SETTLEMENT_GROUP_LENGTH` characters, never interpreted.
Kompass does not know that ``"steuerrelevant"`` is about tax and does not treat
it specially; it compares tokens. A longer one is an error on the statement
rather than a value cut to fit, because a token truncated on its way into the
database would merge amounts a section wrote it to keep apart.

**What it is not.** It says nothing about *when* or *by whom* money is paid, and
it adds no state to the statement: Kompass produces a payment instruction, and
the group is a constraint on the shape of that instruction. The group is written
to the obligation row with the rest of the transfer, so a statement settled
years ago still says which of its amounts were kept apart, and
``manage.py verifyrulesets`` compares it on a replay — a change that would now
merge a taxable payment into somebody's travel costs is reported as drift
rather than passing as agreement.

.. tip::
   **The reference text is the other half of the instruction, and it is
   unchanged on purpose.** A bundled booking still itemises what it covers
   (``"Fahrtkosten EUR 24.00, Tagegeld EUR 28.00"``) and a booking that stayed
   on its own still carries its transfer's own reference — which is exactly
   what bundling used to destroy, since "Tourenleitervergütung" concatenated
   into a mileage claim is not an instruction anybody can act on. The group
   token itself is **not** written into the reference: it is your rules' word
   for a category of money, not German prose for whoever reads the paper.

   Write the :attr:`~kompass.rules.Transfer.label` of a separately-settled
   transfer so that it stands on its own, because that is the line somebody
   will read off a statement they got as a PDF, with no access to Kompass at
   all.


The section's numbers
=====================

A figure that the section votes on rather than a rule that it writes — the
allowance per day, the maximum per night, the rate per kilometre — is a
*parameter*, read from the context as ``ctx.params.ALLOWANCE_PER_DAY``. The
values come from the section's ``settings.toml``, as exact decimal strings,
and they are hashed into the ruleset's version alongside its sources: changing
the allowance per day is a new version, not an edit, and nothing that was
settled under the old number moves.

.. note::
   The parameter names are **not** free-form. Kompass copies a fixed list of
   settings into a version's parameters — ``PARAMETER_KEYS`` in
   ``finance/engine/context.py``, today ``ALLOWANCE_PER_DAY``,
   ``MAX_NIGHT_COST``, ``AID_PER_KM_TRAIN``, ``AID_PER_KM_CAR`` and
   ``EXCURSION_ORG_FEE`` (from ``[finance]``) plus
   ``LJP_CONTRIBUTION_PER_DAY`` and ``LJP_TAX`` (from ``[LJP]``) — so
   ``ctx.params.WHATEVER_YOU_LIKE`` raises
   :class:`~kompass.rules.RuleError`.

   A number that is not one of those keys belongs in the ruleset as a
   module-level constant, where it is versioned with the rules that read it.
   That is arguably where a figure the section voted on belongs anyway: the
   hash moves when it changes, which is exactly the behaviour a parameter has.


Cases: a ruleset's own tests
============================

A case is one JSON file beside the rules, in ``rules/cases/*.json``, holding a
whole context and what the rules are expected to make of it. It needs no
database, no fixtures and no Django, which is the point: the cases run in your
own repository's CI against the image you deploy, and **the instance runs them
again at import** — a case that fails means the version is stored as a draft
and never activated.

.. code-block:: json

   {
     "name": "allowance only",
     "params": {"ALLOWANCE_PER_DAY": "22"},
     "inputs": {"allowance_to": [7]},
     "excursion": {"duration": "2.0", "leaders": [7], "staff_count": 1,
                   "approved_staff_count": 2},
     "expect": {
       "transfers": [
         ["SECTION", "7", "44.00", "allowance"],
         ["PARTICIPANTS", "SECTION", "44.00", "participant_contribution"]
       ],
       "errors": [],
       "checks": [true]
     }
   }

* Only the keys a case cares about have to be there. Everything else takes a
  quiet default: no bills, no trip, no answers, every parameter unset.
* Money is written as a **string** (``"42.69"``), so that a case file never
  carries a binary float.
* A party is ``"SECTION"``, ``"PARTICIPANTS"`` or a member id.
* Each expected transfer is ``[source, destination, amount, category]``, in the
  order the rules produced them, and **the engine's balancing transfer is the
  last one**. A case that leaves it out fails, which is deliberate: it makes
  the case say out loud what the participants end up contributing.
* A transfer may be written with a **fifth** element, its
  :ref:`settlement group <development_manual/finance_rules/settlement_groups>`.
  A row of four says nothing about the group; a row of five pins it, and ``""``
  pins *no group*. Both halves are worth writing down — see
  :ref:`development_manual/finance_rules/settlement_group_cases`.
* ``errors`` is the list of messages :meth:`~kompass.rules.Ruleset.transfers`
  returned, compared exactly.
* ``checks`` is the expected ``ok`` state of each check, in order. Leaving the
  key out means the case does not look at them.
* ``permissions`` maps a codename to the ids that hold it, for a ruleset whose
  rules read :meth:`~kompass.rules.RuleContext.permission_holders`.

The format is implemented in ``jdav_web/finance/engine/cases.py``, which is
also where a new key would be added.

.. _development_manual/finance_rules/derived_cases:

What a case cannot prove about a derived input
----------------------------------------------

A case answers questions, and a derived question is not answered: the engine
resolves it from the context the case file describes. So writing ``kilometers``
into a case's ``inputs`` proves nothing — the engine will supply
``excursion.kilometers`` over it, exactly as it does on a real statement. Put
the figure where the rule will read it from::

    {
      "name": "travel at the volunteer rate",
      "inputs": {"regime": "ehrenamt", "paid_to": 7},
      "excursion": {"kilometers": 100, "leaders": [7]},
      "bills": [{"amount": "40.00", "payer": 7}],
      "expect": {"transfers": [["SECTION", "7", "20.00", "travel"],
                               ["PARTICIPANTS", "SECTION", "20.00",
                                "participant_contribution"]]}
    }

A case **can** prove the other half, and it is the half worth a case: leave
``excursion`` out and the same declaration is an ordinary question, so a case
with ``"inputs": {"kilometers": 250}`` and no trip is the statement that
settles a purchase. Both arms of one declaration, in two files.

.. _development_manual/finance_rules/row_cases:

How a case answers a table
--------------------------

A ``rows`` answer is written the way it is stored: a list of objects, one per
row, keyed by the field keys the declaration names::

    {
      "name": "three people, three ways there",
      "inputs": {"reisen": [{"member": 7, "approach": "car", "kilometers": 120,
                             "passengers": 2},
                            {"member": 8, "approach": "public", "kilometers": 120},
                            {"member": 9, "approach": "muscle", "kilometers": 40}]},
      "excursion": {"kilometers": 120, "approach": "car", "leaders": [7, 8, 9]},
      "bills": [{"amount": "31.40", "payer": 8, "covered": true}],
      "expect": {"transfers": ["…"]}
    }

Each cell is typed by the field that asks for it, so money in a cell is a
string like money anywhere else and a person is an id. Nothing in the case
format is specific to tables, and that is the point rather than an accident: a
worked case is what gates activation, so a type a case cannot express is a type
a section cannot ship.

A **seed** is not expressible in a case, and should not be. A seed is written
when somebody's statement gets an excursion; a case file is a context with no
edit history, so what it states is the row as the answer it ended up being.
Prefilling is tested where it happens — in Kompass, against the API and the
admin — and a section's cases are about what its rules make of an answer.

An option source is resolved for a case too, out of the context the file
describes: the ``bills`` above are where ``options_source="bills.payers"``
finds member 7. A case's own answers are not validated against it — the case
runner types them and nothing more, the same as it has always done — but
``--fuzz`` answers a party-valued question out of exactly that set, so a
ruleset whose option source comes out empty is a ruleset the fuzzer will keep
offering nobody to.

.. _development_manual/finance_rules/settlement_group_cases:

How a case pins a settlement group
----------------------------------

Write the fifth element, and write it on both sides::

    "expect": {
      "transfers": [
        ["SECTION", "7", "24.00", "travel", ""],
        ["SECTION", "7", "15.00", "tour_leader_fee", "steuerrelevant"],
        ["PARTICIPANTS", "SECTION", "39.00", "participant_contribution", ""]
      ]
    }

That case says two things, and the second is the one that keeps working: the
Vergütung is in a group of its own, **and the travel costs are in none**. A
case that only names the group on the Vergütung would go on passing if a later
edit put every transfer in ``"steuerrelevant"`` — at which point the two merge
again, into one bank transfer, and the separation the section asked for is
gone with every check still green.

The comparison is per row and per width: a row of four is not compared on the
group, so every case written before groups existed passes unchanged, and a row
of five is compared on it exactly.

What a case **cannot** prove is the merging itself. A case runs the rules; it
has no database, no ledgers and no bookings, and what may share a bank transfer
is settled where the bookings are bundled. So a case pins the tokens and
Kompass's own suite pins what the tokens do to
``Statement.reduce_transactions`` — the same division of
labour as :meth:`~kompass.rules.Ruleset.approval`, which a case cannot assert
either.


Checking a ruleset
==================

``checkruleset`` runs the import check, loads the package, and runs its cases.
It touches no data, so it runs anywhere the image runs:

.. code-block:: console

   docker run --rm -v "$PWD":/app/config:ro \
       -e KOMPASS_CONFIG_DIR_PATH=/app/config \
       ghcr.io/chrisflav/kompass:<tag> \
       python jdav_web/manage.py checkruleset /app/config/rules --fuzz 200

``KOMPASS_CONFIG_DIR_PATH`` makes the fuzz use the numbers from the
``settings.toml`` beside the rules; the cases carry their own ``params``. The
command keeps the image's own working directory, ``/app``, which is where it
has to run — see the warning below.

``--fuzz N`` additionally builds ``N`` random but valid statements, asks the
ruleset what to ask the person, answers those questions at random *within the
domains the ruleset itself declared*, and checks the two things that must hold
whatever the answers are: that the rules report no error, and that the books
balance. It is not a proof and it is not a substitute for a case with an
expected figure — it is the cheapest way to find the rule that divides by a
participant count nobody checked for zero.

One round in four settles **no trip at all**. That is new, and it is worth
knowing before the next run of a ruleset that passed before: until now every
random statement had an excursion, so the arm of a declaration that answers
"and when there is no trip" was the one arm nothing random ever reached — which
is also the arm a ruleset is most likely to have got wrong, since a purchase or
a repair goes through it in production every week. A table whose cells are
seeded off the excursion has that arm by construction: with no trip there is no
seed, so the table arrives empty and whatever the rules do with an empty table
is what a real purchase statement will do.

A ``rows`` question is answered with between zero and :attr:`~kompass.rules.Input.max`
rows, each cell drawn from its own field's domain. Zero is in the range
deliberately: an empty table is the state a statement is in before anybody fills
it in and after somebody deletes the prefilled row, so a rule that divides by
the number of rows has to survive it.

A section's CI runs three commands, all three inside the image the instance
runs, so that the API module and the interpreter match production. They do
**not** share a working directory:

.. code-block:: console

   cd /app/config && mypy --strict rules      # reads ./pyproject.toml
   cd /app/config && ruff check rules          # reads ./pyproject.toml
   cd /app && python jdav_web/manage.py checkruleset /app/config/rules --fuzz 200

.. warning::
   The third command must not run from ``/app/config``. Kompass pulls in
   Celery, whose Django fixup inserts the working directory at the front of
   ``sys.path`` on purpose, and a configuration directory contains a
   ``rules/`` package — which is also the top-level name of ``django-rules``,
   a dependency and an installed app. From ``/app/config`` the section's own
   ruleset shadows it and ``django.setup()`` dies with ``No module named
   'rules.contrib'`` before a single rule is read.

   So ``checkruleset`` runs from ``/app``, exactly as the container
   entrypoint does, and is given the package by absolute path. ``mypy`` and
   ``ruff`` do need ``/app/config`` as their working directory, because that
   is where their ``pyproject.toml`` is; neither imports Django, so neither
   is affected.

The exact invocation — the mount, the environment and where ``mypy`` and
``ruff`` come from, since the image carries the application's dependencies and
not a toolchain — is ``.github/workflows/check-rules.yml`` in
``deploy/config-template/``.

``mypy --strict`` is worth having because the accessors are typed: a
``Decimal + bool``, a destination that is an ``int`` rather than a
:class:`~kompass.rules.Member`, a rule that forgot
:attr:`~kompass.rules.RuleContext.excursion` may be ``None`` — all of those are
a file and a line rather than an error on somebody's statement. ``ruff``, with
the banned-import rules the template ships, reports a forbidden import as a
lint failure in your own CI instead of a rejected version in the admin.

A section without CI has ``checkruleset`` by hand and the admin's dry run.
That is less, and it is stated as less.


API reference
=============

.. currentmodule:: kompass.rules

The ruleset
-----------

.. autoclass:: Ruleset
   :members:

.. py:data:: CONTEXT_VERSION
   :type: int
   :value: 1

   The version of the context shape this Kompass offers. A ruleset declares
   the version it was written against in :attr:`Ruleset.context_version`, and
   Kompass refuses to load one written for a newer context. Changes are
   additive — a field is added, never renamed or removed — so a ruleset
   written against version 1 keeps working.

.. autoexception:: RuleError

The context
-----------

.. autoclass:: RuleContext()
   :members:

.. autoclass:: Excursion
   :members:

.. autoclass:: Participant
   :members:

.. autoclass:: LJP
   :members:

.. py:data:: LJPGoal
   :value: Literal["qualification", "participation", "development", "environment"]

   The learning goal of a Landesjugendplan proposal.

.. py:data:: TourApproach
   :value: Literal["muscle", "public", "car"]

   How the group travelled: on muscle power, by public transport, or by car.

.. autoclass:: Bill
   :members:

.. autoclass:: StatementInfo
   :members:

.. autoclass:: Inputs()
   :members:

.. autoclass:: Params()
   :members:

.. autoclass:: Roles()
   :members:
   :exclude-members: get

   .. py:method:: get(role, default=())

      The holders of ``role``, or ``default`` when nobody holds it.

      Documented here rather than inherited: the signature comes from
      :class:`~collections.abc.Mapping`, but the behaviour does not. The
      default is ``()`` rather than ``None``, and on a context that did not
      resolve the role assignments this **raises**
      :class:`RuleError` instead of returning the default — which is the whole
      point of the unresolved state, and the opposite of what
      ``Mapping.get``'s own docstring says.

Parties
-------

.. autoclass:: Member
   :members:

.. autoclass:: Section
   :members:

.. autoclass:: Participants
   :members:

.. py:data:: SECTION
   :type: Section
   :value: Section()

   The section — the one instance of :class:`Section`.

.. py:data:: PARTICIPANTS
   :type: Participants
   :value: Participants()

   The participants as one party — the one instance of :class:`Participants`.

.. py:data:: Party
   :value: Member | Section | Participants

   Anything that can be one end of a :class:`Transfer`.

.. py:data:: MemberId
   :value: NewType("MemberId", int)

   A member's primary key, and the only identity a rule ever sees. Names,
   addresses and bank details are resolved by the engine after evaluation, so
   that a ruleset cannot leak them.

What a ruleset returns
----------------------

.. autoclass:: Transfer
   :members:

.. autoclass:: Input
   :members:

.. autoclass:: Choice
   :members:

.. autoclass:: Field
   :members:

.. autoclass:: Row()
   :members:

.. py:data:: InputType
   :value: Literal["money", "int", "bool", "text", "choice", "member", "member_set", "rows"]

   The widget vocabulary an :class:`Input` is rendered with. It is
   presentation, not rule structure: see
   :ref:`development_manual/finance_rules/widgets` for what each one is and
   how its answer is read. ``rows`` is the one entry that is a shape rather
   than a widget — see :ref:`development_manual/finance_rules/rows`.

.. py:data:: CELL_TYPES
   :value: ("money", "int", "bool", "text", "choice", "member", "member_set")

   The types a :class:`Field` — a cell of a ``rows`` question — may have:
   :data:`InputType` without ``rows``, because there is no table inside a
   table.

.. py:data:: SOURCE_ROOTS
   :value: ("excursion", "statement")

   The context fields an :attr:`Input.source` may start at. A source is
   ``"<root>.<field>"``, one field deep, and the field has to be a real field
   of what that root holds — see
   :ref:`development_manual/finance_rules/derived`.

.. py:data:: OPTION_SOURCES
   :value: ("excursion.leaders", "excursion.participants", "bills.payers", "statement.creator", "statement.submitter")

   Where an :attr:`Input.options_source` may take a party-valued question's
   people from. A fixed vocabulary rather than a path, so that no spelling of
   it reaches somebody the statement does not already mention — see
   :ref:`development_manual/finance_rules/options`.

.. autoclass:: Check
   :members:

.. autoclass:: Constraint
   :members:

.. autoclass:: Forbid
   :members:

Helpers
-------

.. autofunction:: split

.. autofunction:: pct

.. autofunction:: quantize

.. autofunction:: first_of

.. py:data:: CENT
   :type: Decimal
   :value: Decimal("0.01")

   One cent — the resolution of every amount in a :class:`Transfer`.

.. py:data:: SETTLEMENT_GROUP_LENGTH
   :type: int
   :value: 50

   How long a :attr:`Transfer.settlement_group` token may be — the width of
   the column it is stored in. A longer one is an error on the statement
   rather than a value cut to fit; see
   :ref:`development_manual/finance_rules/settlement_groups`.
