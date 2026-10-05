"""Provider-free browser readiness. Never runs a research stage."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

from dragon.browser_protocol import BrowserFailure,LIMITS,assert_launch_policy,canonical_hash
from dragon.dynamic_browser import dynamic_extractor_from_config,implementation_identity,local_browser_directory
from dragon.discovery import DiscoveryError,FetchResponse,fetch_and_extract_source


def probe(root,*,url,offline=False):
    extractor=dynamic_extractor_from_config(root,diagnostic="offline" if offline else True)
    if extractor is None: raise DiscoveryError("SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","Optional route not configured")
    kwargs={}
    if offline:
        url="https://fixture.invalid/"
        kwargs["transport"]=lambda *_:FetchResponse(url,200,"text/html",b"<html><script>fixture</script></html>")
    result=fetch_and_extract_source(url,fallback_extractor=extractor,dynamic_only=True,**kwargs)
    capture=Path(extractor.last_receipt["capture"])
    (capture/"normalized.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    summary={"status":"PROBE_PASS_NOT_REGISTERED","purpose":"OPERATIONAL_DIAGNOSTIC_NOT_RESEARCH",
        "offline":offline,"capture":str(capture),"url":url,"http_status":result["http_status"],
        "retrieved_at":result["retrieved_at"],"content_hash":result["content_hash"],
        "normalized_output_sha256":result["dynamic_provenance"]["normalized_output_sha256"],
        "provider_calls":0,"research_actions":0}
    (capture/"probe-summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    return summary


def qualify(root, *, live_capture, offline_capture, controls_log):
    """Promote only independently captured operational and network-free control proofs."""
    directory=local_browser_directory(root)
    for path in (live_capture,offline_capture):
        if not path.resolve().is_relative_to((directory/"attempts").resolve()):
            raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Probe outside the local adapter capture tree")
    live=json.loads((live_capture/"response.json").read_text(encoding="utf-8"))
    normalized=json.loads((live_capture/"normalized.json").read_text(encoding="utf-8"))
    offline=json.loads((offline_capture/"response.json").read_text(encoding="utf-8"))
    if live_capture.resolve()==offline_capture.resolve():
        raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Live and offline proofs must be distinct")
    for capture,value,is_offline in ((live_capture,live,False),(offline_capture,offline,True)):
        if json.loads((capture/"implementation.json").read_text(encoding="utf-8"))!=implementation_identity(root):
            raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Probe ran a different implementation")
        request=json.loads((capture/"request.json").read_text(encoding="utf-8"))
        summary=json.loads((capture/"probe-summary.json").read_text(encoding="utf-8"))
        validate_probe_proof(value,request,summary,offline=is_offline)
    log=controls_log.read_text(encoding="utf-8-sig")
    if "failed" in log.casefold() or "ERROR" in log or "PASSED" not in log:
        raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Focused control tests did not pass")
    for name in ("test_native_job_cleans_descendants_on_success_failure_timeout[success]",
                 "test_native_job_cleans_descendants_on_success_failure_timeout[failure]",
                 "test_native_job_cleans_descendants_on_success_failure_timeout[timeout]",
                 "test_native_job_cleans_descendants_on_success_failure_timeout[output]",
                 "test_concurrency_refuses_second_job","test_readiness_rejects_unsafe_flags",
                 "test_secure_success_structured_normalization_and_provenance"):
        if not any(name in line and "PASSED" in line for line in log.splitlines()):
            raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Missing passed control: "+name)
    metadata=live["dynamic_provenance"]
    for value in (live,offline):
        if value.get("status")!="PASS" or not value["host"]["cleanup"]["verified"] or not value["host"]["temporary_directory_removed"]:
            raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Acquisition or cleanup did not pass")
        proof=value["dynamic_provenance"]
        assert_launch_policy({"chromium_sandbox":True,"args":proof["effective_arguments"]})
        if proof["sandbox_verified"] is not True or proof["ignore_https_errors"] is not False or proof["tls_negative"]["status"]!="PASS":
            raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Sandbox/TLS proof incomplete")
    original_hash=normalized["dynamic_provenance"].pop("normalized_output_sha256")
    if canonical_hash(normalized)!=original_hash:
        raise DiscoveryError("DYNAMIC_NORMALIZATION_FAILURE","Normalized response hash differs")
    proofs={}
    for capture in (live_capture,offline_capture):
        for name in ("request.json","response.json","normalized.json","probe-summary.json","implementation.json","evaluation.json"):
            path=capture/name
            proofs[path.relative_to(directory).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    target=directory/"focused-controls.log"
    if target.exists(): raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Control proof already exists")
    target.write_bytes(controls_log.read_bytes())
    proofs[target.relative_to(directory).as_posix()]=hashlib.sha256(target.read_bytes()).hexdigest()
    runtime=dynamic_extractor_from_config(root,diagnostic=True).runtime
    receipt={"status":"DYNAMIC_BROWSER_BACKEND_READY","verified_at":datetime.now(timezone.utc).isoformat(),
        "implementation":implementation_identity(root),"limits":LIMITS,"runtime":str(runtime.resolve()),
        "runtime_sha256":hashlib.sha256(runtime.read_bytes()).hexdigest(),"runtime_files":metadata["runtime_files"],
        "checks":dict.fromkeys(("secure_launch","renderer_sandbox","strict_tls","tls_negative",
             "structured_response","normalization","cleanup_success","cleanup_failure","cleanup_timeout",
             "concurrency","output_limit"),"PASS"),"proof_artifacts":proofs,
        "provider_calls":0,"research_actions":0,"research_budget_used":0,
        "browser_version":metadata["browser_version"],"limitations":["Windows only","same-host HTTPS only",
             "temporary storage monitored, not OS quota","browser broker runs as the local user",
             "readiness expires after 24 hours and is invalidated by runtime/code/browser changes"]}
    data=(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n").encode()
    if (directory/"readiness.json").exists(): raise DiscoveryError("DYNAMIC_READINESS_FAILURE","Readiness receipt already exists; preserve before requalification")
    (directory/"readiness.json").write_bytes(data)
    (directory/"readiness.sha256").write_text(hashlib.sha256(data).hexdigest()+"\n",encoding="ascii")
    return receipt


def validate_probe_proof(value,request,summary,*,offline):
    """Require actual contained processes and token/TLS evidence before promotion."""
    def require(condition,detail):
        if not condition: raise DiscoveryError("DYNAMIC_READINESS_FAILURE",detail)
    require(request.get("operation")==("offline_probe" if offline else "probe"),"Wrong probe operation")
    require(summary.get("offline") is offline and summary.get("purpose")=="OPERATIONAL_DIAGNOSTIC_NOT_RESEARCH",
            "Missing separate operational probe identity")
    require(value.get("status")=="PASS","Probe failed")
    host=value.get("host",{}); proof=value.get("dynamic_provenance",{})
    require(host.get("exit_status")==0 and host.get("cleanup",{}).get("verified") is True
            and host.get("cleanup",{}).get("after",{}).get("active_processes")==0
            and host.get("temporary_directory_removed") is True,"Process or workspace cleanup unproven")
    require(host.get("job_limits")=={"memory_bytes":LIMITS["memory_bytes"],"active_processes":LIMITS["processes"],
        "cpu_percent":LIMITS["cpu_percent"],"kill_on_close":True,"breakaway":False},"Enforced Job policy differs")
    members=host.get("browser_job_membership",[])
    require(bool(members) and all(x.get("contained") is True for x in members),"Actual process containment failed")
    tree=proof.get("process_tree",[])
    require({int(x["id"]) for x in tree}|{proof.get("worker_pid")}=={x.get("pid") for x in members},
            "Process ledger does not cover worker and browser tree")
    tokens=proof.get("renderer_tokens",[])
    require(bool(tokens) and {int(x["id"]) for x in tree if x["type"]=="renderer"}=={x.get("pid") for x in tokens}
        and all(x.get("sandbox_verified") is True and isinstance(x.get("integrity_rid"),int)
            and x["integrity_rid"]<=4096 and (x.get("restricted_token") is True or x.get("app_container") is True)
            for x in tokens),"Renderer token proof incomplete")
    assert_launch_policy(proof.get("launch_options",{}))
    assert_launch_policy({"chromium_sandbox":True,"args":proof.get("effective_arguments",[])})
    require(proof.get("ignore_https_errors") is False and proof.get("tls_negative",{}).get("status")=="PASS"
        and "ERR_CERT_" in proof["tls_negative"].get("error",""),"Strict TLS fixture rejection unproven")
    require(proof.get("javascript_verified") is True,"JavaScript rendering unproven")
    require(proof.get("requested_url")==request.get("url") and proof.get("http_status")==200,
            "Probe request/status differs")
    require(hashlib.sha256(value.get("text","").strip().encode()).hexdigest()==proof.get("extracted_text_sha256")
        and hashlib.sha256(value.get("rendered_html","").encode()).hexdigest()==proof.get("content_sha256"),
        "Content hashes differ")
    require(bool(proof.get("runtime_files")),"Runtime file inventory missing")
    for name,digest in proof["runtime_files"].items():
        require(Path(name).is_file() and hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,
                "Runtime dependency changed")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("probe","offline-probe","status","qualify"))
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument("--url",default="https://www.python.org/about/")
    parser.add_argument("--live-capture",type=Path)
    parser.add_argument("--offline-capture",type=Path)
    parser.add_argument("--controls-log",type=Path)
    args=parser.parse_args()
    if args.operation=="qualify" and any(value is None for value in (args.live_capture,args.offline_capture,args.controls_log)):
        parser.error("qualify requires --live-capture, --offline-capture and --controls-log")
    try:
        if args.operation=="status":
            backend=dynamic_extractor_from_config(args.root,diagnostic=True)
            result=backend.readiness() if backend else {"state":"SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE"}
        elif args.operation=="qualify":
            result=qualify(args.root,live_capture=args.live_capture,offline_capture=args.offline_capture,controls_log=args.controls_log)
        else:
            result=probe(args.root,url=args.url,offline=args.operation=="offline-probe")
    except (DiscoveryError,BrowserFailure) as exc:
        result={"status":"LIVE_ACCEPTANCE_BLOCKED_BROWSER_BACKEND","code":exc.code,"detail":exc.detail,
                "provider_calls":0,"research_actions":0}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get("status") in {"PROBE_PASS_NOT_REGISTERED","DYNAMIC_BROWSER_BACKEND_READY"} or result.get("state")=="DYNAMIC_ADAPTER_READY" else 1

if __name__=="__main__": sys.exit(main())
