"""The one home of the edit rules that both stores apply to one operator record.

`src/store.py` (JsonStore) and `src/store_pg.py` (PostgresStore) store the same
operator records. JsonStore writes the JSON file. PostgresStore writes the stored
document and projects its rows. Both apply the same edit rules to a record, and
before round 56 each class held its own copy of every rule. The walk of round 56
measured the shared statements of the four mutators:

  * `JsonStore:seed_put` and `PostgresStore:seed_put`: 5 shared statements, and 3 of
    them held one rule (the delete and the merge),
  * `JsonStore:verdict_put` and `PostgresStore:verdict_put`: 4, and 1 held one rule
    (the merge),
  * `JsonStore:label_put` and `PostgresStore:label_put`: 6, and 2 held two rules
    (the lookup and the clear),
  * `JsonStore:anchors_put` and `PostgresStore:anchors_put`: 2, and 1 held one rule
    (the float spelling).

So each class held six statements of five rules, and 17 statements in all were
copies. The other 11 statements are plumbing that both bodies must hold.

The two copies could drift in silence. The guard that compares the two backends
(`tests/test_store_contract.py`) skips its Postgres cases when POOL_DATABASE_URL is
unset, and that is the state of a default run. `PostgresStore.label_put` admitted
the copy in its own docstring: "a new key (`new_key`, else the basename) is
appended - JsonStore.label_put exactly."

One rule now has one home: this module. It holds pure functions only. It holds no
store, no file, and no database, so both classes import it without a second import
path. The five rules are:

  * `merge_record` merges the incoming fields of one record into the stored fields.
  * `drop_key` removes one key, and it is quiet when the key is absent.
  * `clear_keys` removes every key of one sequence, and it is quiet for each one.
  * `keys_for_basename` finds the stored keys whose file name matches one crop file.
  * `spelled_time` answers the stored spelling of one anchor time key.

The callers keep every side effect: the lock, the file write, the stored document,
and the row projection. This module changes no byte of a stored document.
"""
from __future__ import annotations

__all__ = ["merge_record", "drop_key", "clear_keys", "keys_for_basename", "spelled_time"]

from pathlib import Path


def merge_record(stored: dict, incoming: dict) -> dict:
    """Merge the fields of one incoming record into the stored fields of that record.

    `incoming` wins, so a field present in both mappings takes the incoming value.
    The function returns a new dict. It does not change either argument.

    This function closes the defect of round 56: the merge of one record sat in
    `src/store.py:281` and in `src/store_pg.py:288`, and one edit had to land in
    both sites.
    """
    return dict(stored, **incoming)


def drop_key(store: dict, key) -> None:
    """Remove one key from a mapping, and answer None.

    An absent key is not an error, so a caller can clear a record twice.

    This function closes the defect of round 56: the delete of one key sat in
    `src/store.py:279` and in `src/store_pg.py:286`.
    """
    store.pop(key, None)


def clear_keys(store: dict, keys) -> None:
    """Remove every key of one sequence from a mapping, and answer None.

    The function keeps the order of the sequence. An absent key is not an error.
    The `label_put` rule of both stores calls this function, because one crop file
    can match more than one stored key.

    This function closes the defect of round 56: the clear of one crop sat in the
    `for` loop of `src/store.py:318` and of `src/store_pg.py:354`.
    """
    for key in keys:
        store.pop(key, None)


def keys_for_basename(store: dict, crop_file: str) -> list:
    """Answer the keys of one mapping whose file name is `crop_file`.

    The answer keeps the order of the mapping, so the first key is the first match
    of the mapping. A caller uses that key and removes the other matches.

    This function closes the defect of round 56: the lookup of a key by basename
    sat in `src/store.py:316` and in `src/store_pg.py:352`.
    """
    return [key for key in store if Path(key).name == crop_file]


def spelled_time(store: dict, t_key: str) -> str:
    """Answer the stored spelling of one anchor time key, or `str(t_key)`.

    A stored key wins when its number is the number of `t_key`, because an existing
    key keeps its original spelling. The function answers `str(t_key)` when the
    mapping holds no such key.

    This function closes the defect of round 56: the float spelling of one anchor
    time sat in `src/store.py:345` and in `src/store_pg.py:396`.
    """
    return next((key for key in store if float(key) == float(t_key)), str(t_key))
