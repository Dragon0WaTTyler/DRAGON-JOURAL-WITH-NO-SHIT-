"""Production-side binding to the existing exceptional ExtractionFallback."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

from dragon.browser_protocol import (LIMITS,BrowserFailure,canonical_hash,safe_url,assert_launch_policy,write_json_atomic)
from dragon.browser_windows import WindowsJob,process_alive
from dragon.discovery import DiscoveryError
from dragon.lock import RunLock,DuplicateRunError,process_alive as posix_process_alive


def implementation_identity(root):
    paths=["dragon/"+name for name in ("dynamic_browser.py","browser_worker.py","browser_windows.py",
        "browser_protocol.py","discovery.py","deep_research_executor.py")]+["dragon_browser_readiness.py"]
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths}


def local_browser_directory(root):
    result=subprocess.run(["git","-C",str(root),"rev-parse","--git-common-dir"],capture_output=True,text=True,check=True,timeout=10)
    directory=Path(result.stdout.strip())
    return (directory if directory.is_absolute() else root/directory).resolve()/"dragon"/"dynamic-browser"


def check_readiness(receipt, *, root, runtime, now=None):
    """Fail closed on stale/missing proofs, changed code, runtime or policy."""
    reasons=[]
    moment=now or datetime.now(timezone.utc)
    if receipt.get("status")!="DYNAMIC_BROWSER_BACKEND_READY": reasons.append("READINESS_NOT_PASS")
    required={"secure_launch","renderer_sandbox","strict_tls","tls_negative","structured_response",
              "normalization","cleanup_success","cleanup_failure","cleanup_timeout","concurrency","output_limit"}
    checks=receipt.get("checks",{})
    reasons.extend("CHECK_"+key.upper() for key in sorted(required) if checks.get(key)!="PASS")
    try:
        created=datetime.fromisoformat(receipt["verified_at"])
        age=(moment-created).total_seconds()
        if not 0<=age<=86400: reasons.append("READINESS_STALE")
    except (KeyError,ValueError,TypeError): reasons.append("READINESS_TIMESTAMP_INVALID")
    if receipt.get("implementation")!=implementation_identity(root): reasons.append("IMPLEMENTATION_CHANGED")
    if receipt.get("limits")!=LIMITS: reasons.append("LIMIT_POLICY_CHANGED")
    if receipt.get("runtime")!=str(runtime.resolve()): reasons.append("RUNTIME_CHANGED")
    if receipt.get("runtime_sha256")!=hashlib.sha256(runtime.read_bytes()).hexdigest(): reasons.append("RUNTIME_BINARY_CHANGED")
    return {"state":"DYNAMIC_ADAPTER_READY" if not reasons else "SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","reasons":reasons}


def run_worker(runtime, worker, request, *, workspace, job_factory=WindowsJob, timeout=30):
    """Bound pipes and all descendants. Request release follows successful job assignment."""
    command=[str(runtime),"-I","-u",str(worker)]
    environment={key:value for key,value in os.environ.items()
                 if key.upper() in {"SYSTEMROOT","WINDIR","LOCALAPPDATA","APPDATA","USERPROFILE","PROGRAMFILES","PROGRAMFILES(X86)"}}
    environment.update(TEMP=str(workspace),TMP=str(workspace),
                       CRAWL4_AI_BASE_DIRECTORY=str(workspace),
                       LITELLM_LOCAL_MODEL_COST_MAP="True",CRAWL4AI_TELEMETRY_ENABLED="false")
    data=json.dumps(request,ensure_ascii=False).encode()
    if len(data)>65536: raise BrowserFailure("DYNAMIC_POLICY_REJECTED","Worker request exceeds limit")
    job=job_factory(memory_bytes=LIMITS["memory_bytes"],processes=LIMITS["processes"],cpu_percent=LIMITS["cpu_percent"])
    environment["DRAGON_BROWSER_JOB_NAME"]=job.name
    process=None
    buffers={"stdout":bytearray(),"stderr":bytearray()}
    output_exceeded=threading.Event()
    readers=[]
    receipt={"command":command,"started_at":datetime.now(timezone.utc).isoformat(),
             "enforced_limits":{key:value for key,value in LIMITS.items() if key!="temp_bytes"},
             "temporary_storage_threshold_bytes":LIMITS["temp_bytes"],"temporary_storage_limit":"MONITORED_NOT_OS_QUOTA",
             "job_limits":job.limits}
    failure=None
    def drain(stream,key,cap):
        while True:
            chunk=stream.read(8192)
            if not chunk: return
            room=cap-len(buffers[key])
            buffers[key].extend(chunk[:max(0,room)])
            if len(chunk)>room:
                output_exceeded.set()
                # Keep draining without retaining additional bytes until the job is stopped.
    try:
        flags=(subprocess.CREATE_NO_WINDOW | 0x4) if os.name=="nt" else 0  # CREATE_SUSPENDED
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 env=environment,cwd=workspace,creationflags=flags)
        job.assign(process)
        job.resume(process.pid)
        receipt["worker_pid"]=process.pid
        for key,cap in (("stdout",LIMITS["output_bytes"]),("stderr",LIMITS["stderr_bytes"])):
            reader=threading.Thread(target=drain,args=(getattr(process,key),key,cap),daemon=True)
            reader.start(); readers.append(reader)
        deadline=time.monotonic()+min(timeout,LIMITS["wall_seconds"])
        def send_request():
            try:
                process.stdin.write(data); process.stdin.close()
            except (BrokenPipeError,OSError):
                pass
        sender=threading.Thread(target=send_request,daemon=True)
        sender.start(); readers.append(sender)
        while process.poll() is None:
            ledger=workspace/"browser-processes.json"
            ack=workspace/"containment.json"
            if ledger.is_file() and not ack.exists():
                try:
                    pids=json.loads(ledger.read_text(encoding="utf-8"))
                    if not isinstance(pids,list) or not 1<=len(pids)<=LIMITS["processes"]:
                        raise ValueError("Invalid browser process ledger")
                    members=[{"pid":int(pid),"contained":job.contains(pid)} for pid in pids]
                    receipt["browser_job_membership"]=members
                    write_json_atomic(ack,{"verified":all(x["contained"] for x in members),"processes":members})
                except (OSError,ValueError,TypeError) as exc:
                    write_json_atomic(ack,{"verified":False,"error":str(exc)})
            if output_exceeded.is_set():
                failure=BrowserFailure("DYNAMIC_OUTPUT_LIMIT","Worker output exceeded bound"); break
            if time.monotonic()>=deadline:
                failure=BrowserFailure("DYNAMIC_NAVIGATION_TIMEOUT","Host worker wall timeout"); break
            storage=0
            for path in workspace.rglob("*"):
                try:
                    if path.is_file(): storage+=path.stat().st_size
                except FileNotFoundError:
                    pass  # Browser cache files may disappear while being observed.
            if storage>LIMITS["temp_bytes"]:
                failure=BrowserFailure("DYNAMIC_STORAGE_LIMIT","Temporary storage threshold exceeded"); break
            time.sleep(0.03)
    except (OSError,subprocess.SubprocessError) as exc:
        failure=BrowserFailure("DYNAMIC_BACKEND_UNAVAILABLE",str(exc))
    finally:
        try:
            receipt["cleanup"]=job.cleanup()
        finally:
            job.close()
        if process is not None:
            # A failed assignment has no descendants: stdin was never released.
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            receipt["exit_status"]=process.returncode
            for reader in readers: reader.join(timeout=3)
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream is not None and not stream.closed: stream.close()
        receipt["stderr"]=buffers["stderr"].decode("utf-8",errors="replace")
        receipt["completed_at"]=datetime.now(timezone.utc).isoformat()
    if not receipt["cleanup"]["verified"]:
        failure=BrowserFailure("DYNAMIC_CLEANUP_FAILURE","Descendant cleanup could not be verified")
    if output_exceeded.is_set() and failure is None:
        failure=BrowserFailure("DYNAMIC_OUTPUT_LIMIT","Worker output exceeded bound")
    if failure:
        return {"schema_version":1,"status":"FAIL","code":failure.code,"detail":failure.detail,"host":receipt}
    try:
        response=json.loads(buffers["stdout"])
        if not isinstance(response,dict) or response.get("schema_version")!=1 or response.get("status") not in {"PASS","FAIL"}:
            raise ValueError("Unsupported worker response")
        if receipt["exit_status"]!=0:
            raise BrowserFailure("DYNAMIC_BROWSER_CRASH",f"Worker exited {receipt['exit_status']}")
        if response["status"]=="PASS":
            digest=response.pop("response_sha256",None)
            if digest!=canonical_hash(response):
                raise ValueError("Worker response hash differs")
            response["worker_response_sha256"]=digest
            receipt["stdout_sha256"]=hashlib.sha256(buffers["stdout"]).hexdigest()
        response["host"]=receipt
        return response
    except BrowserFailure as exc:
        return {"schema_version":1,"status":"FAIL","code":exc.code,"detail":exc.detail,"host":receipt}
    except (ValueError,UnicodeError) as exc:
        return {"schema_version":1,"status":"FAIL","code":"DYNAMIC_NORMALIZATION_FAILURE","detail":str(exc),"host":receipt}


class DynamicBrowserExtractor:
    def __init__(self, *, root, runtime, directory, diagnostic=False, runner=run_worker):
        self.root,self.runtime,self.directory=Path(root),Path(runtime),Path(directory)
        self.diagnostic,self.runner=diagnostic,runner
        self.directory.mkdir(parents=True,exist_ok=True)
        self.last_receipt=None

    def readiness(self):
        if not self.runtime.is_file():
            return {"state":"SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","reasons":["RUNTIME_MISSING"]}
        if os.name!="nt":
            return {"state":"SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","reasons":["WINDOWS_CONTAINMENT_NOT_AVAILABLE"]}
        try:
            data=(self.directory/"readiness.json").read_bytes()
            if hashlib.sha256(data).hexdigest()!=(self.directory/"readiness.sha256").read_text(encoding="ascii").strip():
                raise ValueError("Readiness receipt hash differs")
            receipt=json.loads(data)
            if not isinstance(receipt,dict): raise ValueError("Readiness receipt must be an object")
            result=check_readiness(receipt,root=self.root,runtime=self.runtime)
            for name,digest in receipt.get("runtime_files",{}).items():
                path=Path(name)
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                    result={"state":"SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","reasons":["BROWSER_DEPENDENCY_CHANGED"]}
                    break
            if not receipt.get("runtime_files"):
                result={"state":"SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","reasons":["BROWSER_DEPENDENCY_PROOF_MISSING"]}
            for name,digest in receipt.get("proof_artifacts",{}).items():
                path=(self.directory/name).resolve()
                if not path.is_relative_to(self.directory.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                    result={"state":"SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","reasons":["READINESS_PROOF_CHANGED"]}
                    break
            if not receipt.get("proof_artifacts"):
                result={"state":"SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","reasons":["READINESS_PROOF_MISSING"]}
            return result
        except (OSError,ValueError,TypeError,KeyError) as exc:
            return {"state":"SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE","reasons":["READINESS_RECEIPT_INVALID",str(exc)]}

    def for_action(self, action):
        used=False
        def call(response,reason):
            nonlocal used
            if used:
                raise DiscoveryError("DYNAMIC_POLICY_REJECTED","One dynamic invocation per action")
            used=True
            return self.extract(response,reason,lineage={"action_id":action.get("action_id"),
                "parent_action_id":action.get("origin_action_id") or action.get("parent_action_id"),
                "parent_observation_id":action.get("originating_observation_id"),
                "job_id":action.get("job_id"),"required_action_id":action.get("required_action_id"),
                "extraction_route":"DYNAMIC"})
        return call

    def __call__(self,response,reason):
        return self.extract(response,reason)

    def extract(self,response,reason,*,lineage=None):
        self.last_receipt=None
        try:
            value=self._extract(response,reason,lineage=lineage)
        except (DiscoveryError,BrowserFailure) as exc:
            if self.last_receipt:
                path=Path(self.last_receipt["capture"])/"evaluation.json"
                path.write_text(json.dumps({"status":"FAIL","code":exc.code,"detail":str(exc)}),encoding="utf-8")
            if isinstance(exc,BrowserFailure): raise DiscoveryError(exc.code,exc.detail) from exc
            raise
        if self.last_receipt:
            path=Path(self.last_receipt["capture"])/"evaluation.json"
            path.write_text(json.dumps({"status":"PASS","extraction_status":"EXTRACTED_NOT_VERIFIED"}),encoding="utf-8")
        return value

    def _extract(self,response,reason,*,lineage=None):
        safe_url(response.url)
        if not self.diagnostic and self.readiness()["state"]!="DYNAMIC_ADAPTER_READY":
            raise DiscoveryError("SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE",json.dumps(self.readiness()))
        if not self.runtime.is_file():
            raise DiscoveryError("DYNAMIC_BACKEND_UNAVAILABLE","Isolated runtime executable absent")
        capture=self.directory/"attempts"/str(uuid4())
        capture.mkdir(parents=True)
        (capture/"implementation.json").write_text(json.dumps(implementation_identity(self.root),indent=2),encoding="utf-8")
        lock=RunLock(self.directory/"dynamic-job.lock","UTC",alive=process_alive if os.name=="nt" else posix_process_alive)
        request={"schema_version":1,"operation":("offline_probe" if self.diagnostic=="offline" else "probe" if self.diagnostic else "acquire"),
                 "url":response.url,"navigation_ms":LIMITS["navigation_ms"],
                 "workspace":None,"lineage":lineage or {}}
        try:
            with lock:
                with tempfile.TemporaryDirectory(prefix="dragon-browser-") as temporary:
                    workspace=Path(temporary)
                    request["workspace"]=str(workspace)
                    (capture/"request.json").write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding="utf-8")
                    value=self.runner(self.runtime,self.root/"dragon/browser_worker.py",request,workspace=workspace)
                value.setdefault("host",{})["temporary_directory_removed"]=not workspace.exists()
        except DuplicateRunError as exc:
            value={"schema_version":1,"status":"FAIL","code":"DYNAMIC_CONCURRENCY_LIMIT","detail":str(exc)}
        except (OSError,BrowserFailure) as exc:
            value={"schema_version":1,"status":"FAIL","code":getattr(exc,"code","DYNAMIC_BACKEND_UNAVAILABLE"),"detail":str(exc)}
        (capture/"response.json").write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
        self.last_receipt={"capture":str(capture),"response":value}
        if value.get("status")!="PASS":
            raise DiscoveryError(value.get("code","DYNAMIC_BACKEND_READINESS_FAILURE"),value.get("detail","Unknown browser failure"))
        if (not isinstance(value.get("text"),str) or len(value["text"].strip())<200
                or not isinstance(value.get("dynamic_provenance"),dict)):
            raise DiscoveryError("DYNAMIC_NORMALIZATION_FAILURE","Incomplete structured extraction")
        provenance=value["dynamic_provenance"]
        try:
            if self.diagnostic=="offline":
                if provenance.get("navigation_mode")!="FIXED_LOOPBACK_JS_FIXTURE_NOT_RESEARCH":
                    raise BrowserFailure("DYNAMIC_POLICY_REJECTED","Uncontrolled offline fixture")
            else:
                final=safe_url(value["url"])
                if final["host"]!=safe_url(response.url)["host"]:
                    raise BrowserFailure("DYNAMIC_POLICY_REJECTED","Response changed target host")
            timestamp=datetime.fromisoformat(provenance["retrieved_at"])
            if timestamp.tzinfo is None or not isinstance(provenance["http_status"],int):
                raise ValueError("Missing aware timestamp/navigation status")
        except BrowserFailure as exc:
            raise DiscoveryError(exc.code,exc.detail) from exc
        except (KeyError,TypeError,ValueError) as exc:
            raise DiscoveryError("DYNAMIC_NORMALIZATION_FAILURE",str(exc)) from exc
        if (provenance.get("extracted_text_sha256")!=hashlib.sha256(value["text"].strip().encode()).hexdigest()
                or provenance.get("requested_url")!=response.url
                or provenance.get("ignore_https_errors") is not False
                or provenance.get("sandbox_verified") is not True):
            raise DiscoveryError("DYNAMIC_NORMALIZATION_FAILURE","Extraction hash or security provenance differs")
        try:
            assert_launch_policy({"chromium_sandbox":True,"args":provenance.get("effective_arguments",[])})
        except BrowserFailure as exc:
            raise DiscoveryError(exc.code,exc.detail) from exc
        if not value.get("host",{}).get("temporary_directory_removed"):
            raise DiscoveryError("DYNAMIC_CLEANUP_FAILURE","Temporary workspace remains")
        value["dynamic_provenance"]["host"]=value["host"]
        value["dynamic_provenance"]["operational_diagnostic"]=self.diagnostic
        return value


def dynamic_extractor_from_config(root,*,diagnostic=False):
    """Explicit local binding; no browser package import or service in the host."""
    from dragon.discovery import load_extraction_adapter_config
    if not (root/"config/extraction-adapters.yaml").is_file(): return None
    settings=load_extraction_adapter_config(root/"config/extraction-adapters.yaml")
    entry=next((item for item in settings["fallbacks"] if item["adapter_id"]=="crawl4ai-optional"),None)
    if entry is None: return None
    directory=local_browser_directory(root)
    try:
        local=json.loads((directory/"runtime.json").read_text(encoding="utf-8"))
        if set(local) not in ({"python_executable"},{"python_executable","enabled"}) or not Path(local["python_executable"]).is_absolute():
            raise ValueError("Runtime binding must contain an absolute Python executable")
        if "enabled" in local and type(local["enabled"]) is not bool:
            raise ValueError("Local enabled flag must be boolean")
    except (OSError,ValueError,TypeError) as exc:
        if not diagnostic and not entry["enabled"]: return None
        raise DiscoveryError("SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE",str(exc)) from exc
    if not diagnostic and not (entry["enabled"] or local.get("enabled") is True): return None
    extractor=DynamicBrowserExtractor(root=root,runtime=Path(local["python_executable"]),directory=directory,diagnostic=diagnostic)
    if not diagnostic and extractor.readiness()["state"]!="DYNAMIC_ADAPTER_READY":
        raise DiscoveryError("SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE",json.dumps(extractor.readiness()))
    return extractor
