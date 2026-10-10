"""The dataset-id contract: one corpus of spellings, and the verdict the rule gives.

The rule for a dataset column is written twice, once for each side of the boundary:

  * `src/datasets.parse_imported_id` (and the built-in names of `src.datasets.STATIC_OUT`)
    is the rule Python applies.
  * `db/migrations/0004_imported_datasets.sql:24-31` states the same rule in SQL
    (`dataset_id_ok`), and the four `dataset` columns check it.

The migration comment claims the two are "measured equal on 25 edge cases". This corpus is
that measurement, made executable: every line holds one spelling and the verdict both sides
must give it. The verdict is a hand-written record of the rule, read from the two statements
above, not a call to either implementation - a corpus that asks the code what to expect
cannot find the code wrong.

The built-in names are the one place the two sides differ, and the difference is by design:
`dataset_id_ok` covers them because it guards every dataset column, while `parse_imported_id`
parses imported ids only.
"""

#: The two published recordings. `src.datasets.STATIC_OUT` is the owner of these names.
BUILT_IN = ("vod30", "highlight")

#: (spelling, the verdict the dataset columns give it)
CASES = (
    ("vod30", True),                        # a published recording
    ("highlight", True),                    # the other published recording
    ("vod31", False),                       # not a published name and not an imported id
    ("VOD30", False),                       # the names are case sensitive
    ("", False),
    ("tw", False),
    ("tw-", False),                         # no VOD id
    ("tw-0", False),                        # a VOD id of zero
    ("tw-123", True),                       # a whole VOD
    ("tw-1", True),
    ("tw-0123", False),                     # leading zeros are not canonical
    ("tw-000", False),
    ("tw-123456789012", True),              # twelve digits, the most a VOD id may have
    ("tw-999999999999", True),
    ("tw-1234567890123", False),            # thirteen digits
    ("tw-9999999999999", False),
    ("tw-123-0-5", True),                   # a range may start at zero
    ("tw-123-5-9", True),
    ("tw-123-5-5", False),                  # start must be before end
    ("tw-123-9-5", False),
    ("tw-123-5", False),                    # half a range
    ("tw-123-", False),
    ("tw-123--5", False),
    ("tw-123-05-9", False),                 # leading zeros in a range are not canonical
    ("tw-123-5-09", False),
    ("tw-123-00-01", False),
    ("tw-1-9-5", False),
    ("tw-1-0-1", True),
    ("tw-1-1-2", True),
    ("tw-0123-1-2", False),
    ("tw-123456789012-1-2", True),
    ("tw-000000000001-1-2", False),
    ("tw-123-1-2-3", False),                # a second range
    ("tw-123-1-2 ", False),                 # a trailing space
    (" tw-123", False),                     # a leading space
    ("tw-123\n", False),                    # a trailing newline
    ("TW-123", False),
    ("Tw-123", False),
    ("tw-+123", False),
    ("tw-1e3", False),
    ("tw-123.0", False),
    ("tw-١٢٣", False),           # Arabic-Indic digits are not [0-9]
    ("tw-１２３", False),           # full-width digits are not [0-9]
    ("tw-1-0000000000000000000001-2", False),   # the seconds are not canonical either
    ("tw-1-1-" + "9" * 57, True),           # 64 characters, the most an id may have
    ("tw-1-1-" + "9" * 58, False),          # 65 characters
    ("vod30 ", False),
    ("vod30\n", False),
    ("out/vods/tw-123", False),             # a path is not an id
    ("tw-123/../x", False),
)
