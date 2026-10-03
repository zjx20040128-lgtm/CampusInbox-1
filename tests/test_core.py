import tempfile
import unittest
from pathlib import Path
from courseinbox.core import Inbox, Conflict, ValidationError, parse_message

AT = '2026-10-03T16:00:00+08:00'
TEXT = '《软件工程》 第三次作业：请提交实验报告、源代码。截止：2026年10月12日 23:59。'

class ParsingTests(unittest.TestCase):
    def test_relative_dates_use_message_time_not_today(self):
        p = parse_message('《高等数学》 第三次作业，请明天18:30前提交。', '2026-01-31T22:00:00+08:00')[0]
        self.assertEqual(p['deadline'], '2026-02-01T18:30:00+08:00')
    def test_date_without_time_is_not_invented(self):
        p = parse_message('《高等数学》 第三次作业，10月12日前提交。', AT)[0]
        self.assertEqual(p['deadline'], '2026-10-12')
        self.assertEqual(p['date_precision'], 'date')
    def test_extension_uses_new_deadline_not_old(self):
        p = parse_message('《软件工程》 第三次作业原截止10月12日23:59，现延期到10月15日18:00。', AT)[0]
        self.assertEqual(p['deadline'], '2026-10-15T18:00:00+08:00')
        self.assertEqual(p['operation'], 'update')
    def test_missing_deadline_and_impossible_date_are_flagged(self):
        for text in ['《数据结构》 实验报告请及时提交', '《数据结构》 实验报告截止2月30日18:00']:
            p = parse_message(text, AT)[0]
            self.assertIsNone(p['deadline'])
            self.assertTrue(p['warnings'])
    def test_plain_notice_not_turned_into_task(self):
        self.assertEqual(parse_message('同学们节日快乐，请注意安全。', AT), [])
    def test_checklist_preserves_deliverables(self):
        p = parse_message(TEXT, AT)[0]
        self.assertIn('实验报告', p['requirements'])
        self.assertIn('源代码', p['requirements'])

class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'inbox.sqlite3'
        self.inbox = Inbox(self.path)
    def tearDown(self):
        self.temp.cleanup()
    def ingest(self, text=TEXT, scope='计科1班', at=AT, source='学习通', event_key=None):
        return self.inbox.ingest(text, source=source, captured_at=at, scope=scope, event_key=event_key)
    def create(self, **kwargs):
        r = self.ingest(**kwargs)
        return self.inbox.confirm(r['proposals'][0]['id'])
    def test_import_waits_for_confirmation(self):
        r = self.ingest()
        self.assertEqual(len(r['proposals']), 1)
        self.assertEqual(self.inbox.tasks(), [])
        self.assertEqual(r['mode'], 'rules')
    def test_exact_replay_is_idempotent_and_confirmation_is_idempotent(self):
        first, replay = self.ingest(), self.ingest()
        self.assertEqual(first['message']['id'], replay['message']['id'])
        self.assertTrue(replay['duplicate'])
        a = self.inbox.confirm(first['proposals'][0]['id'])
        b = self.inbox.confirm(first['proposals'][0]['id'])
        self.assertEqual(a['id'], b['id'])
        self.assertEqual(len(self.inbox.tasks()), 1)
    def test_duplicate_cross_source_links_evidence_not_second_task(self):
        t = self.create()
        r = self.ingest(source='班级群')
        self.assertEqual(r['proposals'][0]['action'], 'link')
        result = self.inbox.confirm(r['proposals'][0]['id'])
        self.assertEqual(result['id'], t['id'])
        self.assertEqual(len(self.inbox.task_detail(t['id'])['sources']), 2)
    def test_same_title_different_class_not_merged(self):
        self.create()
        r = self.ingest(scope='计科2班')
        self.assertEqual(r['proposals'][0]['action'], 'create')
        self.inbox.confirm(r['proposals'][0]['id'])
        self.assertEqual(len(self.inbox.tasks()), 2)
    def test_extension_stays_pending_then_records_history(self):
        t = self.create()
        r = self.ingest('《软件工程》 第三次作业延期到10月15日18:00。', at='2026-10-04T09:00:00+08:00')
        self.assertEqual(r['proposals'][0]['action'], 'update')
        self.assertEqual(self.inbox.task_detail(t['id'])['deadline'], '2026-10-12T23:59:00+08:00')
        changed = self.inbox.confirm(r['proposals'][0]['id'])
        self.assertEqual(changed['deadline'], '2026-10-15T18:00:00+08:00')
        detail = self.inbox.task_detail(t['id'])
        self.assertEqual(len(detail['history']), 2)
        self.assertEqual(detail['history'][0]['before']['deadline'], '2026-10-12T23:59:00+08:00')
    def test_stale_proposals_do_not_overwrite_newer_confirmation(self):
        t = self.create()
        a = self.ingest('《软件工程》 第三次作业延期到10月15日18:00。', at='2026-10-04T09:00:00+08:00')['proposals'][0]
        b = self.ingest('《软件工程》 第三次作业延期到10月16日18:00。', at='2026-10-05T09:00:00+08:00')['proposals'][0]
        self.inbox.confirm(b['id'])
        with self.assertRaises(Conflict):
            self.inbox.confirm(a['id'])
        self.assertEqual(self.inbox.task_detail(t['id'])['deadline'], '2026-10-16T18:00:00+08:00')
    def test_cancel_requires_confirmation_and_scope_match(self):
        t = self.create()
        p = self.ingest('《软件工程》 第三次作业取消，不用提交。', at='2026-10-04T09:00:00+08:00')['proposals'][0]
        self.assertEqual(p['action'], 'cancel')
        self.assertEqual(self.inbox.task_detail(t['id'])['status'], 'pending')
        self.assertEqual(self.inbox.confirm(p['id'])['status'], 'cancelled')
    def test_done_is_not_submitted_and_remains_due(self):
        t = self.create()
        self.inbox.patch_task(t['id'], {'status':'done'})
        d = self.inbox.dashboard('2026-10-12T18:00:00+08:00')
        self.assertEqual(d['submitted'], 0)
        self.assertEqual(len(d['reminders']), 1)
        self.inbox.patch_task(t['id'], {'status':'submitted'})
        self.assertEqual(self.inbox.dashboard('2026-10-12T18:00:00+08:00')['reminders'], [])
    def test_data_persists_after_reopen(self):
        t = self.create()
        self.assertEqual(Inbox(self.path).task_detail(t['id'])['title'], '第三次作业')
    def test_ics_escapes_and_dates_are_timezone_correct(self):
        self.create()
        self.create(text='《高等数学》 第一次作业，10月13日前提交。')
        output = self.inbox.calendar()
        self.assertIn('DTSTART:20261012T155900Z', output)
        self.assertIn('DTSTART;VALUE=DATE:20261013', output)
        self.assertIn('BEGIN:VCALENDAR', output)
        self.assertEqual(output.count('BEGIN:VEVENT'), 2)
    def test_reject_invalid_status_and_deadline_edits(self):
        p = self.ingest()['proposals'][0]
        with self.assertRaises(ValidationError):
            self.inbox.confirm(p['id'], {'deadline':'随便一个时间'})
        t = self.inbox.confirm(p['id'])
        with self.assertRaises(ValidationError):
            self.inbox.patch_task(t['id'], {'status':'platform_confirmed'})

if __name__ == '__main__':
    unittest.main()
