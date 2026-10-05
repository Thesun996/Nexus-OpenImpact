import json
import os
import subprocess
import sys
from pathlib import Path
import pytest


@pytest.mark.parametrize('demo,count,coverage',[('symbol_rename',1,'complete'),('symbol_removal',1,'complete'),('symbol_no_impact',0,'complete'),('symbol_boundaries',1,'partial')])
def test_symbol_cli_demo(demo,count,coverage):
    root=Path(__file__).resolve().parents[2]
    project=root/'examples'/demo
    result=subprocess.run([sys.executable,'-m','openimpact','analyze',str(project),'--change',str(project/'change.json'),'--format','json'],capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONUTF8':'1','OPENIMPACT_LLM_PROVIDER':'rule'})
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['summary']['direct_reference_count']==count
    assert report['coverage']['status']==coverage
    if count: assert report['summary']['indirect_1hop_module_count']==1 and report['summary']['indirect_2hop_module_count']==1
