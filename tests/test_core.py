import csv
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import article_vocab as a


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.basic, cls.advanced, cls.labels = a.load_lists()

    def setUp(self):
        self.units = a.blocks('He studied soil respiration and carbon sequestration.\n\nPolicies mitigate climate impacts.')

    def item(self,word,category,uid=1,surface=None):
        return dict(word=word, surface=surface or word, unit_id=uid, phonetic='',
                    meaning='示例释义', example=self.units[uid-1]['text'], translation='示例译文',
                    pos='n. phr.' if ' ' in word else 'v.', category=category,reason='测试筛选依据')

    def valid(self,items,technical=True):
        return a.validate(items,self.units,self.basic,self.advanced,self.labels,technical)

    def test_basic_words_blocked_even_when_called_technical(self):
        rows, rejected=self.valid([self.item('he','technical_word'),self.item('soil','technical_word')])
        self.assertEqual(rows,[])
        self.assertEqual(len(rejected),2)

    def test_professional_phrase_keeps_basic_components(self):
        rows,rejected=self.valid([self.item('soil respiration','technical_phrase'),self.item('carbon sequestration','technical_phrase')])
        self.assertEqual(len(rows),2)
        self.assertEqual(rejected,[])
        self.assertTrue(all('source' not in r for r in rows))

    def test_list_backed_word(self):
        rows,rejected=self.valid([self.item('mitigate','vocabulary',2)])
        self.assertEqual(len(rows),1)
        self.assertIn('TOEFL',rows[0]['evidence'])

    def test_fabricated_word_and_example_rejected(self):
        altered=self.item('mitigate','vocabulary',2)
        altered['example']='Policies mitigate all impacts.'
        rows,rejected=self.valid([altered,self.item('photosynthesis','vocabulary')])
        self.assertFalse(rows)
        self.assertEqual(len(rejected),2)

    def test_malicious_source_override_ignored(self):
        item=self.item('mitigate','vocabulary',2); item['source']='invented'
        rows,_=self.valid([item]); self.assertNotIn('source',rows[0])

    def test_invalid_fields_and_category(self):
        item=self.item('mitigate','vocabulary',2); item['translation']=None
        rows,rejected=self.valid([item,self.item('mitigate','easy',2)])
        self.assertEqual(len(rejected),2)

    def test_technical_can_be_disabled(self):
        rows,_=self.valid([self.item('soil respiration','technical_phrase')],False)
        self.assertFalse(rows)

    def test_word_boundaries(self):
        self.assertFalse(a.contains('the carbon pool','he'))
        self.assertTrue(a.contains('The carbon pool.','carbon pool'))

    def test_lemma_supported_and_arbitrary_rewrite_blocked(self):
        units=a.blocks('Policies mitigated severe impacts.')
        item=self.item('mitigate','vocabulary',2,'mitigated')
        item.update(unit_id=1,example=units[0]['text'])
        rows,_=a.validate([item],units,self.basic,self.advanced,self.labels)
        self.assertEqual(len(rows),1)
        item['word']='photosynthesis'
        rows,_=a.validate([item],units,self.basic,self.advanced,self.labels)
        self.assertFalse(rows)

    def test_chunks_no_loss(self):
        parts=list(a.chunks(self.units,20))
        self.assertEqual([u for p in parts for u in p],self.units)
        self.assertGreater(len(parts),1)

    def test_csv_commas_quotes_unicode(self):
        row={k:'' for k in a.FIELDS}
        row.update(word='mitigate',meaning='减缓，缓解',example='He said, "mitigate impacts".')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'out.csv'; a.export_csv(p,[row])
            self.assertTrue(p.read_bytes().startswith(b'\xef\xbb\xbf'))
            with p.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f); self.assertEqual(reader.fieldnames,a.FIELDS)
                self.assertEqual(next(reader),row)

    def test_formula_safety(self):
        self.assertEqual(a.csv_cell('=1+1'),"'=1+1")
        self.assertEqual(a.csv_cell('normal'),'normal')

    def test_docx_read(self):
        xml='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Carbon sequestration.</w:t></w:r></w:p></w:body></w:document>'
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'sample.docx'
            with zipfile.ZipFile(p,'w') as z:z.writestr('word/document.xml',xml)
            self.assertEqual(a.read_article(p),'Carbon sequestration.')

    def test_dedup(self):
        rows,_=self.valid([self.item('mitigate','vocabulary',2)]*2)
        self.assertEqual(len(a.merge_rows(rows)),1)

    def test_json_validation(self):
        self.assertEqual(a.parse_json('```json\n{"items":[]}\n```'),[])
        with self.assertRaises(ValueError): a.parse_json('{"items":{}}')

    def test_mock_api_contract(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                captured.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"items":[]}'}}]}).encode())
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            result=a.chat(f'http://127.0.0.1:{server.server_port}/v1','test-model','',self.units,self.advanced,'ecology')
            self.assertEqual(result,[])
            self.assertEqual(captured[0][0],'/v1/chat/completions')
            self.assertEqual(captured[0][1]['model'],'test-model')
            self.assertIn('source_units',captured[0][1]['messages'][1]['content'])
        finally:server.shutdown();server.server_close();thread.join()

    def test_remote_plain_http_blocked(self):
        with self.assertRaises(ValueError):a.chat('http://example.com','m','key',self.units,self.advanced,'ecology')


if __name__=='__main__':unittest.main()
