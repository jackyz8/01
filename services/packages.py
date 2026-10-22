import re, subprocess
from config import Config
from services import sandbox
from services.process_manager import _ensure_venv

PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*(\[[A-Za-z0-9,._\-]+\])?((==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!_\-]+)?$")

class PackageManager:
    def __init__(self):
        self.busy = set()

    def install(self, p, args: list[str]) -> tuple[int, str]:
        if p.id in self.busy: return 1, "Another pip operation is running."
        self.busy.add(p.id)
        try:
            ok, msg = _ensure_venv(p)
            if not ok: return 1, "venv: " + msg
            cmd, env, cname = sandbox.build_pip(p, args)
            try:
                r = subprocess.run(cmd, cwd=str(sandbox.project_src(p)), env=env,
                                   capture_output=True, text=True, timeout=Config.PIP_TIMEOUT)
                out = (r.stdout or "") + (r.stderr or "")
                return r.returncode, out[-8000:]
            except subprocess.TimeoutExpired:
                if cname:
                    subprocess.run([Config.DOCKER_BIN,"kill",cname], capture_output=True)
                return 124, "Timeout"
        finally:
            self.busy.discard(p.id)

    @staticmethod
    def parse(text: str, expected: str):
        toks = [t for t in re.split(r"[\s,]+", text.strip()) if t]
        if toks and toks[0].lower() == "pip": toks.pop(0)
        if toks and toks[0].lower() in ("install","uninstall"):
            sub = toks.pop(0).lower()
            if sub != expected: raise ValueError(f"Use only names (typed 'pip {sub}').")
        pkgs = []
        for t in toks:
            if t.startswith("-"): raise ValueError(f"Option '{t}' not allowed.")
            if not PKG_RE.match(t) or len(t) > 100:
                raise ValueError(f"Invalid package spec: {t[:60]}")
            pkgs.append(t)
        if not pkgs: raise ValueError("No packages.")
        if len(pkgs) > 25: raise ValueError("Max 25 packages.")
        return pkgs

PKG = PackageManager()