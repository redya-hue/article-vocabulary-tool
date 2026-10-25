import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import article_vocab as a


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.basic,cls.advanced,cls.labels=a.load_lists()

    def response(self,part):
        items=[]
        for u in part:
            for w in sorted(set(a.TOKEN.findall(u['text'].lower())) & self.advanced):
                items.append({'word':w,'surface':w,'unit_id':u['id'],'phonetic':'','meaning':'测试释义',
                    'example':u['text'],'translation':'测试译文','pos':'n.','category':'vocabulary','reason':'词表命中'})
        return items

    def run_job(self,units,ask,cache,cancel=None):
        events=[]
        stats=a.run_batches(units,ask,self.basic,self.advanced,self.labels,True,cache,
                            lambda k,v:events.append((k,v)),cancel or threading.Event())
        rows=a.merge_rows([row for k,v in events if k=='rows' for row in v[0]])
        return stats,rows,events

    def test_truncation_split_then_resume_without_api(self):
        units=a.blocks('Policies mitigate impacts.\n\nResilience improves recovery.')
        calls=[]
        def ask(part):
            calls.append(part)
            if len(part)>1:raise a.OutputIncomplete('length')
            return self.response(part)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'checkpoint.json'
            stats,rows,_=self.run_job(units,ask,a.Checkpoint(path))
            self.assertTrue(stats['complete']);self.assertEqual(len(calls),3)
            self.assertEqual({r['word'] for r in rows},{'mitigate','resilience'})
            def forbidden(part):raise AssertionError('No repeat calls permitted')
            again,restored,_=self.run_job(units,forbidden,a.Checkpoint(path))
            self.assertTrue(again['complete']);self.assertEqual(again['api_calls'],0)
            self.assertEqual(restored,rows)

    def test_network_error_preserves_success_and_resumes(self):
        units=[{'id':1,'text':'mitigate '+'ordinary '*100},{'id':2,'text':'resilience '+'ordinary '*100}]
        def ask(part):
            if part[0]['id']==2:raise RuntimeError('simulated timeout')
            return self.response(part)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'checkpoint.json'
            stats,rows,_=self.run_job(units,ask,a.Checkpoint(path))
            self.assertFalse(stats['complete']);self.assertIn('error',stats)
            self.assertIn('mitigate',{r['word'] for r in rows})
            seen=[]
            def second(part):seen.append(part[0]['id']);return self.response(part)
            stats,rows,_=self.run_job(units,second,a.Checkpoint(path))
            self.assertTrue(stats['complete']);self.assertEqual(seen,[2])
            self.assertEqual({r['word'] for r in rows},{'mitigate','resilience'})

    def test_bad_leaf_does_not_abort_following_text(self):
        units=a.blocks('Mitigate impacts.\n\nResilience improves recovery.')
        def ask(part):
            if len(part)>1 or part[0]['id']==1:raise a.OutputIncomplete('length')
            return self.response(part)
        with tempfile.TemporaryDirectory() as tmp:
            stats,rows,_=self.run_job(units,ask,a.Checkpoint(Path(tmp)/'c.json'))
            self.assertFalse(stats['complete']);self.assertEqual(len(stats['failed']),1)
            self.assertIn('resilience',{r['word'] for r in rows})

    def test_long_single_unit_can_split_without_text_loss(self):
        text=' '.join(['mitigate']*110)
        children=a.split_part([{'id':3,'text':text}])
        self.assertGreater(len(children),1)
        self.assertEqual(' '.join(c[0]['text'] for c in children),text)
        self.assertTrue(all(c[0]['fragment'] for c in children))

    def test_initial_long_units_cover_all_words(self):
        text=' '.join(['mitigate']*1500)
        units=a.blocks(text)
        self.assertGreater(len(units),1)
        self.assertEqual(' '.join(u['text'] for u in units),text)

    def test_shared_translations_and_local_examples(self):
        units=a.blocks('Soil respiration and carbon sequestration increase.')
        value={'items':[{'word':'soil respiration','surface':'Soil respiration','unit_id':1,'meaning':'土壤呼吸','pos':'n. phr.','category':'technical_phrase','reason':'术语'},
                        {'word':'carbon sequestration','surface':'carbon sequestration','unit_id':1,'meaning':'碳固存','pos':'n. phr.','category':'technical_phrase','reason':'术语'}],
               'translations':{'1':'土壤呼吸和碳固存增加。'}}
        items=a.parse_json(json.dumps(value),units)
        self.assertTrue(all(x['example']==units[0]['text'] for x in items))
        rows,rejected=a.validate(items,units,self.basic,self.advanced,self.labels)
        self.assertEqual(len(rows),2);self.assertEqual(rejected,[])
        self.assertTrue(all('source' not in r for r in rows))

    def test_missing_translation_not_treated_as_success(self):
        with self.assertRaises(a.OutputIncomplete):
            a.parse_json('{"items":[{"unit_id":1}],"translations":{}}',[{'id':1,'text':'mitigate'}])

    def test_no_twenty_word_cap(self):
        words=[w for w in sorted(self.advanced) if w.isalpha() and not a.forms(w)&self.basic][:45]
        units=a.blocks(' '.join(words))
        with tempfile.TemporaryDirectory() as tmp:
            stats,rows,_=self.run_job(units,self.response,a.Checkpoint(Path(tmp)/'c.json'))
        self.assertTrue(stats['complete']);self.assertEqual(len(rows),45)
        self.assertEqual(a.FIELDS,['word','phonetic','meaning','example','translation','pos'])

    def test_deepseek_request_and_length_response(self):
        requests=[]
        class FakeOpener:
            def open(self,req,timeout):
                requests.append(json.loads(req.data))
                return io.BytesIO(json.dumps({'choices':[{'finish_reason':'length','message':{'content':'{"items":['}}]}).encode())
        with patch.object(a.urllib.request,'build_opener',return_value=FakeOpener()):
            with self.assertRaises(a.OutputIncomplete):
                a.chat('https://api.deepseek.com','deepseek-flash','test-key',[{'id':1,'text':'mitigate'}],self.advanced,'ecology')
        self.assertEqual(requests[0]['thinking'],{'type':'disabled'})
        self.assertEqual(requests[0]['response_format'],{'type':'json_object'})
        self.assertEqual(requests[0]['max_tokens'],8000)

    def test_cancel_keeps_checkpoint(self):
        cancel=threading.Event();cancel.set()
        with tempfile.TemporaryDirectory() as tmp:
            stats,rows,_=self.run_job(a.blocks('Mitigate impacts.'),self.response,a.Checkpoint(Path(tmp)/'c.json'),cancel)
        self.assertFalse(stats['complete']);self.assertEqual(stats['api_calls'],0)

    def test_checkpoint_reset_ignores_corrupt_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'c.json';p.write_text('not json')
            cache=a.Checkpoint(p,reset=True);cache.save()
            self.assertEqual(a.Checkpoint(p).nodes,{})


if __name__=='__main__':unittest.main()
