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
inside ``inputs`` already works — but a ruleset that overrides
``relevant_inputs`` is overriding the method the form actually calls, while
the case runner, the fuzzer and the stored declarations go through ``inputs``.
Keep the two consistent, or the question a person is asked and the answer a
rule reads come apart.


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
     - :meth:`~kompass.rules.Inputs.raw`
     - **In the vocabulary, not yet usable** — see the warning below.
   * - ``member``
     - :meth:`~kompass.rules.Inputs.member`
     - One person out of :attr:`~kompass.rules.Input.options`. Unanswered:
       ``None``.
   * - ``member_set``
     - :meth:`~kompass.rules.Inputs.members`
     - Several people out of :attr:`~kompass.rules.Input.options`, at most
       :attr:`~kompass.rules.Input.max` of them. Unanswered: ``()``.

For ``member`` and ``member_set``, the engine re-validates a submitted answer
against the options the declaration offered, so an answer can never name
somebody the rule did not offer. A rule cannot widen the set by returning a
wider one from somewhere else either: the leaders in
:attr:`~kompass.rules.Excursion.leaders` are re-checked too.

Which *keys* may be declared is a separate and much tighter restriction than
which types exist — see
:ref:`development_manual/finance_rules/four_keys`.

.. warning::
   **Do not use** ``choice`` **yet** (**#573**). It is in the vocabulary and
   the form renders it, but there is no way to say what may be chosen:
   :attr:`~kompass.rules.Input.options` is ``tuple[Member, ...]`` and
   ``finance/inputs.py::options_for`` resolves it through
   ``Member.objects.in_bulk``, so a ``choice`` arrives with an empty option
   list and ``clean_value`` falls through to "anything else is text" — it
   accepts any string at all.

   Worse, the unanswered value is ``None`` while
   :meth:`~kompass.rules.Inputs.text` type-checks against ``str``, so reading
   an unanswered ``choice`` with the accessor its type suggests raises
   :class:`~kompass.rules.RuleError` — and because that happens inside
   :meth:`~kompass.rules.Ruleset.transfers`, it collapses the whole evaluation
   into one error rather than reporting a missing answer.

   Until #573, a fixed set of alternatives is a ``bool`` per alternative, or a
   ``text`` input whose value a check validates. If you must use ``choice``,
   read it with :meth:`~kompass.rules.Inputs.raw` and test for ``None``
   before anything else — and know that nothing validates what came in.


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
* ``errors`` is the list of messages :meth:`~kompass.rules.Ruleset.transfers`
  returned, compared exactly.
* ``checks`` is the expected ``ok`` state of each check, in order. Leaving the
  key out means the case does not look at them.
* ``permissions`` maps a codename to the ids that hold it, for a ruleset whose
  rules read :meth:`~kompass.rules.RuleContext.permission_holders`.

The format is implemented in ``jdav_web/finance/engine/cases.py``, which is
also where a new key would be added.

.. _development_manual/finance_rules/four_keys:

Only four input keys can be answered today
------------------------------------------

.. danger::
   This is the one restriction on this page that can cost money, and it is a
   restriction of the **running instance**, not of the case runner.

   A statement does not yet store its answers in one field. It has four
   columns, the ones the reference ruleset happens to need, and
   ``finance/engine/context.py::statement_inputs`` returns exactly those:
   ``night_cost``, ``allowance_to``, ``subsidy_to`` and ``ljp_to``. A
   declaration under any other key has nowhere to be stored, so
   ``finance/engine/evaluation.py::_answered`` substitutes that type's empty
   value — ``0.00``, ``0``, ``False``, ``""``, ``None`` or ``()`` — on every
   evaluation. The person is asked the question, the answer goes nowhere, and
   the rule reads a zero. Nothing raises and nothing warns.

   :meth:`~kompass.rules.Inputs.raw` does not get round it: the key is present
   in the mapping, holding the empty value. There is nothing else to read.

   **A case will not catch it**, which is what makes it dangerous.
   ``cases.py::_inputs`` coerces those same four keys and passes any other key
   through as JSON wrote it, so a case that answers a custom key proves
   something the instance will never do: the case goes green and production
   pays zero.

   Until the answers move into one JSON field (step 3 of the refactor,
   **#556**, in flight), a rule may only read those four keys — and a section
   whose policy needs another number puts it in the ruleset as a module
   constant, where it is versioned with the rules, rather than declaring an
   input for it.

   One consequence of the four keys being the reference ruleset's: their
   *types* are fixed too — ``night_cost`` is ``money``, ``allowance_to`` is
   ``member_set``, ``subsidy_to`` and ``ljp_to`` are ``member``. A declaration
   that reuses a key with a different type gets the column's value, not the
   declared type's.

..
   MAINTENANCE: when #556 lands — the answers moving into one JSON field —
   this whole section shrinks to a sentence about the case runner coercing
   only the four keys, the "which keys" sentence under the widget table goes
   away, and the comment in `deploy/config-template/rules/__init__.py` and the
   README's Ludwigsburg table need the same edit. #556 is in flight and may
   land right after this page.


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

.. py:data:: InputType
   :value: Literal["money", "int", "bool", "text", "choice", "member", "member_set"]

   The widget vocabulary an :class:`Input` is rendered with. It is
   presentation, not rule structure: see
   :ref:`development_manual/finance_rules/widgets` for what each one is and
   how its answer is read.

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
