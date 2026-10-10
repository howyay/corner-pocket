"""The identity of one refusal: a stable ``code`` and the Chinese sentence for the operator.

The service writes each refusal sentence in English (``operator_message``).  The operator
reads Chinese.  The console (annotator/ops.js) used to hold its own copy of that Chinese
keyed by the English sentence, so rewording one sentence in python quietly dropped the
Chinese for every operator.

This module owns that copy.  One row per refusal the console must know:

    English sentence -> Refusal(code, zh)

The sentence is the exact argument a raise site passes to ``ValueError`` or ``APIError``.
``zh`` is the Chinese sentence, moved here byte for byte from the console.  A sentence
with no row here keeps the English sentence, and the console then shows its own generic
Chinese line.  ``tests/test_refusal_identity.py`` pins how many raised sentences have no
row, so no one adds a refusal without a decision about this table.

A few refusals name facts inside the sentence: the channel a VOD belongs to, the free
space an import needs, the id of the import that already runs.  Their sentence cannot be a
key of the table, because the service builds it.  The ``FactRefusal`` rows below hold both
templates and the field names, and the small functions under them fill both languages from
one set of facts.  ``tests/test_job_refusal_identity.py`` holds a code to a raise site.
"""
from typing import NamedTuple


class Refusal(NamedTuple):
    """One refusal the console must know: the token it reads and the line it shows."""

    code: str
    zh: str


# The body keys the service sends beside ``error`` (annotator/unified_server.py).
CODE_KEY = "code"
ZH_KEY = "zh"

# English sentence -> identity.  Keep the order of the sentences you add.
REFUSALS = {
    'Player name already exists': Refusal('player_name_exists', '球员姓名已存在。'),
    'The pairing changed; review the teams again': Refusal('pairing_changed', '配对已变化，请重新查看组合。'),
    'An even number of solo players is needed to pair': Refusal('pairing_needs_even_solo', '需要偶数名单人报名者才能配对。'),
    'Registration is locked while a pairing is shown; accept or clear it first': Refusal('pairing_locked_registration', '正在显示配对结果，请先采用或清除。'),
    'Random pairing is for doubles': Refusal('pairing_random_doubles_only', '随机配对仅用于双打。'),
    'No pairing to accept': Refusal('pairing_none', '没有可采用的配对。'),
    'Remove solo players before changing format': Refusal('format_solo_players_present', '请先移除单人报名者，再更改赛制。'),
    'No round-2 bye slot to fill': Refusal('bye_slot_none', '没有可填补的第二轮轮空位。'),
    'No round-1 loser to draw from': Refusal('revival_draw_pool_empty', '首轮没有可抽取的负者。'),
    'Finish round 1 first; every round-1 loser must be in the draw': Refusal('revival_draw_round1_open', '请先完成首轮，所有首轮负者都要参加抽签。'),
    'Round 2 has a signed result; the draw is closed': Refusal('revival_draw_closed_signed', '第二轮已有签署的赛果，抽签已关闭。'),
    'A second chance was already drawn for this event': Refusal('revival_draw_already', '本场赛事已经抽过复活名额。'),
    'Undo is closed: a result has been signed since the draw': Refusal('revival_undo_closed_signed', '抽签后已有新的签署赛果，无法撤销。'),
    'No revival draw to undo': Refusal('revival_undo_none', '没有可撤销的复活抽签。'),
    'An event with a signed result cannot be deleted; hide it from history instead': Refusal('event_delete_signed', '有已签赛果的赛事不能删除，请改为从历史中隐藏。'),
    'Only an archived event can be hidden': Refusal('event_hide_not_archived', '只能隐藏已归档的赛事。'),
    "A bye is added by the draw; type the guest's real name": Refusal('guest_name_is_bye', '轮空由抽签自动安排，请输入访客的真实姓名。'),
    'Name held by a guest in this event; add the guest to the regulars instead': Refusal('guest_name_held_by_guest', '这个名字属于本场赛事的一位访客；请把该访客加入常客，而不是给常客改成同名。'),
    'Player name already exists; select the regular by id': Refusal('player_name_select_regular', '该姓名已属于常客，请从常客名单选择。'),
    'Player name already exists; cannot infer guest identity': Refusal('player_name_guest_ambiguous', '该姓名已存在，无法确定访客身份。'),
    'Player has tournament history; mark Inactive instead': Refusal('player_has_history', '球员已有赛事记录，请改为停用而非删除。'),
    'Remove entrants before changing format': Refusal('format_entrants_present', '请先移除参赛者，再更改赛制。'),
    'Tournament already started': Refusal('tournament_started', '赛事已经开始。'),
    'Registration is closed': Refusal('registration_closed', '报名已关闭。'),
    'Person already registered': Refusal('person_registered', '此人已经报名。'),
    'Inactive player': Refusal('player_inactive', '该球员已停用。'),
    'Need an unstarted tournament with at least two entrants': Refusal('tournament_not_ready', '请至少登记两名参赛者，并确保赛事尚未开始。'),
    'Wrong number of team members': Refusal('team_size_wrong', '队伍人数不符合赛制。'),
    'Maximum 128 entrants': Refusal('entrants_max', '最多允许128名参赛者。'),
    'Match is not editable': Refusal('match_not_editable', '此比赛当前不可编辑。'),
    'Absent player; match held': Refusal('player_absent', '有球员缺席，比赛暂缓。'),
    'Table is occupied': Refusal('table_occupied', '球台已被占用。'),
    'All tables are in use': Refusal('tables_all_in_use', '所有球台都在使用中，请先释放一张球台。'),
    'Source already added': Refusal('source_exists', '这个直播源已经添加过了。'),
    'image_base64 is not a decodable image': Refusal('image_not_decodable', '无法读取这张图片，请换一张 JPEG 或 PNG 照片。'),
    'Use a Twitch channel or videos/<digits> URL': Refusal('source_url_twitch_channel_or_video', '请输入Twitch频道网址或 videos/<数字> 视频网址。'),
    'Match is not on a table': Refusal('match_not_on_table', '此比赛尚未上台。'),
    'Schedule match before scoring': Refusal('match_not_scheduled', '请先安排比赛上台，再记录比分。'),
    'Two scores required': Refusal('score_both_required', '请填写双方比分。'),
    'Both players cannot win': Refusal('score_both_winners', '双方不能同时达到获胜比分。'),
    'A live race-winning score is required': Refusal('score_race_winner_required', '请先填写进行中比赛的有效获胜比分。'),
    'Explicit confirmation required': Refusal('confirmation_required', '需要明确确认此操作。'),
    'Unknown id': Refusal('unknown_id', '找不到此记录，请刷新后重试。'),
    'Invalid format': Refusal('format_invalid', '赛制无效。'),
    'Invalid player status': Refusal('player_status_invalid', '球员状态无效。'),
    'Player notes must be text up to 4000 characters': Refusal('player_notes_too_long', '球员备注最多4000字。'),
    'State changed; reload before retrying': Refusal('revision_conflict', '数据已被修改，请刷新后重试。'),
    'Use an HTTPS Twitch channel or video URL without query parameters': Refusal('source_url_https_no_query', '请输入不带查询参数的HTTPS Twitch频道或视频网址。'),
}


class FactRefusal(NamedTuple):
    """One refusal whose sentence names facts, so its Chinese is a template too.

    ``en`` and ``zh`` hold the same placeholder names, and ``fields`` names the facts the
    sentence carries.  Fill both templates from one set of facts, and never send a template:
    a placeholder that reaches the operator is a broken line.
    """

    code: str
    en: str
    zh: str
    fields: tuple


# A job refusal names facts, so the service builds its sentence from them.  The English and
# the Chinese template are spelled here, once each.  The English sentence is the operator's
# text and it stays byte for byte as it was before this work.
CHANNEL_REFUSAL = FactRefusal(
    'vod_channel_not_saved',
    "This VOD belongs to {channel}. Only saved channels can be analysed; "
    "add the channel under Source first.",
    '此回放属于 {channel}。只能分析已保存的频道；请先在“来源”中添加该频道。',
    ('channel',))

DISK_REFUSAL = FactRefusal(
    'vod_disk_space',
    "Not enough free disk space: this import needs {needed} (about {estimate} "
    "estimated x 1.2 + 2 GB reserve) and {free} is free. "
    "Import a shorter range or free some space first.",
    '磁盘空间不足：本次导入需要 {needed}（按 {estimate} 估算 × 1.2，另留 2 GB 余量），'
    '当前可用 {free}。请缩短导入范围，或先释放一些空间。',
    ('needed_bytes', 'estimate_bytes', 'free_bytes'))

# The refusals of the import slot.  Their sentence names the import it talks about, and the
# operator's English line keeps that id.  The Chinese line names the state, not the id: the
# served field ``id`` carries the id beside it.
ALREADY_STARTING = Refusal('vod_already_starting', '已有一个导入正在启动，请等待它，或先取消。')
ALREADY_RUNNING = Refusal('vod_already_running', '已有一个导入在运行，请等待它结束，或先取消。')
ALREADY_IMPORTED = Refusal('vod_already_imported', '这一段已经导入；要再次导入，请先删除它。')

#: The import-slot refusals by the short name the service builds them with.
JOB_REFUSALS = {'already_starting': ALREADY_STARTING, 'already_running': ALREADY_RUNNING,
                'already_imported': ALREADY_IMPORTED}


def gb(count):
    """A byte count as both sentences write it (``annotator/vod_import.py`` re-exports this)."""
    return f"{count / 1e9:.1f} GB"


def channel_refusal(channel):
    """The channel refusal: the sentence, and the identity beside it.

    ``channel`` is the channel the VOD belongs to.  An empty name becomes the sentence's own
    words for a channel Twitch did not name, so the operator never reads a blank.
    """
    named = channel or "a channel Twitch did not name"
    return (CHANNEL_REFUSAL.en.format(channel=named),
            {CODE_KEY: CHANNEL_REFUSAL.code, ZH_KEY: CHANNEL_REFUSAL.zh.format(channel=named),
             'channel': named})


def disk_refusal(needed_bytes, estimate_bytes, free_bytes):
    """The disk refusal: the sentence, and the identity beside it.

    The identity names the three byte counts the sentence prints, so the console reads the
    numbers as data and never parses them back out of the text.
    """
    text = {'needed': gb(needed_bytes), 'estimate': gb(estimate_bytes), 'free': gb(free_bytes)}
    return (DISK_REFUSAL.en.format(**text),
            {CODE_KEY: DISK_REFUSAL.code, ZH_KEY: DISK_REFUSAL.zh.format(**text),
             'needed_bytes': needed_bytes, 'estimate_bytes': estimate_bytes, 'free_bytes': free_bytes})


def job_identity(name, **facts):
    """The identity of one import-slot refusal: its code, its Chinese, and its named facts."""
    row = JOB_REFUSALS[name]
    return {CODE_KEY: row.code, ZH_KEY: row.zh, **facts}


def of(sentence):
    """The ``Refusal`` of one sentence, or ``None`` when python holds no row for it."""
    return REFUSALS.get(sentence)


def identity_fields(sentence):
    """The body keys and values that identify one refusal.

    The result is empty for a sentence with no row, so an unknown refusal adds nothing to
    the body.
    """
    found = of(sentence)
    if found is None:
        return {}
    return {CODE_KEY: found.code, ZH_KEY: found.zh}
