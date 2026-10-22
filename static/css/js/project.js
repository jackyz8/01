const pid = window.PROJECT_ID;
const $ = id => document.getElementById(id);
let es = null;

async function load(){
  try{
    const p = await api(`/api/projects/${pid}`);
    $("p-name").textContent = p.name;
    $("p-status").textContent = p.status;
    $("p-status").className = "status-"+p.status;
    $("p-startup").textContent = p.startup || "not set";
    $("p-uptime").textContent = Math.round(p.uptime)+"s";
    $("p-cpu").textContent = p.usage.cpu;
    $("p-mem").textContent = p.usage.mem;
    $("p-lasterr").textContent = p.last_error || "—";
    $("startup-select").innerHTML = (p.files||[]).filter(f=>f.endsWith(".py"))
      .map(f => `<option ${f===p.startup?"selected":""}>${f}</option>`).join("")
      || "<option disabled>No .py files</option>";
    $("req-exists").textContent = p.requirements ? "✅ requirements.txt found" : "❌ not present";
  }catch(e){ toast(e.message, true); }
}

["start","stop","restart"].forEach(op=>{
  $("btn-"+op).addEventListener("click", async () => {
    try{ const r = await api(`/api/projects/${pid}/${op}`, {method:"POST"});
         toast(r.message || op); }
    catch(e){ toast(e.message,true); }
    load();
  });
});

$("btn-delete").addEventListener("click", async ()=>{
  if(!confirm("Delete this project? A backup is kept on server.")) return;
  try{ await api(`/api/projects/${pid}`, {method:"DELETE"}); location.href="/dashboard"; }
  catch(e){ toast(e.message,true); }
});

// ---------- upload ----------
$("upload-form").addEventListener("submit", ev => {
  ev.preventDefault();
  const f = $("upload-input").files[0];
  if(!f) return;
  const fd = new FormData(); fd.append("file", f);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/api/projects/${pid}/upload`);
  xhr.setRequestHeader("X-Requested-With","XMLHttpRequest");
  const bar = $("upload-progress");
  bar.style.display = "block"; bar.value = 0;
  xhr.upload.onprogress = e => { bar.value = e.total ? (e.loaded/e.total)*100 : 0; };
  xhr.onload = () => {
    bar.style.display = "none";
    let data = {}; try{ data = JSON.parse(xhr.responseText); }catch{}
    if(xhr.status >= 200 && xhr.status < 300){
      toast(`Uploaded. startup: ${data.startup || "not detected"}`);
      load();
    }else toast(data.error || "Upload failed", true);
  };
  xhr.onerror = () => toast("Upload network error", true);
  xhr.send(fd);
});

// ---------- logs (SSE) ----------
$("btn-logs").addEventListener("click", () => {
  if(es) es.close();
  $("logs").textContent = "";
  es = new EventSource(`/api/projects/${pid}/logs/stream`);
  es.onmessage = e => {
    const d = JSON.parse(e.data);
    if(d.lines){ $("logs").textContent += d.lines + "\n";
                 $("logs").scrollTop = $("logs").scrollHeight; }
  };
  es.addEventListener("end", () => { es.close(); es=null; load(); });
});

$("btn-download-logs").onclick = () => location.href = `/api/projects/${pid}/logs/download`;
$("btn-clear-logs").onclick = () => $("logs").textContent = "";

// ---------- console input ----------
$("console-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  const t = $("console-input").value; if(!t) return;
  try{
    const r = await api(`/api/projects/${pid}/console/input`,
                        {method:"POST", body:JSON.stringify({text:t})});
    toast(r.message); $("console-input").value = "";
  }catch(e){ toast(e.message,true); }
});

// ---------- startup / settings ----------
$("save-settings").onclick = async () => {
  try{
    await api(`/api/projects/${pid}`, {method:"PATCH", body: JSON.stringify({
      startup: $("startup-select").value || null,
      args: $("args-input").value,
      auto_restart: $("auto-restart").checked,
      restart_every_h: parseInt($("sched").value)||0,
    })});
    toast("Saved"); load();
  }catch(e){ toast(e.message,true); }
};

// ---------- packages ----------
async function runPkg(op, pkgs){
  try{
    const r = await api(`/api/projects/${pid}/packages/install`,
                        {method:"POST", body:JSON.stringify({op, packages: pkgs})});
    $("pip-output").textContent = r.output;
    toast(r.ok?"pip OK":"pip failed", !r.ok);
    refreshInstalled();
  }catch(e){ toast(e.message,true); }
}
$("btn-pip-install").onclick  = () => runPkg("install", $("pip-input").value);
$("btn-pip-upgrade").onclick  = () => runPkg("upgrade", $("pip-input").value);
$("btn-pip-uninstall").onclick= () => runPkg("uninstall", $("pip-input").value);
$("btn-pip-requirements").onclick = () => runPkg("install", "requirements");
async function refreshInstalled(){
  try{
    const r = await api(`/api/projects/${pid}/packages`);
    $("pip-installed").innerHTML = r.packages.map(p=>`<li>${p.name} ${p.version}</li>`).join("");
  }catch(e){ /*ignore*/ }
}

// ---------- env vars ----------
async function refreshEnv(){
  try{
    const list = await api(`/api/projects/${pid}/env`);
    $("env-list").innerHTML = list.map(v =>
      `<li><code>${v.key}</code> = ••••• <button class="danger"
       onclick="delEnv('${v.key}')">Delete</button></li>`).join("") || "<li class='muted'>None</li>";
  }catch(e){}
}
window.delEnv = async key => {
  try{ await api(`/api/projects/${pid}/env/${encodeURIComponent(key)}`, {method:"DELETE"}); refreshEnv(); }
  catch(e){ toast(e.message,true); }
};
$("env-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  const key = $("env-key").value.trim(), value = $("env-value").value;
  try{ await api(`/api/projects/${pid}/env`, {method:"POST", body:JSON.stringify({key,value})});
       $("env-form").reset(); refreshEnv(); toast("Saved"); }
  catch(e){ toast(e.message,true); }
});

// ---------- backups ----------
async function refreshBackups(){
  try{
    const list = await api(`/api/projects/${pid}/backups`);
    $("backups").innerHTML = list.map(b => `
      <li>
        ${new Date(b.created_at*1000).toLocaleString()} — ${(b.size/1048576).toFixed(2)} MB
        <a class="btn secondary" href="/api/projects/${pid}/backups/${b.id}/download">⬇</a>
        <button class="secondary" onclick="restoreBk(${b.id})">↩ Restore</button>
      </li>`).join("") || "<li class='muted'>No backups yet</li>";
  }catch(e){}
}
window.restoreBk = async bid => {
  if(!confirm("Replace current files with this backup? A new backup of current state will be taken first.")) return;
  try{ await api(`/api/projects/${pid}/backups/${bid}/restore`, {method:"POST"});
       toast("Restored"); load(); refreshBackups(); }
  catch(e){ toast(e.message,true); }
};
$("btn-backup-now").onclick = async () => {
  try{ await api(`/api/projects/${pid}/backups`, {method:"POST"}); refreshBackups(); toast("Backup created"); }
  catch(e){ toast(e.message,true); }
};

// ---------- files (simple explorer) ----------
let fmPath = "";
async function fmLoad(path=""){
  fmPath = path;
  try{
    const d = await api(`/api/projects/${pid}/files?path=${encodeURIComponent(path)}`);
    $("fm-path").textContent = "/"+path;
    $("fm-list").innerHTML = d.items.map(it => `
      <li>
        ${it.dir ? "📁" : "📄"}
        <a href="#" onclick="fmOpen('${escape(it.name)}',${it.dir});return false">${it.name}</a>
        <span class="muted">${it.dir?"":(it.size+" B")}</span>
        <button class="secondary" onclick="fmDownload('${escape(it.name)}')">⬇</button>
        <button class="danger" onclick="fmDel('${escape(it.name)}')">🗑</button>
      </li>`).join("");
  }catch(e){ toast(e.message,true); }
}
function escape(s){ return s.replace(/'/g,"\\'").replace(/</g,"&lt;"); }
window.fmOpen = async (name, isDir) => {
  if(isDir){ fmLoad((fmPath? fmPath+"/" : "")+name); return; }
  try{
    const p = (fmPath? fmPath+"/" : "")+name;
    const r = await api(`/api/projects/${pid}/files/read?path=${encodeURIComponent(p)}`);
    $("fm-editor").style.display = "block";
    $("fm-editor-path").textContent = p;
    $("fm-editor-text").value = r.content;
    $("fm-editor-save").onclick = async () => {
      try{ await api(`/api/projects/${pid}/files/write`, {method:"PUT",
              body:JSON.stringify({path:p, content:$("fm-editor-text").value})});
           toast("Saved"); }
      catch(e){ toast(e.message,true); }
    };
  }catch(e){ toast(e.message,true); }
};
window.fmDownload = name =>
  location.href = `/api/projects/${pid}/files/download?path=${encodeURIComponent((fmPath? fmPath+"/" : "")+name)}`;
window.fmDel = async name => {
  if(!confirm("Delete "+name+"?")) return;
  try{ await api(`/api/projects/${pid}/files?path=${encodeURIComponent((fmPath? fmPath+"/" : "")+name)}`,
                 {method:"DELETE"}); fmLoad(fmPath); }
  catch(e){ toast(e.message,true); }
};
$("fm-upload-form").addEventListener("submit", ev => {
  ev.preventDefault();
  const f = $("fm-upload-input").files[0]; if(!f) return;
  const fd = new FormData(); fd.append("file", f); fd.append("path", fmPath);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/api/projects/${pid}/files/upload`);
  xhr.setRequestHeader("X-Requested-With","XMLHttpRequest");
  xhr.onload = () => { if(xhr.status<300){ fmLoad(fmPath); toast("Uploaded"); }
                       else toast("Upload failed", true); };
  xhr.send(fd);
});

// ---------- init ----------
load(); refreshInstalled(); refreshEnv(); refreshBackups(); fmLoad("");
setInterval(load, 5000);