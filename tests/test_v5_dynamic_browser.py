"""Network-free tests; Windows integration uses local worker/child processes only."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import socket
import sys

import pytest

from dragon.browser_protocol import (LIMITS,BrowserFailure,assert_launch_policy,canonical_hash,safe_url,classify_error)
from dragon.dynamic_browser import DynamicBrowserExtractor,check_readiness,implementation_identity,run_worker
from dragon.discovery import FetchResponse,DiscoveryError,fetch_and_extract_source
from dragon.lock import RunLock
from dragon.browser_windows import WindowsJob,token_security

ROOT=Path(__file__).resolve().parents[1]
TEXT="Actual rendered source content. "*20


def response():
    return FetchResponse("https://example.com/source",200,"text/html",b"<html><script>app()</script></html>")


def extracted():
    return {"schema_version":1,"status":"PASS","text":TEXT,"title":"Source title",
            "url":response().url,"extraction_method":"crawl4ai-optional",
            "host":{"temporary_directory_removed":True,"cleanup":{"verified":True}},
            "dynamic_provenance":{"requested_url":response().url,"final_url":response().url,
                 "retrieved_at":"2026-10-05T12:00:00+00:00","http_status":200,
                 "ignore_https_errors":False,"sandbox_verified":True,"effective_arguments":[],
                 "extracted_text_sha256":hashlib.sha256(TEXT.strip().encode()).hexdigest()}}


def backend(tmp_path,runner):
    return DynamicBrowserExtractor(root=ROOT,runtime=Path(sys.executable),directory=tmp_path/"backend",diagnostic=True,runner=runner)


def ready_receipt():
    return {"status":"DYNAMIC_BROWSER_BACKEND_READY","verified_at":datetime.now(timezone.utc).isoformat(),
            "checks":dict.fromkeys(("secure_launch","renderer_sandbox","strict_tls","tls_negative",
                "structured_response","normalization","cleanup_success","cleanup_failure","cleanup_timeout",
                "concurrency","output_limit"),"PASS"),"implementation":implementation_identity(ROOT),
            "runtime":str(Path(sys.executable).resolve()),
            "runtime_sha256":hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),"limits":LIMITS}


def test_secure_success_structured_normalization_and_provenance(tmp_path):
    calls=[]
    def runner(*args,**kwargs):
        calls.append(args[2]); return extracted()
    extractor=backend(tmp_path,runner)
    result=fetch_and_extract_source(response().url,transport=lambda *_:response(),
        fallback_extractor=extractor,dynamic_only=True)
    assert len(calls)==1 and calls[0]["operation"]=="probe"
    assert result["verification_status"]=="EXTRACTED_NOT_VERIFIED"
    assert result["retrieved_at"]=="2026-10-05T12:00:00+00:00"
    assert result["content_hash"]==hashlib.sha256(TEXT.strip().encode()).hexdigest()
    digest=result["dynamic_provenance"].pop("normalized_output_sha256")
    assert digest==canonical_hash(result)
    assert extractor.last_receipt["response"]["host"]["temporary_directory_removed"] is True


@pytest.mark.parametrize("flag",["--no-sandbox","--no-sandbox=true","--ignore-certificate-errors",
                                "--allow-insecure-localhost","--disable-web-security"])
def test_readiness_rejects_unsafe_flags(flag):
    with pytest.raises(BrowserFailure,match="Forbidden"):
        assert_launch_policy({"chromium_sandbox":True,"args":[flag]})


@pytest.mark.parametrize("options",[{"chromium_sandbox":False},{"chromium_sandbox":True,"ignore_https_errors":True}])
def test_sandbox_and_tls_intent_must_be_explicit(options):
    with pytest.raises(BrowserFailure): assert_launch_policy(options)


@pytest.mark.parametrize("url",["http://example.com","file:///C:/secret","https://127.0.0.1",
                               "https://10.0.0.1","https://localhost","https://x.internal",
                               "https://user:pass@example.com","https://example.com:8443"])
def test_network_policy_rejects_local_and_unsafe_targets(url):
    with pytest.raises(BrowserFailure): safe_url(url)


def test_network_policy_rejects_private_dns(monkeypatch):
    monkeypatch.setattr(socket,"getaddrinfo",lambda *_args,**_kwargs:[(None,None,None,None,("192.168.1.2",443))])
    with pytest.raises(BrowserFailure): safe_url("https://example.com",resolve=True)


@pytest.mark.parametrize(("detail","phase","expected"),[
    ("net::ERR_CERT_AUTHORITY_INVALID","navigation","DYNAMIC_TLS_FAILURE"),
    ("Timeout 15000ms exceeded","navigation","DYNAMIC_NAVIGATION_TIMEOUT"),
    ("No browser binary","launch","DYNAMIC_LAUNCH_FAILURE"),
    ("TargetClosed: browser has been closed","navigation","DYNAMIC_BROWSER_CRASH"),
    ("net::ERR_CONNECTION_RESET","navigation","DYNAMIC_PAGE_RETRIEVAL_FAILURE")])
def test_failure_classification(detail,phase,expected):
    assert classify_error(detail,phase=phase)==expected


@pytest.mark.parametrize("code",["DYNAMIC_TLS_FAILURE","DYNAMIC_NAVIGATION_TIMEOUT","DYNAMIC_LAUNCH_FAILURE",
                                  "DYNAMIC_BROWSER_CRASH","DYNAMIC_EXTRACTION_FAILURE","DYNAMIC_POLICY_REJECTED"])
def test_backend_failures_are_explicit_and_captured(tmp_path,code):
    extractor=backend(tmp_path,lambda *_args,**_kwargs:{"schema_version":1,"status":"FAIL","code":code,"detail":"controlled failure"})
    with pytest.raises(DiscoveryError) as error: extractor(response(),"bounded dynamic recovery")
    assert error.value.code==code
    assert extractor.last_receipt["response"]["code"]==code
    assert list((tmp_path/"backend/attempts").glob("*/response.json"))


def test_unavailable_runtime(tmp_path):
    extractor=DynamicBrowserExtractor(root=ROOT,runtime=tmp_path/"missing",directory=tmp_path,diagnostic=True)
    with pytest.raises(DiscoveryError) as error: extractor(response(),"dynamic")
    assert error.value.code=="DYNAMIC_BACKEND_UNAVAILABLE"
    assert extractor.readiness()["reasons"]==["RUNTIME_MISSING"]


def test_concurrency_refuses_second_job(tmp_path):
    extractor=backend(tmp_path,lambda *_a,**_k:pytest.fail("must not execute"))
    with RunLock(extractor.directory/"dynamic-job.lock","UTC"):
        with pytest.raises(DiscoveryError) as error: extractor(response(),"dynamic")
    assert error.value.code=="DYNAMIC_CONCURRENCY_LIMIT"


def test_lineage_and_single_call_per_action(tmp_path):
    calls=[]
    def runner(*args,**kwargs):
        calls.append(args[2]); return extracted()
    extractor=backend(tmp_path,runner)
    call=extractor.for_action({"action_id":"ACT-1","origin_action_id":"ACT-0","job_id":"JOB-1"})
    call(response(),"dynamic")
    assert calls[0]["lineage"]["action_id"]=="ACT-1"
    assert calls[0]["lineage"]["parent_action_id"]=="ACT-0"
    with pytest.raises(DiscoveryError) as error: call(response(),"dynamic")
    assert error.value.code=="DYNAMIC_POLICY_REJECTED"
    assert len(calls)==1 and LIMITS["retries"]==0 and LIMITS["dynamic_calls_per_action"]==1


def test_normalization_hash_mismatch_fails(tmp_path):
    value=extracted(); value["dynamic_provenance"]["extracted_text_sha256"]="wrong"
    with pytest.raises(DiscoveryError) as error:
        backend(tmp_path,lambda *_a,**_k:value)(response(),"dynamic")
    assert error.value.code=="DYNAMIC_NORMALIZATION_FAILURE"
    evaluation=next((tmp_path/"backend/attempts").glob("*/evaluation.json"))
    assert json.loads(evaluation.read_text())["code"]=="DYNAMIC_NORMALIZATION_FAILURE"


@pytest.mark.parametrize("check",list(ready_receipt()["checks"]))
def test_readiness_requires_every_mandatory_check(check):
    receipt=ready_receipt(); receipt["checks"][check]="FAIL"
    assert check_readiness(receipt,root=ROOT,runtime=Path(sys.executable))["state"]=="SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE"


def test_readiness_true_only_when_all_checks_pass():
    assert check_readiness(ready_receipt(),root=ROOT,runtime=Path(sys.executable))["state"]=="DYNAMIC_ADAPTER_READY"


def test_stale_or_changed_receipt_rejected():
    receipt=ready_receipt(); receipt["verified_at"]=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    assert "READINESS_STALE" in check_readiness(receipt,root=ROOT,runtime=Path(sys.executable))["reasons"]
    receipt=ready_receipt(); receipt["implementation"]={}
    assert "IMPLEMENTATION_CHANGED" in check_readiness(receipt,root=ROOT,runtime=Path(sys.executable))["reasons"]


@pytest.mark.skipif(os.name!="nt",reason="Windows Job Object integration")
@pytest.mark.parametrize("mode",["success","failure","timeout","output"])
def test_native_job_cleans_descendants_on_success_failure_timeout(tmp_path,mode):
    # The child never accesses a network; job ownership precedes request release.
    worker=tmp_path/"worker.py"
    worker.write_text("""import sys,json,subprocess,time
request=json.load(sys.stdin)
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
if request['mode']=='timeout': time.sleep(60)
elif request['mode']=='output': sys.stdout.buffer.write(b'x'*2100000); sys.stdout.flush(); time.sleep(60)
elif request['mode']=='failure': print(json.dumps({'schema_version':1,'status':'FAIL','code':'DYNAMIC_LAUNCH_FAILURE','detail':'controlled'}))
else:
    import hashlib
    value={'schema_version':1,'status':'PASS','text':'test'}
    value['response_sha256']=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    print(json.dumps(value))
""",encoding="utf-8")
    value=run_worker(Path(sys.executable),worker,{"mode":mode},workspace=tmp_path,timeout=1 if mode in ("timeout","output") else 5)
    assert value["host"]["cleanup"]["verified"] is True
    assert value["host"]["cleanup"]["after"]["active_processes"]==0
    assert value["host"]["cleanup"]["before"]["total_processes"]>=2
    assert value["host"]["job_limits"]["breakaway"] is False
    if mode=="timeout": assert value["code"]=="DYNAMIC_NAVIGATION_TIMEOUT"
    elif mode=="output": assert value["code"]=="DYNAMIC_OUTPUT_LIMIT"
    elif mode=="failure": assert value["code"]=="DYNAMIC_LAUNCH_FAILURE"
    else: assert value["status"]=="PASS"


@pytest.mark.skipif(os.name!="nt",reason="Windows token integration")
def test_token_inspection_is_observation_not_string_removal():
    facts=token_security(os.getpid())
    assert isinstance(facts["integrity_rid"],int)
    assert facts["pid"]==os.getpid()
    assert facts["sandbox_verified"] is False  # ordinary production Python is not a renderer sandbox


def probe_proof(tmp_path):
    value=extracted(); file=tmp_path/"runtime.bin"; file.write_bytes(b"pinned dependency")
    value["rendered_html"]="<html>fixture</html>"
    proof=value["dynamic_provenance"]
    proof.update(worker_pid=10,process_tree=[{"id":11,"type":"browser"},{"id":12,"type":"renderer"}],
        renderer_tokens=[{"pid":12,"integrity_rid":4096,"restricted_token":True,"app_container":False,"sandbox_verified":True}],
        launch_options={"chromium_sandbox":True,"args":[]},tls_negative={"status":"PASS","error":"net::ERR_CERT_AUTHORITY_INVALID"},
        javascript_verified=True,content_sha256=hashlib.sha256(value["rendered_html"].encode()).hexdigest(),
        runtime_files={str(file):hashlib.sha256(file.read_bytes()).hexdigest()})
    value["host"].update(exit_status=0,cleanup={"verified":True,"after":{"active_processes":0}},
        job_limits={"memory_bytes":LIMITS["memory_bytes"],"active_processes":LIMITS["processes"],
                    "cpu_percent":LIMITS["cpu_percent"],"kill_on_close":True,"breakaway":False},
        browser_job_membership=[{"pid":x,"contained":True} for x in (10,11,12)])
    return value,{"operation":"probe","url":response().url},{"offline":False,"purpose":"OPERATIONAL_DIAGNOSTIC_NOT_RESEARCH"}


def test_promotion_requires_actual_complete_probe_proof(tmp_path):
    from dragon_browser_readiness import validate_probe_proof
    value,request,summary=probe_proof(tmp_path)
    validate_probe_proof(value,request,summary,offline=False)


@pytest.mark.parametrize("defect",["operation","containment","missing_worker","renderer_token","tls","cleanup","job_limit","content","runtime"])
def test_promotion_rejects_missing_or_unsafe_actual_proof(tmp_path,defect):
    from dragon_browser_readiness import validate_probe_proof
    value,request,summary=probe_proof(tmp_path)
    if defect=="operation": request["operation"]="offline_probe"
    elif defect=="containment": value["host"]["browser_job_membership"][1]["contained"]=False
    elif defect=="missing_worker": value["host"]["browser_job_membership"].pop(0)
    elif defect=="renderer_token": value["dynamic_provenance"]["renderer_tokens"][0]["restricted_token"]=False
    elif defect=="tls": value["dynamic_provenance"]["tls_negative"]["error"]="Timeout"
    elif defect=="cleanup": value["host"]["cleanup"]["after"]["active_processes"]=1
    elif defect=="job_limit": value["host"]["job_limits"]["breakaway"]=True
    elif defect=="content": value["rendered_html"]="tampered"
    elif defect=="runtime": next(iter(value["dynamic_provenance"]["runtime_files"])); (tmp_path/"runtime.bin").write_bytes(b"changed")
    with pytest.raises(DiscoveryError): validate_probe_proof(value,request,summary,offline=False)


def test_registration_rechecks_proof_and_dependency_hashes(tmp_path):
    extractor=backend(tmp_path,lambda *_a,**_k:pytest.fail("no execution"))
    proof=extractor.directory/"proof.json"; proof.write_text("proof")
    dependency=tmp_path/"dependency"; dependency.write_text("dependency")
    receipt=ready_receipt()
    receipt["proof_artifacts"]={"proof.json":hashlib.sha256(proof.read_bytes()).hexdigest()}
    receipt["runtime_files"]={str(dependency):hashlib.sha256(dependency.read_bytes()).hexdigest()}
    data=json.dumps(receipt).encode()
    (extractor.directory/"readiness.json").write_bytes(data)
    (extractor.directory/"readiness.sha256").write_text(hashlib.sha256(data).hexdigest())
    assert extractor.readiness()["state"]=="DYNAMIC_ADAPTER_READY"
    proof.write_text("tampered")
    assert extractor.readiness()["reasons"]==["READINESS_PROOF_CHANGED"]
    proof.write_text("proof"); dependency.write_text("changed")
    assert extractor.readiness()["reasons"]==["BROWSER_DEPENDENCY_CHANGED"]


@pytest.mark.skipif(os.name!="nt",reason="Windows Job integration")
def test_native_worker_joins_exact_parent_job_before_browser_import(tmp_path):
    worker=tmp_path/"worker.py"
    worker.write_text("import sys,os,json\nsys.path.insert(0,"+repr(str(ROOT/"dragon"))+")\n"
        "from browser_windows import join_parent_job\n"
        "facts=join_parent_job(os.environ['DRAGON_BROWSER_JOB_NAME'])\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'schema_version':1,'status':'FAIL','code':'EXPECTED_CONTAINED_WORKER','detail':str(facts)}))",encoding="utf-8")
    value=run_worker(Path(sys.executable),worker,{},workspace=tmp_path,timeout=5)
    assert value["code"]=="EXPECTED_CONTAINED_WORKER"
    assert "'verified': True" in value["detail"] and value["host"]["cleanup"]["verified"] is True


def test_local_opt_in_cannot_register_native_backend_without_host_proof(tmp_path,monkeypatch):
    import dragon.dynamic_browser as module
    monkeypatch.setattr(module,"local_browser_directory",lambda _root:tmp_path)
    (tmp_path/"runtime.json").write_text(json.dumps({"python_executable":sys.executable,"enabled":True}),encoding="utf-8")
    with pytest.raises(DiscoveryError) as error:
        module.dynamic_extractor_from_config(ROOT)
    assert error.value.code=="SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE"
    assert "READINESS_RECEIPT_INVALID" in str(error.value)


def test_unconfigured_optional_browser_does_not_block_static_factory(tmp_path,monkeypatch):
    import dragon.dynamic_browser as module
    monkeypatch.setattr(module,"local_browser_directory",lambda _root:tmp_path)
    assert module.dynamic_extractor_from_config(ROOT) is None
    (tmp_path/"runtime.json").write_text(json.dumps({"python_executable":sys.executable,"enabled":False}),encoding="utf-8")
    assert module.dynamic_extractor_from_config(ROOT) is None


def test_local_opt_in_with_all_proofs_registers_actual_native_adapter(tmp_path,monkeypatch):
    import dragon.dynamic_browser as module
    from dragon.deep_research_executor import discovery_adapter_from_config
    monkeypatch.setattr(module,"local_browser_directory",lambda _root:tmp_path)
    (tmp_path/"runtime.json").write_text(json.dumps({"python_executable":sys.executable,"enabled":True}),encoding="utf-8")
    proof=tmp_path/"proof.json"; proof.write_text("verified fixture")
    dependency=tmp_path/"runtime-dependency"; dependency.write_text("pinned")
    receipt=ready_receipt()
    receipt["proof_artifacts"]={"proof.json":hashlib.sha256(proof.read_bytes()).hexdigest()}
    receipt["runtime_files"]={str(dependency):hashlib.sha256(dependency.read_bytes()).hexdigest()}
    data=json.dumps(receipt).encode(); (tmp_path/"readiness.json").write_bytes(data)
    (tmp_path/"readiness.sha256").write_text(hashlib.sha256(data).hexdigest())
    backend=module.dynamic_extractor_from_config(ROOT)
    assert isinstance(backend,module.DynamicBrowserExtractor) and backend.readiness()["state"]=="DYNAMIC_ADAPTER_READY"
    adapter=discovery_adapter_from_config(ROOT)
    members=getattr(adapter,"adapters",[adapter])
    assert members and all(isinstance(item.fallback_extractor,module.DynamicBrowserExtractor) for item in members)
