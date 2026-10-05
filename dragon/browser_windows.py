"""Windows containment and token inspection for the optional browser worker.

No browser dependency is imported in the production Python runtime.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import os
import time
from uuid import uuid4


def _api():
    if os.name != "nt":
        raise OSError("WINDOWS_BROWSER_CONTAINMENT_REQUIRED")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    kernel.IsProcessInJob.argtypes = [w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)]
    kernel.OpenJobObjectW.argtypes=[w.DWORD,w.BOOL,w.LPCWSTR]
    kernel.OpenJobObjectW.restype=w.HANDLE
    kernel.GetCurrentProcess.restype=w.HANDLE
    return kernel


def _check(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


class BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", w.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_limit", w.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]


class IOCounts(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IOCounts),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]


class CPUControl(ctypes.Structure):
    _fields_ = [("flags", w.DWORD), ("rate", w.DWORD)]


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in ("user", "kernel", "period_user", "period_kernel")] + [
        ("faults", w.DWORD), ("total_processes", w.DWORD), ("active", w.DWORD), ("terminated", w.DWORD)]


class ThreadEntry(ctypes.Structure):
    _fields_=[("size",w.DWORD),("usage",w.DWORD),("thread_id",w.DWORD),("owner_pid",w.DWORD),
              ("base_priority",w.LONG),("delta_priority",w.LONG),("flags",w.DWORD)]


class WindowsJob:
    """Job-wide commit/process/CPU limits, descendant ownership and kill-on-close."""

    def __init__(self, *, memory_bytes=2_147_483_648, processes=32, cpu_percent=50):
        self.api = _api()
        self.name="Local\\DRAGON_BROWSER_"+uuid4().hex
        self.handle = _check(self.api.CreateJobObjectW(None, self.name))
        self.closed = False
        try:
            limits = ExtendedLimits()
            # ACTIVE_PROCESS, JOB_MEMORY, KILL_ON_JOB_CLOSE. No breakaway flags.
            limits.basic.flags = 0x8 | 0x200 | 0x2000
            limits.basic.active_limit = processes
            limits.job_memory = memory_bytes
            _check(self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            cpu = CPUControl(0x1 | 0x4, cpu_percent * 100)  # ENABLE | HARD_CAP
            _check(self.api.SetInformationJobObject(self.handle, 15, ctypes.byref(cpu), ctypes.sizeof(cpu)))
            effective = ExtendedLimits()
            effective_cpu = CPUControl()
            _check(self.api.QueryInformationJobObject(self.handle, 9, ctypes.byref(effective), ctypes.sizeof(effective), None))
            _check(self.api.QueryInformationJobObject(self.handle, 15, ctypes.byref(effective_cpu), ctypes.sizeof(effective_cpu), None))
            if (effective.basic.flags != limits.basic.flags or effective.job_memory != memory_bytes
                    or effective.basic.active_limit != processes or effective_cpu.flags != 5
                    or effective_cpu.rate != cpu_percent * 100):
                raise OSError("WINDOWS_JOB_LIMIT_READBACK_FAILED")
            self.limits = {"memory_bytes": memory_bytes, "active_processes": processes,
                           "cpu_percent": cpu_percent, "kill_on_close": True, "breakaway": False}
        except Exception:
            self.close()
            raise

    def assign(self, process):
        # Worker cannot import/launch Crawl4AI until the parent sends its request.
        _check(self.api.AssignProcessToJobObject(self.handle, int(process._handle)))

    def resume(self,pid):
        # Popen closes the initial thread handle; reopen only the owned suspended process's thread.
        self.api.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD]
        self.api.CreateToolhelp32Snapshot.restype=w.HANDLE
        self.api.Thread32First.argtypes=[w.HANDLE,ctypes.POINTER(ThreadEntry)]
        self.api.Thread32Next.argtypes=[w.HANDLE,ctypes.POINTER(ThreadEntry)]
        self.api.OpenThread.argtypes=[w.DWORD,w.BOOL,w.DWORD]
        self.api.OpenThread.restype=w.HANDLE
        self.api.ResumeThread.argtypes=[w.HANDLE]
        self.api.ResumeThread.restype=w.DWORD
        snapshot=self.api.CreateToolhelp32Snapshot(0x4,0)
        if snapshot==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry=ThreadEntry(); entry.size=ctypes.sizeof(entry)
            valid=self.api.Thread32First(snapshot,ctypes.byref(entry))
            while valid:
                if entry.owner_pid==pid:
                    thread=_check(self.api.OpenThread(0x2,False,entry.thread_id))
                    try:
                        if self.api.ResumeThread(thread)==0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                        return
                    finally:
                        self.api.CloseHandle(thread)
                valid=self.api.Thread32Next(snapshot,ctypes.byref(entry))
            raise OSError("SUSPENDED_WORKER_THREAD_NOT_FOUND")
        finally:
            self.api.CloseHandle(snapshot)

    def accounting(self):
        data = Accounting()
        _check(self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(data), ctypes.sizeof(data), None))
        return {"active_processes": data.active, "total_processes": data.total_processes,
                "terminated_processes": data.terminated, "user_100ns": data.user, "kernel_100ns": data.kernel}

    def contains(self,pid):
        process=_check(self.api.OpenProcess(0x1000,False,int(pid)))
        try:
            member=w.BOOL()
            _check(self.api.IsProcessInJob(process,self.handle,ctypes.byref(member)))
            return bool(member.value)
        finally:
            self.api.CloseHandle(process)

    def cleanup(self):
        before = self.accounting()
        _check(self.api.TerminateJobObject(self.handle, 1))
        deadline = time.monotonic() + 3
        after = self.accounting()
        while after["active_processes"] and time.monotonic() < deadline:
            time.sleep(0.02)
            after = self.accounting()
        return {"before": before, "after": after, "verified": after["active_processes"] == 0}

    def close(self):
        if not self.closed:
            self.api.CloseHandle(self.handle)
            self.closed = True


def token_security(pid: int) -> dict:
    """Read actual renderer-token integrity/restrictions; errors never become PASS."""
    kernel = _api()
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    adv.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    adv.IsTokenRestricted.argtypes = [w.HANDLE]
    adv.IsTokenRestricted.restype = w.BOOL
    adv.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    adv.GetSidSubAuthority.argtypes = [ctypes.c_void_p, w.DWORD]
    adv.GetSidSubAuthority.restype = ctypes.POINTER(w.DWORD)
    process = _check(kernel.OpenProcess(0x1000, False, pid))  # QUERY_LIMITED_INFORMATION
    token = w.HANDLE()
    try:
        _check(adv.OpenProcessToken(process, 0x8, ctypes.byref(token)))
        needed = w.DWORD()
        adv.GetTokenInformation(token, 25, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        _check(adv.GetTokenInformation(token, 25, buffer, needed, ctypes.byref(needed)))
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
        count = adv.GetSidSubAuthorityCount(sid).contents.value
        integrity = adv.GetSidSubAuthority(sid, count - 1).contents.value
        container = w.DWORD()
        _check(adv.GetTokenInformation(token, 29, ctypes.byref(container), ctypes.sizeof(container), ctypes.byref(needed)))
        restricted = bool(adv.IsTokenRestricted(token))
        return {"pid": pid, "integrity_rid": integrity, "restricted_token": restricted,
                "app_container": bool(container.value),
                "sandbox_verified": integrity <= 4096 and (restricted or bool(container.value))}
    finally:
        if token.value:
            kernel.CloseHandle(token)
        kernel.CloseHandle(process)


def process_alive(pid: int) -> bool:
    # os.kill(pid, 0) sends a console control event on Windows; never use it.
    kernel = _api()
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 5  # inaccessible owner is treated as alive
    try:
        kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        code = w.DWORD()
        _check(kernel.GetExitCodeProcess(handle, ctypes.byref(code)))
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def join_parent_job(name):
    """Store Python launchers may activate the real interpreter outside inheritance.

    The trusted worker assigns only itself before importing any browser package.
    It immediately closes the query handle, preserving parent kill-on-close.
    """
    if not name or not name.startswith("Local\\DRAGON_BROWSER_"):
        raise OSError("PARENT_BROWSER_JOB_MISSING")
    kernel=_api()
    job=_check(kernel.OpenJobObjectW(0x1|0x4,False,name))  # ASSIGN_PROCESS | QUERY
    try:
        current=kernel.GetCurrentProcess()
        member=w.BOOL()
        _check(kernel.IsProcessInJob(current,job,ctypes.byref(member)))
        if not member.value:
            _check(kernel.AssignProcessToJobObject(job,current))
        _check(kernel.IsProcessInJob(current,job,ctypes.byref(member)))
        if not member.value: raise OSError("WORKER_NOT_IN_PARENT_JOB")
        return {"pid":os.getpid(),"verified":True}
    finally:
        kernel.CloseHandle(job)
