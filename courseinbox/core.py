"""CourseInbox domain: provenance, draft review and versioned tasks. Stdlib only."""
from __future__ import annotations
import contextlib
import hashlib
import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

CN = timezone(timedelta(hours=8))
STATUSES = {'pending', 'in_progress', 'done', 'submitted', 'cancelled'}
KINDS = {'assignment', 'exam', 'experiment', 'project', 'other'}

class ValidationError(ValueError):
    pass
class Conflict(ValidationError):
    pass
class NotFound(ValidationError):
    pass

def now_iso():
    return datetime.now(CN).replace(microsecond=0).isoformat()

def parse_timestamp(value):
    if not isinstance(value, str):
        raise ValidationError('消息时间必须是带时区的 ISO 时间。')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValidationError('消息时间无效，请使用带时区的 ISO 时间。') from None
    if result.tzinfo is None:
        raise ValidationError('消息时间缺少时区。')
    return result.astimezone(CN)

def clean_string(value, name, maximum=160, required=False):
    if not isinstance(value, str):
        raise ValidationError(f'{name}必须为文本。')
    value = value.strip()
    if len(value) > maximum:
        raise ValidationError(f'{name}最多 {maximum} 个字符。')
    if required and not value:
        raise ValidationError(f'请填写{name}。')
    return value

def normalize(value):
    return re.sub(r'[\W_]+', '', value, flags=re.UNICODE).lower()

def validate_deadline(value):
    if value is None or value == '':
        return None, 'unknown'
    if not isinstance(value, str):
        raise ValidationError('截止日期必须为文本。')
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value).isoformat(), 'date'
        result = parse_timestamp(value)
        return result.replace(microsecond=0).isoformat(), 'minute'
    except (ValueError, ValidationError):
        raise ValidationError('截止日期无效，使用 YYYY-MM-DD 或带时区时间。') from None

def deadline_instant(value):
    if not value:
        return None
    if len(value) == 10:
        # Only the calendar day is known: overdue starts next day, never guess 23:59.
        return datetime.combine(date.fromisoformat(value) + timedelta(days=1), datetime.min.time(), CN)
    return parse_timestamp(value)

def extract_deadline(text, anchor):
    warnings = []
    change = re.search(r'(?:延期(?:到|至)|延至|推迟(?:到|至)|改为|调整(?:为|到))\s*[:：]?', text)
    segment = text[change.end():] if change else text
    if not change:
        cue = re.search(r'(?:截止(?:时间|日期)?(?:为|到|至)?|截至|最晚|提交时间)\s*[:：]?', text)
        if cue:
            segment = text[cue.end():]
    explicit = re.search(r'(?:(\d{4})\s*[年/-]\s*)?(\d{1,2})\s*[月/-]\s*(\d{1,2})(?:\s*日|\b)', segment)
    chosen = None
    evidence = ''
    end = 0
    if explicit:
        year = int(explicit.group(1) or anchor.year)
        try:
            chosen = date(year, int(explicit.group(2)), int(explicit.group(3)))
        except ValueError:
            return None, 'unknown', explicit.group(0), ['原文日期不存在，请手动核对。']
        end = explicit.end()
        evidence = explicit.group(0)
        if not explicit.group(1):
            warnings.append('原文未写年份，暂按消息发布年份，请核对。')
    else:
        rel = re.search(r'今天|今日|明天|明日|后天|后日|(?:(?:本|下)周|星期|周)[一二三四五六日天]', segment)
        if rel:
            token = rel.group(0)
            if token in ('今天', '今日', '明天', '明日', '后天', '后日'):
                offset = {'今天': 0, '今日': 0, '明天': 1, '明日': 1, '后天': 2, '后日': 2}[token]
                chosen = anchor.date() + timedelta(days=offset)
            else:
                weekday = '一二三四五六日'.index(token[-1].replace('天', '日'))
                monday = anchor.date() - timedelta(days=anchor.weekday())
                if token.startswith('下周'):
                    chosen = monday + timedelta(days=7 + weekday)
                elif token.startswith('本周'):
                    chosen = monday + timedelta(days=weekday)
                else:
                    chosen = anchor.date() + timedelta(days=(weekday - anchor.weekday()) % 7)
                    warnings.append('原文未说明哪一周，请核对日期。')
            end, evidence = rel.end(), token
    if chosen is None:
        return None, 'unknown', '', ['未识别到明确截止日期，请核对或留空。']
    # A time must follow the selected date within the same short clause.
    tail = re.split(r'[。；;\n]', segment[end:], maxsplit=1)[0][:36]
    tm = re.search(r'(?:(上午|下午|晚上|中午)\s*)?(\d{1,2})\s*[:：点时]\s*(\d{1,2})?(?:分)?', tail)
    if tm:
        h, m = int(tm.group(2)), int(tm.group(3) or 0)
        period = tm.group(1)
        if period in ('下午', '晚上') and h < 12:
            h += 12
        if period == '上午' and h == 12:
            h = 0
        try:
            dt = datetime(chosen.year, chosen.month, chosen.day, h, m, tzinfo=CN)
        except ValueError:
            return None, 'unknown', evidence + tm.group(0), ['原文时间不存在，请手动核对。']
        value, precision = dt.isoformat(), 'minute'
        evidence += tail[:tm.end()]
    else:
        value, precision = chosen.isoformat(), 'date'
        warnings.append('原文未写具体时刻，保留为日期。')
    if chosen < anchor.date():
        warnings.append('截止日期早于消息发布时间，请核对年份和历史消息。')
    return value, precision, evidence, warnings

TASK_PATTERN = r'第[零〇一二三四五六七八九十百\d]+次(?:作业|实验|测验|考试)|(?:实验|作业|报告)\s*[零〇一二三四五六七八九十\d]+|(?:期中|期末)考试'

def parse_message(text, captured_at, course='', scope=''):
    text = clean_string(text, '消息', 30000, True)
    anchor = parse_timestamp(captured_at)
    if not re.search(r'作业|实验|报告|考试|测验|论文|课程设计|提交|截止|签到|答辩', text):
        return []
    course_match = re.search(r'《([^》]{1,80})》|【([^】]{1,80})】|课程\s*[:：]\s*([^\n，,。；;]{1,80})', text)
    course = course.strip() or (next((x for x in course_match.groups() if x), '') if course_match else '')
    # Separate paragraphs are separate candidates only when each contains a task marker.
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    blocks = paragraphs if len(paragraphs) > 1 and all(re.search(TASK_PATTERN, p) for p in paragraphs) else [text]
    result = []
    for block in blocks[:20]:
        own_course = re.search(r'《([^》]+)》', block)
        block_course = course if course_match is None or len(blocks) == 1 else (own_course.group(1) if own_course else course)
        title_match = re.search(TASK_PATTERN, block)
        label = re.search(r'(?:任务|标题)\s*[:：]\s*([^\n，,。；;]{1,100})', block)
        generic = re.search(r'实验报告|课程设计|毕业论文|论文|实验|考试|作业|签到|答辩|报告', block)
        title = title_match.group(0) if title_match else (label.group(1) if label else (generic.group(0) if generic else '课程任务'))
        operation = 'cancel' if re.search(r'(?:取消|作废|无需提交|不用提交)', block) else ('update' if re.search(r'延期|延至|推迟|改为|调整', block) else 'create')
        deadline, precision, deadline_evidence, warnings = extract_deadline(block, anchor)
        if not block_course:
            warnings.append('未识别课程，请填写后再确认。')
        if not title_match and not label:
            warnings.append('任务名称较笼统，不自动与其他任务合并。')
        requirements = []
        submission = re.search(r'(?:提交|上传|上交)\s*[:：]?\s*([^。；;\n]{1,160})', block)
        if submission:
            body = re.split(r'(?:截止|截至|最晚|于\s*\d|在\s*\d)', submission.group(1))[0]
            for part in re.split(r'[、，,和及+＋]', body):
                part = part.strip(' ：:。 ')
                if part and not re.search(r'\d.*(?:月|日|:)|明天|后天|周[一二三四五六日]|前提交|不用', part):
                    requirements.append(part[:120])
        kind = 'exam' if re.search(r'考试|测验', title) else ('experiment' if '实验' in title else ('project' if re.search(r'设计|论文', title) else 'assignment'))
        result.append(dict(title=title, course=block_course, scope=scope, deadline=deadline, date_precision=precision, kind=kind,
                           requirements=requirements, operation=operation, matchable=bool(title_match or label), evidence=block[:1200],
                           deadline_evidence=deadline_evidence, warnings=warnings, captured_at=anchor.isoformat()))
    return result

def validate_candidate(candidate, message, edits=None):
    if not isinstance(candidate, dict):
        raise ValidationError('草稿格式无效。')
    c = dict(candidate)
    if edits:
        if not isinstance(edits, dict):
            raise ValidationError('编辑字段必须为对象。')
        allowed = {'title','course','scope','deadline','kind','requirements'}
        if set(edits) - allowed:
            raise ValidationError('存在不支持的编辑字段。')
        c.update(edits)
    c['title'] = clean_string(c.get('title', ''), '任务名称', 160, True)
    c['course'] = clean_string(c.get('course', ''), '课程', 100)
    c['scope'] = clean_string(c.get('scope', message['scope']), '班级', 100)
    c['deadline'], c['date_precision'] = validate_deadline(c.get('deadline'))
    if c.get('kind', 'other') not in KINDS:
        raise ValidationError('任务类型无效。')
    c['kind'] = c.get('kind', 'other')
    c['operation'] = c.get('operation', 'create')
    if c['operation'] not in {'create','update','cancel'}:
        raise ValidationError('任务操作无效。')
    requirements = c.get('requirements', [])
    if not isinstance(requirements, list) or len(requirements) > 30:
        raise ValidationError('提交材料必须是最多 30 条的列表。')
    c['requirements'] = list(dict.fromkeys(clean_string(x, '材料名称', 180, True) for x in requirements))
    c['evidence'] = clean_string(c.get('evidence', message['text'][:1200]), '原文依据', 30000)
    if c['evidence'] and c['evidence'] not in message['text']:
        raise ValidationError('草稿依据必须能在消息原文中找到。')
    c['warnings'] = [str(x)[:250] for x in c.get('warnings', [])[:20]]
    c['captured_at'] = message['captured_at']
    c['matchable'] = bool(c.get('matchable', False))
    c['deadline_evidence'] = str(c.get('deadline_evidence', ''))[:300]
    return c

def task_key(candidate):
    if not candidate.get('course') or not candidate.get('matchable'):
        return None
    return '|'.join(normalize(candidate[x]) for x in ('course','scope','title'))

def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

class Inbox:
    def __init__(self, db_path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, task_key TEXT UNIQUE NOT NULL, data TEXT NOT NULL, version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, message_id TEXT NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', task_id TEXT);
            CREATE TABLE IF NOT EXISTS sources(task_id TEXT NOT NULL, message_id TEXT NOT NULL, UNIQUE(task_id,message_id));
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, data TEXT NOT NULL);
            ''')
    @contextlib.contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
    def _task(self, db, task_id):
        row = db.execute('SELECT data FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not row:
            raise NotFound('任务不存在。')
        return json.loads(row['data'])
    def _match(self, db, candidate):
        key = task_key(candidate)
        row = db.execute('SELECT data FROM tasks WHERE task_key=?', (key,)).fetchone() if key else None
        return json.loads(row['data']) if row else None
    def _proposal(self, db, candidate, message):
        c = validate_candidate(candidate, message)
        target = self._match(db, c)
        warnings = list(c['warnings'])
        if target:
            if c['operation'] == 'cancel':
                action = 'cancel'
            elif c['deadline'] and c['deadline'] != target['deadline']:
                action = 'update'
                if c['operation'] != 'update':
                    warnings.append('相同任务出现不同截止日期，请确认是否变更。')
            elif c['requirements'] and set(c['requirements']) != {x['text'] for x in target['checklist']}:
                action = 'update'
            else:
                action = 'link'
            if parse_timestamp(message['captured_at']) < parse_timestamp(target['last_source_at']) and action != 'link':
                warnings.append('消息比当前任务来源更早，确认时将阻止覆盖，请查看最新通知。')
        else:
            action = 'create'
            if c['operation'] in ('cancel', 'update'):
                warnings.append('未找到同课程、同班级的原任务，请核对任务名称。')
        c['warnings'] = warnings
        p = dict(id=uuid.uuid4().hex, message_id=message['id'], candidate=c, action=action,
                 target_id=target['id'] if target else None, expected_version=target['version'] if target else None,
                 before=target, status='pending', created_at=now_iso())
        db.execute('INSERT INTO proposals(id,message_id,data) VALUES(?,?,?)', (p['id'], message['id'], dump(p)))
        return p
    def ingest(self, text, source='手动导入', captured_at=None, course='', scope='', event_key=None, sample=False, candidates=None, mode='rules', trace=None):
        text = clean_string(text, '消息', 30000, True)
        source = clean_string(source, '来源', 120, True)
        course, scope = clean_string(course, '课程', 100), clean_string(scope, '班级', 100)
        at = parse_timestamp(captured_at or now_iso()).replace(microsecond=0).isoformat()
        if event_key is not None:
            event_key = clean_string(event_key, '通知标识', 1000, True)
        fingerprint = hashlib.sha256(dump([text,source,course,scope,event_key,at[:10]]).encode()).hexdigest()
        with self.lock, self.connection() as db:
            old = db.execute('SELECT data FROM messages WHERE fingerprint=?', (fingerprint,)).fetchone()
            if old:
                m = json.loads(old['data'])
                ps = [self._unpack_proposal(row) for row in db.execute('SELECT * FROM proposals WHERE message_id=?', (m['id'],))]
                return dict(message=m, proposals=ps, duplicate=True, mode=m['mode'], trace=m.get('trace', []))
            m = dict(id=uuid.uuid4().hex, text=text, source=source, course=course, scope=scope, captured_at=at,
                     received_at=now_iso(), sample=bool(sample), mode=mode, trace=trace or [])
            parsed = parse_message(text, at, course, scope) if candidates is None else candidates
            if not isinstance(parsed, list) or len(parsed) > 20:
                raise ValidationError('每条消息最多包含 20 个任务草稿。')
            db.execute('INSERT INTO messages VALUES(?,?,?)', (m['id'], fingerprint, dump(m)))
            proposals = [self._proposal(db, c, m) for c in parsed]
            return dict(message=m, proposals=proposals, duplicate=False, mode=mode, trace=m['trace'])
    @staticmethod
    def _unpack_proposal(row):
        p = json.loads(row['data'])
        p['status'], p['task_id'] = row['status'], row['task_id']
        return p
    def proposals(self, status='pending'):
        with self.connection() as db:
            sql, args = ('SELECT * FROM proposals WHERE status=? ORDER BY rowid DESC', (status,)) if status else ('SELECT * FROM proposals ORDER BY rowid DESC', ())
            return [self._unpack_proposal(r) for r in db.execute(sql, args)]
    def messages(self):
        with self.connection() as db:
            return [json.loads(r['data']) for r in db.execute('SELECT data FROM messages ORDER BY rowid DESC LIMIT 500')]
    def tasks(self, course='', scope=None):
        with self.connection() as db:
            items = [json.loads(r['data']) for r in db.execute('SELECT data FROM tasks ORDER BY rowid DESC')]
        return sorted([x for x in items if (not course or normalize(x['course']) == normalize(course)) and (scope is None or normalize(x['scope']) == normalize(scope))], key=lambda x:(x['status'] in ('submitted','cancelled'), x['deadline'] or '9999', x['title']))
    def _save_task(self, db, task, key=None):
        if key is None:
            db.execute('UPDATE tasks SET data=?, version=? WHERE id=?', (dump(task),task['version'],task['id']))
        else:
            db.execute('INSERT INTO tasks VALUES(?,?,?,?)', (task['id'],key,dump(task),task['version']))
    def _history(self, db, task, before, action, message_id=None):
        db.execute('INSERT INTO history(task_id,data) VALUES(?,?)', (task['id'],dump(dict(at=now_iso(),action=action,before=before,after=task,message_id=message_id))))
    def confirm(self, proposal_id, edits=None):
        with self.lock, self.connection() as db:
            row = db.execute('SELECT * FROM proposals WHERE id=?', (proposal_id,)).fetchone()
            if not row:
                raise NotFound('草稿不存在。')
            p = self._unpack_proposal(row)
            if p['status'] == 'confirmed':
                return self._task(db, p['task_id'])
            if p['status'] != 'pending':
                raise Conflict('草稿已忽略。')
            message = json.loads(db.execute('SELECT data FROM messages WHERE id=?', (p['message_id'],)).fetchone()['data'])
            c = validate_candidate(p['candidate'], message, edits)
            target = self._match(db, c)
            if p['target_id']:
                if not target or target['id'] != p['target_id']:
                    raise Conflict('更改课程、班级或名称会改变匹配结果，请忽略后重新导入。')
                if target['version'] != p['expected_version']:
                    raise Conflict('任务已被更新，本草稿版本已过期。请忽略并重新导入最新通知。')
            elif target:
                raise Conflict('另一草稿已经创建了该任务。请忽略并重新导入以关联来源。')
            if target and p['action'] != 'link' and parse_timestamp(message['captured_at']) < parse_timestamp(target['last_source_at']):
                raise Conflict('历史消息不能覆盖较新的已确认通知。')
            before = dict(target) if target else None
            if target:
                task = dict(target)
                if c['operation'] == 'cancel':
                    task['status'] = 'cancelled'
                else:
                    if c['deadline']:
                        task['deadline'], task['date_precision'] = c['deadline'],c['date_precision']
                    if c['requirements']:
                        done = {x['text']:x['done'] for x in task['checklist']}
                        task['checklist'] = [dict(text=x,done=done.get(x,False)) for x in c['requirements']]
                task['version'] += 1
                task['updated_at'] = now_iso()
                task['last_source_at'] = max(task['last_source_at'],message['captured_at'])
                self._save_task(db, task)
            else:
                task = dict(id=uuid.uuid4().hex,title=c['title'],course=c['course'],scope=c['scope'],kind=c['kind'],
                            deadline=c['deadline'],date_precision=c['date_precision'],checklist=[dict(text=x,done=False) for x in c['requirements']],
                            status='cancelled' if c['operation']=='cancel' else 'pending',version=1,created_at=now_iso(),updated_at=now_iso(),
                            last_source_at=message['captured_at'],sample=message['sample'])
                self._save_task(db, task, task_key(c) or ('unmatched:' + task['id']))
            db.execute('INSERT OR IGNORE INTO sources VALUES(?,?)', (task['id'],message['id']))
            self._history(db, task, before, p['action'], message['id'])
            p['candidate'] = c
            db.execute("UPDATE proposals SET status='confirmed',task_id=?,data=? WHERE id=?", (task['id'],dump(p),p['id']))
            return task
    def dismiss(self, proposal_id):
        with self.lock, self.connection() as db:
            row = db.execute('SELECT status FROM proposals WHERE id=?', (proposal_id,)).fetchone()
            if not row:
                raise NotFound('草稿不存在。')
            if row['status'] == 'confirmed':
                raise Conflict('已确认草稿不能忽略。')
            db.execute("UPDATE proposals SET status='dismissed' WHERE id=?", (proposal_id,))
            return dict(id=proposal_id,status='dismissed')
    def patch_task(self, task_id, changes):
        if not isinstance(changes, dict) or set(changes) - {'status','checklist','expected_version'}:
            raise ValidationError('任务只支持更新状态和材料勾选。')
        with self.lock, self.connection() as db:
            before = self._task(db, task_id)
            if changes.get('expected_version') is not None and changes['expected_version'] != before['version']:
                raise Conflict('任务已更新，请刷新后重试。')
            task = dict(before)
            if 'status' in changes:
                if changes['status'] not in STATUSES:
                    raise ValidationError('任务状态无效。')
                task['status'] = changes['status']
            if 'checklist' in changes:
                values = changes['checklist']
                if not isinstance(values, list) or len(values) != len(task['checklist']) or any(type(v) is not bool for v in values):
                    raise ValidationError('材料勾选应为与当前材料等长的布尔列表。')
                task['checklist'] = [dict(text=x['text'],done=v) for x,v in zip(task['checklist'],values)]
            task['updated_at'], task['version'] = now_iso(),task['version'] + 1
            self._save_task(db, task)
            self._history(db, task, before, 'status/checklist')
            return task
    def task_detail(self, task_id):
        with self.connection() as db:
            task = self._task(db, task_id)
            task['sources'] = [json.loads(r['data']) for r in db.execute('SELECT m.data FROM messages m JOIN sources s ON m.id=s.message_id WHERE s.task_id=? ORDER BY m.rowid DESC', (task_id,))]
            task['history'] = [json.loads(r['data']) for r in db.execute('SELECT data FROM history WHERE task_id=? ORDER BY id DESC', (task_id,))]
            return task
    def dashboard(self, at=None):
        moment = parse_timestamp(at or now_iso())
        tasks = self.tasks()
        active = [t for t in tasks if t['status'] not in ('submitted','cancelled')]
        reminders = []
        for task in active:
            due = deadline_instant(task['deadline'])
            if not due:
                continue
            seconds = (due-moment).total_seconds()
            if seconds <= 86400:
                reminders.append(dict(task_id=task['id'],title=task['title'],course=task['course'],deadline=task['deadline'],status=task['status'],overdue=seconds <= 0,
                                      level='overdue' if seconds <= 0 else ('soon' if seconds <= 7200 else 'today')))
        upcoming = [t for t in active if t['deadline'] and 0 < (deadline_instant(t['deadline'])-moment).total_seconds() <= 7*86400]
        return dict(total=len(tasks),active=len(active),submitted=sum(t['status']=='submitted' for t in tasks),done=sum(t['status']=='done' for t in tasks),
                    overdue=sum(r['overdue'] for r in reminders),upcoming=len(upcoming),pending_reviews=len(self.proposals()),reminders=reminders,
                    courses=sorted({t['course'] for t in tasks if t['course']}),as_of=moment.isoformat())
    def calendar(self):
        def escape(x):
            return str(x).replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,').replace('\r','')
        lines = ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//CourseInbox//CN','CALSCALE:GREGORIAN','METHOD:PUBLISH','X-WR-CALNAME:CourseInbox 课务日历']
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        for t in self.tasks():
            if not t['deadline'] or t['status'] == 'cancelled':
                continue
            lines += ['BEGIN:VEVENT', f"UID:{t['id']}@courseinbox.local",f'DTSTAMP:{stamp}',f"SEQUENCE:{t['version']}",f"SUMMARY:{escape(t['course']+' · '+t['title'])}",
                      'DESCRIPTION:' + escape('班级：' + t['scope'] + '\n状态：' + t['status'] + '\n提交材料：' + '、'.join(x['text'] for x in t['checklist']))]
            if t['date_precision'] == 'date':
                day = date.fromisoformat(t['deadline'])
                lines += [f'DTSTART;VALUE=DATE:{day.strftime("%Y%m%d")}',f'DTEND;VALUE=DATE:{(day+timedelta(days=1)).strftime("%Y%m%d")}']
            else:
                due = parse_timestamp(t['deadline']).astimezone(timezone.utc)
                lines += [f'DTSTART:{due.strftime("%Y%m%dT%H%M%SZ")}',f'DTEND:{(due+timedelta(minutes=15)).strftime("%Y%m%dT%H%M%SZ")}',
                          'BEGIN:VALARM','ACTION:DISPLAY','TRIGGER:-PT2H','DESCRIPTION:课程任务即将截止','END:VALARM']
            lines += ['END:VEVENT']
        lines += ['END:VCALENDAR']
        # RFC 5545 folding is measured in UTF-8 octets and must not split a code point.
        folded = []
        for line in lines:
            chunk = ''
            for char in line:
                if len((chunk+char).encode('utf-8')) > 75:
                    folded.append(chunk)
                    chunk = ' '
                chunk += char
            folded.append(chunk)
        return '\r\n'.join(folded) + '\r\n'
