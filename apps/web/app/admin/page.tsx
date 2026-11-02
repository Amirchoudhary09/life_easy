"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
type Tab="Overview"|"Users"|"Job sources"|"Feature flags"|"Developer";
export default function AdminPage(){
 const [user,setUser]=useState<any>(null),[tab,setTab]=useState<Tab>("Overview"),[notice,setNotice]=useState(""),[error,setError]=useState(""),[loading,setLoading]=useState(true);
 const [metrics,setMetrics]=useState<any>({}),[users,setUsers]=useState<any[]>([]),[query,setQuery]=useState(""),[sources,setSources]=useState<any[]>([]),[runs,setRuns]=useState<any[]>([]),[provider,setProvider]=useState("greenhouse"),[board,setBoard]=useState(""),[flags,setFlags]=useState<any[]>([]),[health,setHealth]=useState<any>(null),[audit,setAudit]=useState<any[]>([]);
 async function api(path:string,init:RequestInit={}){
  const headers=new Headers(init.headers||{});const csrf=document.cookie.split("; ").find(x=>x.startsWith("life_easy_csrf="))?.split("=")[1];
  if(csrf)headers.set("X-CSRF-Token",decodeURIComponent(csrf));if(init.body)headers.set("Content-Type","application/json");
  const r=await fetch(path,{...init,headers,credentials:"include"});const data=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(data.detail||"Request failed: "+r.status);return data;
 }
 async function refresh(){
  setLoading(true);setError("");
  try{
   const me=await api("/api/v1/auth/me");setUser(me.user);
   if(!["admin","developer"].includes(me.user.role))throw new Error("This account does not have admin or developer access. Access is intentionally disabled until an authorized account is configured.");
   const results=await Promise.allSettled([
    api("/api/v1/admin/overview"),api("/api/v1/admin/users"),api("/api/v1/admin/job-sources"),api("/api/v1/admin/feature-flags"),api("/api/v1/admin/health"),api("/api/v1/admin/audit")
   ]);
   if(results[0].status==="fulfilled")setMetrics(results[0].value.metrics);
   if(results[1].status==="fulfilled")setUsers(results[1].value.users||[]);
   if(results[2].status==="fulfilled"){setSources(results[2].value.sources||[]);setRuns(results[2].value.recent_runs||[]);}
   if(results[3].status==="fulfilled")setFlags(results[3].value.flags||[]);
   if(results[4].status==="fulfilled")setHealth(results[4].value);
   if(results[5].status==="fulfilled")setAudit(results[5].value.events||[]);
   const denied=results.find(x=>x.status==="rejected"&&String(x.reason).includes("Administrator access"));
   if(denied&&me.user.role!=="admin")setNotice("Developer view is read-only for user and job administration.");
  }catch(e){setError((e as Error).message);}finally{setLoading(false);}
 }
 useEffect(()=>{refresh();},[]);
 async function updateUser(id:string,kind:"role"|"status",value:string){
  try{await api("/api/v1/admin/users/"+id+"/"+kind,{method:"PATCH",body:JSON.stringify({[kind]:value})});setNotice("User "+kind+" updated.");await refresh();}
  catch(e){setError((e as Error).message);}
 }
 async function saveSource(e:React.FormEvent){
  e.preventDefault();try{await api("/api/v1/admin/job-sources",{method:"POST",body:JSON.stringify({provider,board_key:board,active:true})});setBoard("");setNotice("Public job board added.");await refresh();}catch(e){setError((e as Error).message);}
 }
 async function toggleSource(id:string,active:boolean){try{await api("/api/v1/admin/job-sources/"+id+"?active="+String(active),{method:"PATCH"});await refresh();}catch(e){setError((e as Error).message);}}
 async function removeSource(id:string){if(!confirm("Remove this public job board?"))return;try{await api("/api/v1/admin/job-sources/"+id,{method:"DELETE"});await refresh();}catch(e){setError((e as Error).message);}}
 async function toggleFlag(flag:any){try{await api("/api/v1/admin/feature-flags/"+encodeURIComponent(flag.flag_key),{method:"PUT",body:JSON.stringify({enabled:!flag.enabled,description:flag.description})});await refresh();}catch(e){setError((e as Error).message);}}
 async function addFlag(e:React.FormEvent){e.preventDefault();const key=prompt("Feature flag key (letters, numbers, - or _)");if(!key)return;try{await api("/api/v1/admin/feature-flags/"+encodeURIComponent(key),{method:"PUT",body:JSON.stringify({enabled:false,description:"Created from admin console"})});await refresh();}catch(e){setError((e as Error).message);}}
 async function ingest(){try{const r=await api("/api/v1/admin/jobs/ingest",{method:"POST"});setNotice("Ingestion finished: "+r.inserted+" new, "+r.updated+" updated.");await refresh();}catch(e){setError((e as Error).message);}}
 const admin=user?.role==="admin";
 const tabs:Tab[]=admin?["Overview","Users","Job sources","Feature flags","Developer"]:["Overview","Developer"];
 const filtered=users.filter(u=>(u.email+" "+(u.display_name||"")).toLowerCase().includes(query.toLowerCase()));
 if(loading)return <main className="admin-shell">Loading secure console…</main>;
 if(error&&!user)return <main className="admin-shell"><Link href="/dashboard">← Dashboard</Link><section className="admin-card"><h1>Console unavailable</h1><p>{error}</p><button onClick={refresh}>Try again</button></section></main>;
 if(error&&user?.role==="user")return <main className="admin-shell"><Link href="/dashboard">← Dashboard</Link><section className="admin-card"><h1>Access not enabled</h1><p>{error}</p><p>No administrator or developer credentials have been created in this build.</p></section></main>;
 return <main className="admin-shell">
  <aside className="admin-side"><Link className="admin-brand" href="/">life<span>easy</span></Link><small>CONTROL PLANE</small>{tabs.map(x=><button key={x} className={tab===x?"selected":""} onClick={()=>setTab(x)}>{x}</button>)}<div className="admin-side-bottom"><b>{user?.email}</b><small>{user?.role?.toUpperCase()} ACCESS</small><Link href="/dashboard">← Career workspace</Link></div></aside>
  <section className="admin-content"><header className="admin-top"><div><small>LIFE EASY / CONTROL PLANE</small><h1>{tab}</h1></div><button onClick={refresh}>Refresh data ↻</button></header>
   {notice&&<p className="admin-notice">{notice}</p>}{error&&<p className="admin-error">{error}</p>}
   {tab==="Overview"&&<><p className="admin-intro">Live service overview. Metrics are read from the application database; provider secrets are never displayed.</p><div className="admin-metrics">{Object.entries({ "Total users":metrics.users_total,"Active users":metrics.users_active,"New users (7d)":metrics.users_new_7d,"Indexed jobs":metrics.jobs_indexed,"Applications":metrics.applications_total,"Connected integrations":metrics.integrations_connected,"Pending approvals":metrics.approvals_pending,"Queued deliveries":metrics.deliveries_queued,"Uncertain deliveries":metrics.deliveries_uncertain}).map(([k,v])=><article key={k}><small>{k}</small><strong>{v??"—"}</strong></article>)}</div><section className="admin-card"><h2>Quick operations</h2><button onClick={ingest} disabled={!admin}>Run job ingestion</button><p>Job ingestion uses public feeds and the active Greenhouse/Lever boards configured below.</p></section></>}
   {tab==="Users"&&<><div className="admin-toolbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search name or email"/><span>{filtered.length} shown</span></div><section className="admin-card admin-table-wrap"><table className="admin-table"><thead><tr><th>User</th><th>Created</th><th>Verifications</th><th>Role</th><th>Status</th><th>Activity</th></tr></thead><tbody>{filtered.map(u=><tr key={u.id}><td><b>{u.display_name||"Unnamed"}</b><small>{u.email}</small></td><td>{new Date(u.created_at).toLocaleDateString()}</td><td>{u.email_verified?"Email ✓":"Email —"}<small>{u.phone_verified?"Phone ✓":"Phone —"}</small></td><td><select value={u.role} onChange={e=>updateUser(u.id,"role",e.target.value)}><option value="user">User</option><option value="developer">Developer</option><option value="admin">Admin</option></select></td><td><select value={u.status} onChange={e=>updateUser(u.id,"status",e.target.value)}><option value="active">Active</option><option value="suspended">Suspended</option></select></td><td>{u.applications_count} applications · {u.resumes_count} resumes</td></tr>)}</tbody></table></section></>}
   {tab==="Job sources"&&<><section className="admin-card"><h2>Add public company job board</h2><form className="admin-form" onSubmit={saveSource}><label>Provider<select value={provider} onChange={e=>setProvider(e.target.value)}><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option></select></label><label>Public board identifier<input value={board} onChange={e=>setBoard(e.target.value)} placeholder="company-board-name" required/></label><button type="submit">Add board</button></form></section><section className="admin-card"><h2>Configured boards</h2>{sources.length?sources.map(s=><article className="admin-row" key={s.id}><div><b>{s.provider}</b><small>{s.board_key}</small></div><span>{s.active?"Active":"Paused"}</span><button onClick={()=>toggleSource(s.id,!s.active)}>{s.active?"Pause":"Enable"}</button><button onClick={()=>removeSource(s.id)}>Remove</button></article>):<p>No company boards configured. Jobicy and Remote OK public feeds still run.</p>}</section><section className="admin-card"><h2>Recent ingestion runs</h2>{runs.map((r,i)=><article className="admin-row" key={i}><div><b>{r.source} · {r.board_key}</b><small>{r.started_at?new Date(r.started_at).toLocaleString():""}</small></div><span>{r.status}</span><span>{r.inserted_count} new / {r.updated_count} updated</span>{r.error_message&&<small>{r.error_message}</small>}</article>)}</section></>}
   {tab==="Feature flags"&&<><section className="admin-card"><div className="admin-row"><h2>Feature rollout</h2><button onClick={addFlag}>Create flag</button></div>{flags.length?flags.map(f=><article className="admin-row" key={f.flag_key}><div><b>{f.flag_key}</b><small>{f.description}</small></div><span>{f.enabled?"Enabled":"Disabled"}</span><button onClick={()=>toggleFlag(f)}>Toggle</button></article>):<p>No feature flags have been created.</p>}</section></>}
   {tab==="Developer"&&<><section className="admin-card"><h2>Service health</h2><div className="admin-health"><article><small>API</small><b>{health?.api||"unknown"}</b></article><article><small>Database</small><b>{health?.database||"unknown"}</b></article><article><small>Secrets</small><b>Values hidden</b></article></div><p>Provider configuration status (presence only)</p><div className="admin-providers">{Object.entries(health?.providers||{}).map(([k,v])=><article key={k}><span>{k}</span><b>{v?"Configured":"Not configured"}</b></article>)}</div><p>Delivery queue: {JSON.stringify(health?.delivery_queue||{})}</p></section><section className="admin-card"><h2>Audit trail</h2>{audit.map(a=><article className="admin-row" key={a.id}><div><b>{a.event_type}</b><small>{a.email} · {new Date(a.created_at).toLocaleString()}</small></div><code>{a.resource_id||"system"}</code></article>)}</section></>}
   <footer className="admin-footer">Life Easy control plane · Admin actions are audited · Provider secrets remain in the hosting secret manager.</footer>
  </section>
 </main>;
}
