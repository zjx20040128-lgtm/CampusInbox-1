import unittest
from courseinbox.files import normalize_ocr
from courseinbox.core import parse_message

class OcrTests(unittest.TestCase):
    def test_chinese_ocr_word_spaces_do_not_break_task_or_date(self):
        raw='《 软 件 工 程 》 第 三 次 作 业\n请 提 交 实 验 报 告 、 源 代 码 。\n截 止 ： 2026 年 1 0 月 1 2 日 23 ： 59 。'
        text=normalize_ocr(raw)
        p=parse_message(text,'2026-10-03T16:00:00+08:00')[0]
        self.assertEqual(p['title'],'第三次作业')
        self.assertEqual(p['course'],'软件工程')
        self.assertEqual(p['deadline'],'2026-10-12T23:59:00+08:00')
        self.assertIn('源代码',p['requirements'])
    def test_latin_word_separators_preserved(self):
        self.assertIn('SQL scripts',normalize_ocr('请 提 交 SQL scripts 文 件'))

if __name__=='__main__': unittest.main()
