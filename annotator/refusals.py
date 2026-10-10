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
row, so no one adds a refusal without a decision about this table.  Every raised sentence
has a row now, so the pinned number is zero and a new refusal cannot arrive without one.

A few refusals name facts inside the sentence: the channel a VOD belongs to, the free
space an import needs, the id of the import that already runs.  Their sentence cannot be a
key of the table, because the service builds it.  The ``FactRefusal`` rows below hold both
templates and the field names, and the small functions under them fill both languages from
one set of facts.  ``tests/test_job_refusal_identity.py`` holds a code to a raise site.

``TEMPLATES`` at the end of this module holds the sentences the service builds from values it
computed: a validation rule, the exit code of ffmpeg, a channel a scan could not list.  Each of
those sentences reads differently for every caller, so the table holds a skeleton with
placeholder names, not a finished sentence.  A raise site passes the skeleton by name and never
an f-string, so the sentence is built in one place and the tests that count the sentences a
raise site states keep their count.  ``tests/test_refusal_templates.py`` pins those rows.
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

    # The sentences that had no row here: every refusal the two raising modules could hand the
    # operator as English only, with the console's own generic Chinese line under it.  Each key
    # is copied from its raise site byte for byte, and each Chinese sentence reuses the words of
    # the rows above and of the console (annotator/ops.js, annotator/vision-stage.js): 来源,
    # 频道, 球员, 比赛, 球台, 参赛者, 配对, 比分, 帧, 片段, 数据集.  A fact inside a sentence (a
    # field name, a status, an id, a byte count) keeps its English spelling in both languages.
    # They are in the order of the module that raises them, operations.py first.
    'operation needs a name': Refusal('operation_name_required', '操作缺少名称。'),
    'channel must be a Twitch channel login': Refusal('channel_not_twitch_login', 'channel 必须是 Twitch 频道登录名。'),
    'Unknown event': Refusal('event_unknown', '找不到该赛事。'),
    'A range needs both startS and endS': Refusal('range_needs_both_bounds', '一个范围要同时给出 startS 和 endS。'),
    'endS must be after startS': Refusal('end_before_start', 'endS 必须晚于 startS。'),
    'Unknown link': Refusal('link_unknown', '找不到该关联。'),
    "This broadcast is this event's own import record; delete or hide the event instead": Refusal('unlink_vod_own_import', '这段直播是本场赛事自己的导入记录；请改为删除或隐藏该赛事。'),
    'JSON object required': Refusal('json_object_required', '需要 JSON 对象。'),
    'integer revision required': Refusal('revision_not_integer', 'revision 必须是整数。'),
    'Invalid member': Refusal('member_invalid', '成员无效。'),
    'That person is not eligible for the second chance': Refusal('revival_entrant_not_eligible', '此人没有复活赛资格。'),
    'A new opponent needs a name': Refusal('late_opponent_name_required', '新对手需要姓名。'),
    'A new teammate needs a name': Refusal('late_partner_name_required', '新队友需要姓名。'),
    'That person cannot play on both sides of the match': Refusal('late_person_both_sides', '此人不能同时在这场比赛的双方出场。'),
    'datasetId must be an imported dataset id such as tw-1234567890-452-1690': Refusal('dataset_id_not_imported', 'datasetId 必须是已导入的数据集 id，例如 tw-1234567890-452-1690。'),
    'channel does not match the channel this range was imported from': Refusal('backfill_channel_mismatch', '频道与导入这段范围时记录的频道不一致。'),
    'This broadcast is not a saved source and was not imported; add its channel or the VOD under Source first': Refusal('backfill_source_not_saved', '这段直播既不是已保存的来源，也没有导入过；请先在来源里添加它的频道或 VOD。'),
    'entrants must be a non-empty list': Refusal('entrants_not_non_empty_list', 'entrants 必须是非空列表。'),
    'Invalid entrant': Refusal('entrant_invalid', '参赛者无效。'),
    'Player name already exists; send the regular as their player id': Refusal('player_name_send_player_id', '球员姓名已存在，请改用该常客的 pid 传入。'),
    'Two entrants name the same regular': Refusal('entrants_same_regular', '有两名参赛者指向同一位常客。'),
    'Two entrants share an id': Refusal('entrants_same_id', '有两名参赛者共用同一个 id。'),
    'Two entrants share a name': Refusal('entrants_same_name', '有两名参赛者同名。'),
    'Every side and winner must name one of the entrants': Refusal('backfill_side_unknown_entrant', '每一方和胜者都必须指向参赛者之一。'),
    'matches must be a non-empty list': Refusal('matches_not_non_empty_list', 'matches 必须是非空列表。'),
    'Invalid match': Refusal('match_invalid', '比赛无效。'),
    'Two sides required': Refusal('match_two_sides_required', '需要两方。'),
    'A match needs two different entrants': Refusal('match_two_entrants_differ', '一场比赛需要两名不同的参赛者。'),
    'winner must be one of the two sides': Refusal('winner_not_a_side', '胜者必须是两方之一。'),
    "result must be 'played' or 'forfeit'": Refusal('result_not_played_or_forfeit', "result 只能是 'played' 或 'forfeit'。"),
    'clip must be [start, end] in whole seconds': Refusal('clip_range_invalid', 'clip 必须是 [start, end]，单位为整秒。'),
    'clip end must be after clip start': Refusal('clip_end_before_start', '片段的结束必须晚于片段开始。'),
    'event object required': Refusal('event_object_required', '需要 event 对象。'),
    'source object required': Refusal('source_object_required', '需要 source 对象。'),
    'Every result must be confirmed by a person: source.humanReviewed must be true': Refusal('backfill_human_review_required', '每一条赛果都必须由人确认：source.humanReviewed 必须为 true。'),
    "source.kind must be 'vod-backfill'": Refusal('source_kind_not_vod_backfill', "source.kind 必须是 'vod-backfill'。"),
    'Unknown operations action': Refusal('operations_action_unknown', '找不到该操作。'),
    'Exactly one unregistered current tournament guest is required': Refusal('guest_promote_needs_one', '需要恰好一名本场赛事中尚未登记的访客。'),
    'absent must be boolean': Refusal('absent_not_boolean', 'absent 必须是布尔值。'),
    'The tournament is not running': Refusal('tournament_not_running', '赛事没有在进行中。'),
    'Choose the match-up: nobody, a second chance, or a new player': Refusal('late_opponent_choice_required', '请选择对手：无人、复活赛，还是新球员。'),
    'Choose the teammate for a doubles event': Refusal('late_partner_choice_required', '请为这场双打赛事选择队友。'),
    'A teammate needs a doubles event': Refusal('partner_needs_doubles', '只有双打赛事才有队友。'),
    'The draw has not started': Refusal('revival_draw_not_started', '抽签还没开始。'),
    'hidden must be boolean': Refusal('hidden_not_boolean', 'hidden 必须是布尔值。'),
    'Invalid cloth color': Refusal('cloth_color_invalid', '台呢颜色无效。'),
    'lampGlow must be between 0 and 0.5': Refusal('lamp_glow_out_of_range', 'lampGlow 必须在 0 到 0.5 之间。'),
    'showDiamonds must be boolean': Refusal('show_diamonds_not_boolean', 'showDiamonds 必须是布尔值。'),
    'autoFrame must be boolean': Refusal('auto_frame_not_boolean', 'autoFrame 必须是布尔值。'),
    'publicBoard must be boolean': Refusal('public_board_not_boolean', 'publicBoard 必须是布尔值。'),
    'write needs a name': Refusal('write_name_required', '写入缺少名称。'),
    'invalid media path': Refusal('media_path_invalid', '媒体路径无效。'),
    'media not found': Refusal('media_not_found', '找不到该媒体文件。'),
    'vod_id is required: a Twitch VOD id or https://www.twitch.tv/videos/<id>': Refusal('vod_id_required', '必须给出 vod_id：Twitch VOD id 或 https://www.twitch.tv/videos/<id>。'),
    'start_s must be a non-negative number of seconds': Refusal('start_s_not_non_negative', 'start_s 必须是非负的秒数。'),
    'query must be a mapping of name to value': Refusal('query_not_mapping', 'query 必须是从名称到值的映射。'),
    'query must be a mapping of name to values': Refusal('query_values_not_mapping', 'query 必须是从名称到多个值的映射。'),
    'action must be start or stop': Refusal('live_action_invalid', 'action 只能是 start 或 stop。'),
    'unsupported live option': Refusal('live_option_unsupported', '不支持该直播选项。'),
    'clock accepts only action and duration': Refusal('clock_fields_invalid', 'clock 只接受 action 和 duration。'),
    'player_id must be a non-empty string': Refusal('player_id_required', 'player_id 必须是非空字符串。'),
    'image_base64 must be a base64 string': Refusal('image_not_base64_string', 'image_base64 必须是 base64 字符串。'),
    'image_base64 is not valid base64': Refusal('image_not_base64', 'image_base64 不是有效的 base64。'),
    'image_base64 decodes past the 8MB limit': Refusal('image_over_8mb', 'image_base64 解码后超过 8MB 上限。'),
    'cluster_id must be an integer': Refusal('cluster_id_not_integer', 'cluster_id 必须是整数。'),
    'track_id must be an integer': Refusal('track_id_not_integer', 'track_id 必须是整数。'),
    'no face data for this player': Refusal('face_data_none', '该球员没有人脸数据。'),
    'unknown dataset': Refusal('dataset_unknown', '找不到该数据集。'),
    'frame_index must be a non-negative integer': Refusal('frame_index_not_non_negative', 'frame_index 必须是非负整数。'),
    'bbox must be [x1, y1, x2, y2] in frame pixels': Refusal('enroll_bbox_invalid', 'bbox 必须是帧像素坐标 [x1, y1, x2, y2]。'),
    'another enrolment preview is running; try again when it finishes': Refusal('enroll_preview_busy', '另一个人脸录入预览正在运行，请等它结束后重试。'),
    'token is required (the one the preview returned)': Refusal('enroll_token_required', '必须给出 token，也就是预览返回的那个。'),
    'player_name must be a string': Refusal('player_name_not_string', 'player_name 必须是字符串。'),
    'enrolment scratch roster carries no enrolment event': Refusal('enrollment_event_missing', '人脸录入的临时名单里没有录入事件。'),
    'unknown ball set': Refusal('ball_set_unknown', '找不到该球组。'),
    'cannot open VOD': Refusal('vod_open_unavailable', '无法打开 VOD。'),
    'cannot read VOD metadata': Refusal('vod_metadata_unreadable', '无法读取 VOD 元数据。'),
    'cannot decode frame': Refusal('frame_decode_unavailable', '无法解码该帧。'),
    'cannot encode frame': Refusal('frame_encode_unavailable', '无法编码该帧。'),
    'video metadata unavailable': Refusal('video_metadata_unavailable', '视频元数据不可用。'),
    'frame_index must be an integer': Refusal('frame_index_not_integer', 'frame_index 必须是整数。'),
    'frame seek failed': Refusal('frame_seek_failed', '帧定位失败。'),
    'frame decode failed': Refusal('frame_decode_failed', '帧解码失败。'),
    'JPEG encoding failed': Refusal('jpeg_encode_failed', 'JPEG 编码失败。'),
    't must be seconds inside the video': Refusal('clip_time_outside_video', 't 必须是视频范围内的秒数。'),
    'clip window is empty at the end of the video': Refusal('clip_window_empty', '视频结尾处没有可截取的片段。'),
    'clip encoding timed out': Refusal('clip_encode_timeout', '片段编码超时。'),
    'clip encoding failed': Refusal('clip_encode_failed', '片段编码失败。'),
    'boxes must be a list with at most 200 entries': Refusal('correction_boxes_invalid', 'boxes 必须是列表，最多 200 项。'),
    'invalid box label': Refusal('box_label_invalid', '标注框的标签无效。'),
    'bbox must be [x1,y1,x2,y2]': Refusal('correction_bbox_invalid', 'bbox 必须是 [x1,y1,x2,y2]。'),
    'box must have positive width and height': Refusal('correction_box_degenerate', '标注框的宽度和高度必须为正。'),
    'table_polygon must have four points': Refusal('table_polygon_point_count', 'table_polygon 必须有四个点。'),
    'invalid table point': Refusal('table_point_invalid', '球台顶点无效。'),
    'table_polygon must have nonzero area': Refusal('table_polygon_zero_area', 'table_polygon 的面积不能为零。'),
    'another frame inference job is running': Refusal('frame_inference_busy', '另一个帧推理任务正在运行。'),
    'unknown event': Refusal('event_not_found', '找不到该事件。'),
    'route not found': Refusal('route_not_found', '找不到该接口。'),
    'feature only available for vod30': Refusal('vod30_only', '此功能仅适用于 vod30。'),
    'unknown window': Refusal('window_unknown', '找不到该窗口。'),
    'unknown crop': Refusal('crop_unknown', '找不到该裁剪图。'),
    'label required; use null to clear': Refusal('ball_label_required', '必须给出 label；要清除请传 null。'),
    'invalid ball label': Refusal('ball_label_invalid', '球的标签无效。'),
    'invalid verdict': Refusal('verdict_invalid', '判定无效。'),
    'invalid shooter': Refusal('shooter_invalid', '击球方无效。'),
    'invalid note': Refusal('note_invalid', '备注无效。'),
    'six anchor points required': Refusal('anchors_six_required', '需要六个锚点。'),
    'each anchor must be [x,y]': Refusal('anchor_shape_invalid', '每个锚点必须是 [x,y]。'),
    'cannot edit seeds during rebuild': Refusal('seeds_edit_during_rebuild', '重建期间不能修改种子。'),
    'invalid window or track': Refusal('window_or_track_invalid', 'window 或 track_id 无效。'),
    'unknown track': Refusal('track_unknown', '找不到该轨迹。'),
    'explicit A/B/ignore label, a guest name, or null is required': Refusal('seed_label_required', '必须明确给出 A/B/ignore 标签、访客姓名或 null。'),
    'label must be A, B, ignore, a guest name up to 60 characters, or null': Refusal('seed_label_text_invalid', 'label 只能是 A、B、ignore、60 字符以内的访客姓名或 null。'),
    'rebuild already running': Refusal('rebuild_running', '重建已在运行。'),
    'unknown context': Refusal('media_context_unknown', '找不到该上下文图片。'),
    'unknown evidence': Refusal('evidence_unknown', '找不到该证据图片。'),
    'invalid byte range': Refusal('byte_range_invalid', '字节范围无效。'),
    'cross-origin write rejected': Refusal('cross_origin_write_rejected', '已拒绝跨域写入。'),
    'invalid Content-Length': Refusal('content_length_invalid', 'Content-Length 无效。'),
    'invalid request size': Refusal('request_size_invalid', '请求体大小无效。'),
    'no live frame ready': Refusal('live_frame_not_ready', '还没有可用的直播帧。'),
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


# -- the sentences the service builds from its own facts ----------------------

# A sentence whose shape follows the values cannot be a key of REFUSALS: the same refusal reads
# differently for every caller.  Each row below holds the skeleton (the English sentence with its
# facts replaced by placeholder names), the code, the Chinese skeleton with the same placeholder
# names, and the fact names in the order the sentence states them.  Fill both languages from one
# set of facts, and never send a skeleton: a placeholder that reaches the operator is a broken
# line.

#: The rule ``integer(value, low, high, name)`` in annotator/operations.py applies.
INTEGER_RANGE = '{name} must be an integer from {low} to {high}'
#: The rule ``text(value, name, maximum)`` in annotator/operations.py applies.
TEXT_LENGTH = '{name} must contain 1–{maximum} characters'
#: The rule ``seconds(value, name)`` in annotator/operations.py applies.
WHOLE_SECONDS = '{name} must be a whole number of seconds, 0 or more'
#: The rule both raise sites of ``instant(value, name)`` in annotator/operations.py apply.
INSTANT = '{name} must be an ISO-8601 instant'
#: ``VodImporter._run`` in annotator/vod_import.py, when ffmpeg stops with a non-zero code.
FFMPEG_FAILED = 'ffmpeg stopped (exit {exit_code}): {detail}. The partial file was removed.'
#: ``VodImporter.scan`` in annotator/vod_import.py, for one channel whose listing failed.
SCAN_CHANNEL = '{channel}: {message}'

# The skeleton -> the row that fills it.  A skeleton is also the key a raise site passes.
TEMPLATES = {
    INTEGER_RANGE: FactRefusal(
        'operation_integer_range', INTEGER_RANGE,
        '{name} 必须是 {low} 到 {high} 之间的整数。', ('name', 'low', 'high')),
    TEXT_LENGTH: FactRefusal(
        'operation_text_length', TEXT_LENGTH,
        '{name} 必须包含 1–{maximum} 个字符。', ('name', 'maximum')),
    WHOLE_SECONDS: FactRefusal(
        'operation_whole_seconds', WHOLE_SECONDS,
        '{name} 必须是 0 或以上的整数秒。', ('name',)),
    INSTANT: FactRefusal(
        'operation_instant', INSTANT,
        '{name} 必须是 ISO-8601 时间点。', ('name',)),
    FFMPEG_FAILED: FactRefusal(
        'vod_ffmpeg_failed', FFMPEG_FAILED,
        'ffmpeg 已停止（退出码 {exit_code}）：{detail}。未完成的文件已删除。',
        ('exit_code', 'detail')),
    SCAN_CHANNEL: FactRefusal(
        'vod_scan_channel_failed', SCAN_CHANNEL,
        '{channel}：读取该频道的回放列表失败（{message}）。', ('channel', 'message')),
}


def filled_refusal(skeleton, **facts):
    """The sentence one skeleton builds, and the identity beside it.

    ``skeleton`` is one of the names above.  The answer is a ``(sentence, identity)`` pair, the
    same shape ``channel_refusal`` and ``disk_refusal`` answer with.  The identity names every
    fact, so the console reads the values as data and never parses them out of the sentence.
    """
    row = TEMPLATES[skeleton]
    return (row.en.format(**facts),
            {CODE_KEY: row.code, ZH_KEY: row.zh.format(**facts), **facts})


class TemplateError(ValueError):
    """A refusal built from facts: the sentence for the operator, and the identity beside it.

    A raise site writes ``raise TemplateError(INTEGER_RANGE, name=name, low=low, high=high)``.
    The skeleton travels as a name, so the sentence is built here and the raise site states the
    facts.  ``fields`` is the body the route adds beside ``error``
    (annotator/unified_server.py ``refusal_body``).
    """

    def __init__(self, skeleton, **facts):
        sentence, self.fields = filled_refusal(skeleton, **facts)
        super().__init__(sentence)
