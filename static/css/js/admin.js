async function load(){
  const users = await api("/api/admin/users");
  document.querySelector("#users-table tbody").innerHTML = users.map(u => `
    <tr>
      <td>${u.id}</td><td>${u.email}</td>
      <td><input type="checkbox" ${u.is_admin?"checked":""} onchange="upd(${u.id},{is_admin:this.checked})"></td>
      <td><input type="checkbox" ${u.is_approved?"checked":""} onchange="upd(${u.id},{is_approved:this.checked})"></td>
      <td><input type="checkbox" ${u.is_banned?"checked":""} onchange="upd(${u.id},{is_banned:this.checked})"></td>
      <td><input type="number" value="${u.max_projects??""}" style="width:70px"
            onchange="upd(${u.id},{max_projects:this.value?parseInt(this.value):null})"></td>
      <td><button class="danger" onclick="upd(${u.id},{is_banned:true})">Ban</button></td>
    </tr>`).join("");
  const projs = await api("/api/admin/projects");
  document.getElementById("all-projects").innerHTML = projs.map(p =>
    `<li>#${p.id} · user ${p.owner_id} · ${p.name} · ${p.status}
      <button class="danger" onclick="kill(${p.id})">Kill</button></li>`).join("");
  const audit = await api("/api/admin/audit");
  document.getElementById("audit").innerHTML = audit.map(a =>
    `<li>${new Date(a.created_at*1000).toLocaleString()} · user ${a.user_id||"-"} · ${a.action} · ${a.detail||""}</li>`).join("");
}
window.upd = async (id, patch) => {
  await api("/api/admin/users/"+id, {method:"PATCH", body:JSON.stringify(patch)});
  load();
};
window.kill = async id => { await api(`/api/admin/projects/${id}/kill`, {method:"POST"}); load(); };
load();