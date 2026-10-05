"""One JSON request / one JSON response. Run only in the pinned isolated runtime."""
from __future__ import annotations
import asyncio
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import traceback

# -I strips script-directory imports; only this trusted sibling directory is added.
sys.path.insert(0,str(Path(__file__).resolve().parent))
from browser_protocol import (BACKEND_VERSION,PLAYWRIGHT_VERSION,LIMITS,BrowserFailure,
                              assert_launch_policy,canonical_hash,safe_url,classify_error,write_json_atomic)
from browser_windows import token_security,join_parent_job

def now(): return datetime.now(timezone.utc).isoformat()


def _tls_fixture(directory):
    """Throwaway self-signed localhost certificate, reachable only inside a probe."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from datetime import timedelta
    from http.server import HTTPServer,BaseHTTPRequestHandler
    import ssl, threading
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"localhost")])
    cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
          .public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=1))
          .not_valid_after(datetime.now(timezone.utc)+timedelta(hours=1))
          .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]),critical=False)
          .sign(key,hashes.SHA256()))
    certfile, keyfile=directory/"fixture-cert.pem",directory/"fixture-key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"UNTRUSTED TLS FIXTURE MUST NOT BE ACCEPTED")
        def log_message(self,*_): pass
    server=HTTPServer(("127.0.0.1",0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile,keyfile)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    return server,thread,f"https://127.0.0.1:{server.server_port}/"


def _javascript_fixture():
    from http.server import HTTPServer,BaseHTTPRequestHandler
    import threading
    text="اختبار تقني محلي خارج البحث ولا يمثل حدثا أو دليلا صحفيا. "*30
    body=("<html><head><title>DRAGON isolated fixture</title></head><body><article id='probe'></article><script>document.getElementById('probe').textContent="+json.dumps(text)+";</script></body></html>").encode()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self,*_): pass
    server=HTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    return server,thread,f"http://127.0.0.1:{server.server_port}/"


async def acquire(request):
    if sys.version_info[:2] != (3,13) or version("crawl4ai") != BACKEND_VERSION or version("playwright") != PLAYWRIGHT_VERSION:
        raise BrowserFailure("DYNAMIC_BACKEND_UNAVAILABLE","Expected Python 3.13 / Crawl4AI 0.9.4 / Playwright 1.63.0")
    from crawl4ai import AsyncWebCrawler,BrowserConfig,CrawlerRunConfig,CacheMode
    from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
    from crawl4ai.browser_manager import BrowserManager
    from playwright.async_api import Error as PlaywrightError
    offline=request["operation"]=="offline_probe"
    target=(dict(safe_url(request["url"]),addresses=["192.0.2.1"])
            if offline else safe_url(request["url"],resolve=True))
    # Pin the sole permitted external host. Unknown external DNS is denied.
    address=target["addresses"][0]
    if ":" in address: address=f"[{address}]"
    options={"headless":True,"channel":"chromium","chromium_sandbox":True,
             "args":["--enable-automation",f"--host-resolver-rules=MAP {target['host']} {address}, MAP * ~NOTFOUND"+(" , EXCLUDE 127.0.0.1" if request["operation"] in {"probe","offline_probe"} else "")],
             "ignore_default_args":["--disable-ipc-flooding-protection"]}
    assert_launch_policy(options)
    class SecureBrowserManager(BrowserManager):
        def _build_browser_args(self):
            # Deliberately replace the pinned library's insecure defaults.
            assert_launch_policy(options)
            return dict(options)
        async def create_browser_context(self,crawlerRunConfig=None):
            context=await self.browser.new_context(ignore_https_errors=False,
                service_workers="block",accept_downloads=False,java_script_enabled=True,
                user_agent="DRAGON/5 bounded dynamic source acquisition")
            await context.route("**/*",guard)
            await context.route_web_socket("**/*",lambda socket: socket.close())
            return context

    policy_blocks=[]
    fixture_url=None
    async def guard(route):
        url=route.request.url
        if fixture_url is not None and url == fixture_url and request["operation"] in {"probe","offline_probe"}:
            await route.continue_()
            return
        try:
            assessed=safe_url(url)
            if assessed["host"] != target["host"]:
                raise BrowserFailure("DYNAMIC_POLICY_REJECTED","Cross-origin browser request denied")
            await route.continue_()
        except BrowserFailure as exc:
            if len(policy_blocks)<32:
                policy_blocks.append({"url":url[:500],"reason":exc.code})
            await route.abort("blockedbyclient")

    config=BrowserConfig(browser_type="chromium",browser_mode="dedicated",use_managed_browser=False,chrome_channel="chromium",
                         headless=True,ignore_https_errors=False,java_script_enabled=True,
                         accept_downloads=False,verbose=False)
    strategy=AsyncPlaywrightCrawlerStrategy(browser_config=config)
    strategy.browser_manager=SecureBrowserManager(browser_config=config,logger=strategy.logger)
    contexts=[]
    async def page_hook(page,context,**_):
        contexts.append(context)
        return page
    strategy.set_hook("on_page_context_created",page_hook)
    metadata={"backend":"crawl4ai-optional","backend_version":BACKEND_VERSION,
              "worker_pid":os.getpid(),"worker_parent_pid":os.getppid(),
              "playwright_version":PLAYWRIGHT_VERSION,"python_version":sys.version,
              "requested_url":request["url"],"started_at":now(),"launch_options":options,
              "ignore_https_errors":False,"dns_pin":target,
              "lineage":request.get("lineage",{}),"policy_blocks":policy_blocks}
    import crawl4ai,playwright
    runtime_paths=[Path(crawl4ai.__file__).parent/name for name in
                   ("browser_manager.py","async_configs.py","async_crawler_strategy.py")]
    runtime_paths.append(Path(playwright.__file__).parent/"driver/package/lib/coreBundle.js")
    runtime_paths.append(Path(playwright.__file__).parent/"driver/node.exe")
    runtime_paths.extend(Path(sys.executable).parent/name for name in
                         ("python.exe","python313.dll","python313.zip","python313._pth"))
    metadata["runtime_files"]={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in runtime_paths}
    crawler=AsyncWebCrawler(config=config,crawler_strategy=strategy,base_directory=request["workspace"])
    phase="launch"
    local_fixture=None
    try:
        async with crawler:
            browser=strategy.browser_manager.browser
            metadata["browser_version"]=browser.version
            session=await browser.new_browser_cdp_session()
            command=await session.send("Browser.getBrowserCommandLine")
            metadata["effective_arguments"]=command["arguments"]
            executable=Path(command["arguments"][0])
            metadata["runtime_files"][str(executable)]=hashlib.sha256(executable.read_bytes()).hexdigest()
            assert_launch_policy({"chromium_sandbox":True,"args":command["arguments"]})
            phase="navigation"
            acquisition_url=request["url"]
            if offline:
                local_fixture=_javascript_fixture()
                acquisition_url=fixture_url=local_fixture[2]
                metadata["navigation_mode"]="FIXED_LOOPBACK_JS_FIXTURE_NOT_RESEARCH"
                metadata["diagnostic_navigation_url"]=acquisition_url
            result=await crawler.arun(acquisition_url,config=CrawlerRunConfig(
                cache_mode=CacheMode.WRITE_ONLY,page_timeout=request["navigation_ms"],
                wait_until="domcontentloaded",semaphore_count=1,verbose=False,screenshot=False,pdf=False,
                session_id="dragon-single-page"))
            if not result.success:
                raise BrowserFailure(classify_error(result.error_message),str(result.error_message)[:2000])
            if result.status_code is None or not 200<=result.status_code<400:
                raise BrowserFailure("DYNAMIC_PAGE_RETRIEVAL_FAILURE",f"HTTP {result.status_code}")
            final_url=result.redirected_url or result.url
            if not offline and safe_url(final_url)["host"] != target["host"]:
                raise BrowserFailure("DYNAMIC_POLICY_REJECTED","Cross-origin final navigation")
            page=strategy.browser_manager.sessions["dragon-single-page"][1]
            js_worked=await page.evaluate("() => { document.body.dataset.dragonProbe='rendered'; return document.body.dataset.dragonProbe === 'rendered'; }")
            process_info=await session.send("SystemInfo.getProcessInfo")
            metadata["process_tree"]=process_info["processInfo"]
            workspace=Path(request["workspace"])
            write_json_atomic(workspace/"browser-processes.json",[os.getpid(),*[int(x["id"]) for x in process_info["processInfo"]]])
            acknowledgement=workspace/"containment.json"
            for _ in range(100):
                if acknowledgement.is_file(): break
                await asyncio.sleep(0.02)
            if not acknowledgement.is_file():
                raise BrowserFailure("DYNAMIC_READINESS_FAILURE","Parent containment acknowledgement missing")
            metadata["containment"]=json.loads(acknowledgement.read_text(encoding="utf-8"))
            if metadata["containment"].get("verified") is not True:
                raise BrowserFailure("DYNAMIC_READINESS_FAILURE","Browser processes are outside the parent Windows Job")
            renderers=[x for x in process_info["processInfo"] if x["type"]=="renderer"]
            tokens=[]
            for renderer in renderers:
                try: tokens.append(token_security(int(renderer["id"])))
                except OSError as exc: tokens.append({"pid":renderer["id"],"sandbox_verified":False,"error":str(exc)})
            metadata["renderer_tokens"]=tokens
            if not tokens or not all(x["sandbox_verified"] for x in tokens):
                raise BrowserFailure("DYNAMIC_READINESS_FAILURE","Actual renderer sandbox token could not be verified")
            metadata["sandbox_verified"]=True
            metadata["javascript_verified"]=js_worked
            if not js_worked:
                raise BrowserFailure("DYNAMIC_READINESS_FAILURE","Rendered-page JavaScript failed")
            if request["operation"] in {"probe","offline_probe"}:
                server,thread,fixture_url=_tls_fixture(Path(request["workspace"]))
                try:
                    fixture_page=await contexts[-1].new_page()
                    try:
                        await fixture_page.goto(fixture_url,wait_until="domcontentloaded",timeout=3000)
                    except PlaywrightError as exc:
                        metadata["tls_negative"]={"status":"PASS" if classify_error(exc)=="DYNAMIC_TLS_FAILURE" else "FAIL","error":str(exc)[:1500]}
                    else:
                        metadata["tls_negative"]={"status":"FAIL","error":"Self-signed certificate accepted"}
                    finally:
                        await fixture_page.close()
                finally:
                    server.shutdown(); server.server_close(); thread.join(timeout=1); fixture_url=None
                if metadata["tls_negative"]["status"]!="PASS":
                    raise BrowserFailure("DYNAMIC_READINESS_FAILURE","TLS negative fixture did not reject certificate")
            html=result.html or ""
            text=(result.markdown.raw_markdown if result.markdown else "").strip()
            if len(html.encode())>LIMITS["content_bytes"] or len(text.encode())>LIMITS["content_bytes"]:
                raise BrowserFailure("DYNAMIC_OUTPUT_LIMIT","Rendered/extracted content exceeds limit")
            if len(text)<200:
                raise BrowserFailure("DYNAMIC_EXTRACTION_FAILURE","Rendered text is insufficient")
            metadata.update(final_url=final_url,http_status=result.status_code,retrieved_at=now(),
                            content_sha256=hashlib.sha256(html.encode()).hexdigest(),
                            extracted_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                            extraction_status="EXTRACTED_NOT_VERIFIED",
                            redirect={"requested":request["url"],"final":final_url,"changed":final_url!=request["url"]})
            return {"schema_version":1,"status":"PASS","text":text,"title":(result.metadata or {}).get("title"),
                    "url":final_url,"rendered_html":html,"extraction_method":"crawl4ai-optional","dynamic_provenance":metadata}
    except BrowserFailure as exc:
        exc.diagnostics=metadata
        raise
    except Exception as exc:
        failure=BrowserFailure(classify_error(exc,phase=phase),str(exc)[-12000:])
        failure.diagnostics=metadata
        raise failure from exc
    finally:
        if local_fixture:
            local_fixture[0].shutdown(); local_fixture[0].server_close(); local_fixture[1].join(timeout=1)
        metadata["closed_at"]=now()


def main():
    # The native pinned runtime is already assigned while suspended. This also
    # refuses activation launchers which cannot open/join the containing Job.
    join_parent_job(os.environ.get("DRAGON_BROWSER_JOB_NAME"))
    request=json.loads(sys.stdin.buffer.read(65537))
    if set(request)!={"schema_version","operation","url","workspace","navigation_ms","lineage"} or request["schema_version"]!=1 or request["operation"] not in {"acquire","probe","offline_probe"}:
        raise BrowserFailure("DYNAMIC_POLICY_REJECTED","Unsupported worker request")
    if not 1<=request["navigation_ms"]<=LIMITS["navigation_ms"]:
        raise BrowserFailure("DYNAMIC_POLICY_REJECTED","Invalid navigation bound")
    safe_url(request["url"])
    return asyncio.run(asyncio.wait_for(acquire(request),timeout=25))

if __name__=="__main__":
    try:
        # Crawl4AI logs cannot corrupt the structured protocol stdout.
        with redirect_stdout(sys.stderr):
            response=main()
        response["response_sha256"]=canonical_hash(response)
    except BrowserFailure as exc:
        response={"schema_version":1,"status":"FAIL","code":exc.code,"detail":exc.detail}
        if hasattr(exc,"diagnostics"): response["diagnostics"]=exc.diagnostics
    except (ImportError,ModuleNotFoundError) as exc:
        response={"schema_version":1,"status":"FAIL","code":"DYNAMIC_BACKEND_UNAVAILABLE","detail":str(exc)}
    except (TimeoutError,asyncio.TimeoutError):
        response={"schema_version":1,"status":"FAIL","code":"DYNAMIC_NAVIGATION_TIMEOUT","detail":"Worker wall timeout"}
    except Exception as exc:
        response={"schema_version":1,"status":"FAIL","code":"DYNAMIC_BACKEND_READINESS_FAILURE","detail":str(exc)[:2000]}
    encoded=json.dumps(response,ensure_ascii=False).encode("utf-8")
    if len(encoded)>LIMITS["output_bytes"]:
        encoded=json.dumps({"schema_version":1,"status":"FAIL","code":"DYNAMIC_OUTPUT_LIMIT","detail":"Response size limit"}).encode()
    sys.stdout.buffer.write(encoded)
