async function refreshStats(){
  try{
    const s = await api("/api/dashboard/stats");
    document.getElementById("kpi-total").textContent   = s.projects.total;
    document.getElementById("kpi-running").textContent = s.projects.running;
    document.getElementById("kpi-stopped").textContent = s.projects.stopped;
    document.getElementById("kpi-crashed").textContent = s.projects.crashed;
    const h = s.host;
    document.getElementById("host-cpu").textContent  = h.cpu_percent.toFixed(1)+"%";
    document.getElementById("host-ram").textContent  = ((h.ram_used/1048576)|0)+" / "+((h.ram_total/1048576)|0)+" MB";
    document.getElementById("host-disk").textContent = ((h.disk_used/1073741824).toFixed(1))+" / "+((h.disk_total/1073741824).toFixed(1))+" GB";
  }catch(e){ /* ignore transient */ }
}

async function refreshProjects(){
  try{
    const projs = await api("/api/projects");
    const el = document.getElementById("projects-list");
    if(!projs.length){ el.innerHTML = "<p class='muted'>No projects yet.</p>"; return; }
    el.innerHTML = projs.map(p => `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div><b>${p.name}</b> <span class="muted">#${p.id}</span></div>
          <span class="status-${p.status}">${p.status.toUpperCase()}</span>
        </div>
        <p class="muted">${p.startup||"—"} · uptime ${Math.round(p.uptime)}s</p>
        <div>
          <a class="btn secondary" href="/projects/${p.id}">Open</a>
          <button class="secondary" onclick="lifecycle(${p.id},'start')">▶ Start</button>
          <button class="secondary" onclick="lifecycle(${p.id},'stop')">⏹ Stop</button>
          <button class="secondary" onclick="lifecycle(${p.id},'restart')">🔄 Restart</button>
          <button class="danger" onclick="delProj(${p.id})">🗑 Delete</button>
        </div>
      </div>`).join("");
  }catch(e){ console.error(e); }
}

async function lifecycle(id, op){
  try{
    const r = await api(`/api/projects/${id}/${op}`, {method:"POST"});
    toast(r.message || op+" ok");
  }catch(e){ toast(e.message, true); }
  refreshProjects(); refreshStats();
}

async function delProj(id){
  if(!confirm("Delete project #"+id+"? A backup will be kept on server.")) return;
  try{ await api("/api/projects/"+id, {method:"DELETE"}); toast("Deleted"); refreshProjects(); refreshStats(); }
  catch(e){ toast(e.message,true); }
}

document.getElementById("create-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  const name = document.getElementById("p-name").value.trim();
  const auto = document.getElementById("p-auto").checked;
  try{
    await api("/api/projects", {method:"POST", body:JSON.stringify({name, auto_restart:auto})});
    document.getElementById("create-form").reset();
    toast("Project created. Upload a ZIP to begin.");
    refreshProjects(); refreshStats();
  }catch(e){ toast(e.message,true); }
});

refreshStats(); refreshProjects();
setInterval(refreshStats, 5000);
setInterval(refreshProjects, 8000);