import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from env_contract import ConfigError, load_contract, parse_env, read_bounded, validate, main


def contract(rule=None):
    return load_contract(json.dumps({'version':1,'variables':{'TOKEN':rule or {}}}))


class ParserTests(unittest.TestCase):
    def test_plain(self): self.assertEqual(parse_env('A=one'), {'A':'one'})
    def test_empty(self): self.assertEqual(parse_env('A='), {'A':''})
    def test_blank_lines(self): self.assertEqual(parse_env('\n# comment\n'), {})
    def test_export(self): self.assertEqual(parse_env('export A=one'), {'A':'one'})
    def test_export_tab(self): self.assertEqual(parse_env('export\tA=one'), {'A':'one'})
    def test_spaces(self): self.assertEqual(parse_env(' A = one  '), {'A':'one'})
    def test_single_quotes(self): self.assertEqual(parse_env("A=' one '"), {'A':' one '})
    def test_double_quotes(self): self.assertEqual(parse_env('A="one#two"'), {'A':'one#two'})
    def test_inline_comment(self): self.assertEqual(parse_env('A=one#two'), {'A':'one'})
    def test_comment_after_quote(self): self.assertEqual(parse_env('A="one" # two'), {'A':'one'})
    def test_equals_in_value(self): self.assertEqual(parse_env('A=a=b'), {'A':'a=b'})
    def test_crlf(self): self.assertEqual(parse_env('A=one\r\nB=two\r\n'), {'A':'one','B':'two'})
    def test_unicode_value(self): self.assertEqual(parse_env('A=नमस्ते'), {'A':'नमस्ते'})
    def test_case_sensitive(self): self.assertEqual(len(parse_env('A=1\na=2')), 2)
    def test_duplicate(self):
        with self.assertRaises(ConfigError) as e: parse_env('A=1\nA=2')
        self.assertEqual(e.exception.line, 2)
    def test_missing_equals(self):
        with self.assertRaises(ConfigError): parse_env('A')
    def test_bad_name(self):
        for name in ('1A','A-B','A B','नमस्ते'):
            with self.subTest(name=name), self.assertRaises(ConfigError): parse_env(name+'=one')
    def test_unclosed(self):
        with self.assertRaises(ConfigError): parse_env('A="one')
    def test_multiline_rejected(self):
        with self.assertRaises(ConfigError): parse_env('A="one\ntwo"')
    def test_trailing_text(self):
        with self.assertRaises(ConfigError): parse_env('A="one" two')
    def test_escaped_quotes_rejected(self):
        with self.assertRaises(ConfigError): parse_env(r'A="one\"two"')
    def test_backslash_in_quoted_rejected(self):
        with self.assertRaises(ConfigError): parse_env(r'A="one\ntwo"')
    def test_unquoted_quote_rejected(self):
        with self.assertRaises(ConfigError): parse_env("A=don't")
    def test_nul_rejected(self):
        with self.assertRaises(ConfigError): parse_env('A=a\x00b')
    def test_expansion_not_performed(self): self.assertEqual(parse_env('A=${TOKEN}'), {'A':'${TOKEN}'})
    def test_command_not_executed(self): self.assertEqual(parse_env('A=$(echo hello)'), {'A':'$(echo hello)'})


class SchemaTests(unittest.TestCase):
    def test_default_rule(self): self.assertEqual(contract(), {'TOKEN':{}})
    def test_all_options(self): self.assertEqual(contract({'type':'integer','min':1,'max':4,'required':False,'allow_empty':True,'choices':['2']})['TOKEN']['min'],1)
    def test_bad_json(self):
        with self.assertRaises(ConfigError): load_contract('{secret')
    def test_duplicate_json(self):
        with self.assertRaises(ConfigError): load_contract('{"version":1,"version":1,"variables":{"TOKEN":{}}}')
    def test_duplicate_rule_key(self):
        with self.assertRaises(ConfigError): load_contract('{"version":1,"variables":{"TOKEN":{"type":"string","type":"boolean"}}}')
    def test_wrong_structure(self):
        for doc in ([], {}, {'version':1,'variables':{},'typo':1}):
            with self.subTest(doc=doc), self.assertRaises(ConfigError): load_contract(json.dumps(doc))
    def test_bad_version(self):
        for version in (True,2,'1',None):
            with self.subTest(version=version), self.assertRaises(ConfigError): load_contract(json.dumps({'version':version,'variables':{'A':{}}}))
    def test_empty_variables(self):
        with self.assertRaises(ConfigError): load_contract('{"version":1,"variables":{}}')
    def test_too_many_variables(self):
        with self.assertRaises(ConfigError): load_contract(json.dumps({'version':1,'variables':{f'A{i}':{} for i in range(513)}}))
    def test_bad_variable_name(self):
        with self.assertRaises(ConfigError): load_contract('{"version":1,"variables":{"A-B":{}}}')
    def test_unknown_option(self):
        with self.assertRaises(ConfigError): contract({'requierd':True})
    def test_wrong_rule(self):
        with self.assertRaises(ConfigError): load_contract('{"version":1,"variables":{"A":[]}}')
    def test_wrong_type(self):
        for kind in ('port',[],True):
            with self.subTest(kind=kind), self.assertRaises(ConfigError): contract({'type':kind})
    def test_wrong_flags(self):
        for flag in ('required','allow_empty'):
            with self.subTest(flag=flag), self.assertRaises(ConfigError): contract({flag:'true'})
    def test_wrong_bounds(self):
        for rule in ({'min':1},{'type':'integer','min':True},{'type':'integer','min':1.5}):
            with self.subTest(rule=rule), self.assertRaises(ConfigError): contract(rule)
    def test_inverted_bounds(self):
        with self.assertRaises(ConfigError): contract({'type':'integer','min':5,'max':1})
    def test_bad_choices(self):
        for choices in ([], 'a', [1], ['a','a']):
            with self.subTest(choices=choices), self.assertRaises(ConfigError): contract({'choices':choices})


class ValidationTests(unittest.TestCase):
    def check(self, value, rule=None): return validate(contract(rule), {'TOKEN':value})
    def codes(self, report): return [e['code'] for e in report['errors']]
    def test_valid_string(self): self.assertTrue(self.check('hello')['ok'])
    def test_missing(self): self.assertEqual(self.codes(validate(contract(),{})), ['missing'])
    def test_optional_missing(self): self.assertTrue(validate(contract({'required':False}),{})['ok'])
    def test_optional_present_empty(self): self.assertEqual(self.codes(self.check('',{'required':False})), ['empty'])
    def test_empty(self):
        for v in ('', ' ', '\t'): self.assertEqual(self.codes(self.check(v)), ['empty'])
    def test_allow_empty_bypasses_type(self): self.assertTrue(self.check('',{'type':'integer','allow_empty':True})['ok'])
    def test_integer(self):
        for v in ('0','001','+12','-12'): self.assertTrue(self.check(v,{'type':'integer'})['ok'])
    def test_bad_integer(self):
        for v in ('1.0',' 1','1 ','१','NaN','1_000'):
            self.assertEqual(self.codes(self.check(v,{'type':'integer'})), ['invalid_integer'])
    def test_huge_integer(self): self.assertEqual(self.codes(self.check('1'*5000,{'type':'integer'})), ['invalid_integer'])
    def test_minimum(self): self.assertEqual(self.codes(self.check('0',{'type':'integer','min':1})), ['below_minimum'])
    def test_maximum(self): self.assertEqual(self.codes(self.check('10',{'type':'integer','max':9})), ['above_maximum'])
    def test_boundary(self): self.assertTrue(self.check('9',{'type':'integer','min':9,'max':9})['ok'])
    def test_boolean(self):
        for v in ('true','false'): self.assertTrue(self.check(v,{'type':'boolean'})['ok'])
    def test_bad_boolean(self):
        for v in ('TRUE','1','yes'): self.assertEqual(self.codes(self.check(v,{'type':'boolean'})), ['invalid_boolean'])
    def test_url(self):
        for v in ('https://example.com/a?x=1','http://localhost:3000','https://[::1]:123'):
            self.assertTrue(self.check(v,{'type':'http_url'})['ok'])
    def test_bad_url(self):
        for v in ('ftp://example.com','//example.com','https://','https://x:bad','https://x:0','https://x:65536','https://user:pass@x','https://x/a b','https://[bad','https://x\\evil'):
            self.assertEqual(self.codes(self.check(v,{'type':'http_url'})), ['invalid_http_url'])
    def test_choices(self): self.assertTrue(self.check('production',{'choices':['production','test']})['ok'])
    def test_not_choices(self): self.assertEqual(self.codes(self.check('dev',{'choices':['test']})), ['not_in_choices'])
    def test_extra_warn(self): self.assertEqual(validate(contract(),{'TOKEN':'x','OTHER':'private'})['warnings'],[{'name':'OTHER','code':'unexpected'}])
    def test_extra_strict(self): self.assertFalse(validate(contract(),{'TOKEN':'x','OTHER':'private'},True)['ok'])
    def test_deterministic(self): self.assertEqual(validate(contract(),{'Z':'s','TOKEN':'x','A':'s'})['warnings'],[{'name':'A','code':'unexpected'},{'name':'Z','code':'unexpected'}])
    def test_no_values(self): self.assertNotIn('PRIVATE_SENTINEL',json.dumps(self.check('PRIVATE_SENTINEL',{'type':'integer'})))
    def test_non_string(self):
        with self.assertRaises(ConfigError): self.check(1)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.schema=Path(self.temp.name)/'contract.json'; self.env=Path(self.temp.name)/'sample.env'
        self.schema.write_text('{"version":1,"variables":{"TOKEN":{"type":"integer"}}}')
        self.env.write_text('TOKEN=1')
    def run_cli(self,*extra):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=main([str(self.schema),*extra])
        return code,out.getvalue(),err.getvalue()
    def test_pass(self): self.assertEqual(self.run_cli('--env-file',str(self.env))[0],0)
    def test_fail(self):
        self.env.write_text('TOKEN=PRIVATE_SENTINEL')
        c,o,e=self.run_cli('--env-file',str(self.env),'--format','json')
        self.assertEqual(c,1); self.assertNotIn('PRIVATE_SENTINEL',o+e); self.assertFalse(json.loads(o)['ok'])
    def test_parse_error_no_leak(self):
        self.env.write_text('PRIVATE_SENTINEL')
        c,o,e=self.run_cli('--env-file',str(self.env),'--format','json')
        self.assertEqual(c,2); self.assertNotIn('PRIVATE_SENTINEL',o+e)
    def test_schema_error_no_leak(self):
        self.schema.write_text('{"PRIVATE_SENTINEL":')
        c,o,e=self.run_cli('--env-file',str(self.env))
        self.assertEqual(c,2); self.assertNotIn('PRIVATE_SENTINEL',o+e)
    def test_duplicate_no_leak(self):
        self.env.write_text('TOKEN=PRIVATE_SENTINEL\nTOKEN=PRIVATE_SENTINEL')
        c,o,e=self.run_cli('--env-file',str(self.env))
        self.assertEqual(c,2); self.assertNotIn('PRIVATE_SENTINEL',o+e)
    def test_bad_utf8(self):
        self.env.write_bytes(b'TOKEN=\xff'); self.assertEqual(self.run_cli('--env-file',str(self.env))[0],2)
    def test_bom(self):
        self.env.write_text('TOKEN=1',encoding='utf-8-sig'); self.assertEqual(self.run_cli('--env-file',str(self.env))[0],0)
    def test_missing_file_safe(self):
        c,o,e=self.run_cli('--env-file',str(self.env)+'PRIVATE_SENTINEL')
        self.assertEqual(c,2); self.assertNotIn('PRIVATE_SENTINEL',o+e)
    def test_process_declared_only(self):
        with patch.dict(os.environ,{'TOKEN':'1','UNRELATED_SECRET':'PRIVATE_SENTINEL'},clear=True):
            c,o,e=self.run_cli('--process','--format','json')
        self.assertEqual(c,0); self.assertNotIn('UNRELATED_SECRET',o); self.assertNotIn('PRIVATE_SENTINEL',o+e)
    def test_process_missing(self):
        with patch.dict(os.environ,{},clear=True): self.assertEqual(self.run_cli('--process')[0],1)
    def test_process_strict_invalid(self): self.assertEqual(self.run_cli('--process','--strict-extra')[0],2)
    def test_no_mutations(self):
        before=self.env.read_bytes(); self.run_cli('--env-file',str(self.env)); self.assertEqual(before,self.env.read_bytes())
    def test_bounded_read(self):
        with self.assertRaises(ConfigError): read_bounded(self.env,2)
    def test_env_limit(self):
        self.env.write_text('TOKEN='+'x'*1048576); self.assertEqual(self.run_cli('--env-file',str(self.env))[0],2)
    def test_schema_limit(self):
        self.schema.write_text(' '*262145); self.assertEqual(self.run_cli('--env-file',str(self.env))[0],2)


if __name__=='__main__': unittest.main()
