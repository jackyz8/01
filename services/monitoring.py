import subprocess, time, psutil, shutil
from config import Config
from services import sandbox

def host_stats():
    vm = psutil.virtual_memory()
    du = shutil.disk_usage(Config.DATA_DIR)
    try: load = os.getloadavg()
    except OSError: load = (0,0,0)
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_count": psutil.cpu_count(),
        "ram_total": vm.total, "ram_used": vm.used, "ram_percent": vm.percent,
        "disk_total": du.total, "disk_used": du.used,
        "disk_percent": du.used * 100 / du.total,
        "load": load,
        "uptime": time.time() - psutil.boot_time(),
    }

def project_usage(p):
    if Config.SANDBOX_MODE == "docker" and p.container:
        r = subprocess.run([Config.DOCKER_BIN,"stats","--no-stream","--format",
                            "{{.CPUPerc}}|{{.MemUsage}}", p.container],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and "|" in r.stdout:
            cpu, mem = r.stdout.strip().splitlines()[-1].split("|", 1)
            return {"cpu": cpu, "mem": mem.split("/")[0].strip()}
        return {"cpu":"?","mem":"?"}
    if not p.pid: return {"cpu":"?","mem":"?"}
    try:
        root = psutil.Process(p.pid)
        procs = [root] + root.children(recursive=True)
        for pr in procs:
            try: pr.cpu_percent(None)
            except psutil.Error: pass
        time.sleep(0.3)
        cpu = rss = 0
        for pr in procs:
            try:
                cpu += pr.cpu_percent(None); rss += pr.memory_info().rss
            except psutil.Error: pass
        return {"cpu": f"{cpu:.1f}%", "mem": f"{rss/1048576:.1f} MB"}
    except psutil.Error:
        return {"cpu":"?","mem":"?"}