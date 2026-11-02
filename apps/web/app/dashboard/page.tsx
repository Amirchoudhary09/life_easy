"use client";
import {useEffect,useState} from "react";
import type {FormEvent} from "react";
import Link from "next/link";
import {useRouter} from "next/navigation";
const API=process.env.NEXT_PUBLIC_API_BASE_URL||"http://localhost:8000";
const tabs=["Overview","Jobs","Applications","Resume & ATS","AI assistant","Connections","Approvals","Profile"];
const statuses=["planned","applied","assessment","interview","offer","rejected","withdrawn"];
export default function DashboardPage(){
 const router=useRouter();
 const [user,setUser]=useState<any>(null);
 const [tab,setTab]=useState("Overview");
 const [notice,setNotice]=useState("");
 const [profile,setProfile]=useState<any>({headline:"",location:"",experience_years:0,skills:[]});
 const [jobs,setJobs]=useState<any[]>([]);
 const [applications,setApplications]=useState<any[]>([]);
 const [resumes,setResumes]=useState<any[]>([]);
 const [resumeId,setResumeId]=useState("");
 const [jobDescription,setJobDescription]=useState("");
 const [ats,setAts]=useState<any>(null);
 const [query,setQuery]=useState("software engineer");
 const [locations,setLocations]=useState("India, Remote");
 const [chat,setChat]=useState<any[]>([{role:"assistant",content:"Hi! I’m Life Easy. Ask me about your resume, jobs, interviews or career plans."}]);
 const [chatText,setChatText]=useState("");
 const [conversationId,setConversationId]=useState("");
 const [busy,setBusy]=useState(false);
 const [integrations,setIntegrations]=useState<any[]>([]);
 const [linkCode,setLinkCode]=useState("");
 const [otp,setOtp]=useState("");
 const [phone,setPhone]=useState("");
 const [emailTo,setEmailTo]=useState("");
 const [emailSubject,setEmailSubject]=useState("");
 const [emailBody,setEmailBody]=useState("");
 const [pending,setPending]=useState<any>(null);
 const [approvals,setApprovals]=useState<any[]>([]);
 const [sourceStatus,setSourceStatus]=useState<any>(null);
 async function api(path:string,init:RequestInit={}){
  const headers=new Headers(init.headers||{});
  const csrf=document.cookie.split("; ").find(x=>x.startsWith("life_easy_csrf="))?.split("=")[1];
  if(csrf)headers.set("X-CSRF-Token",decodeURIComponent(csrf));
  if(init.body && !(init.body instanceof FormData))headers.set("Content-Type","application/json");
  const r=await fetch(API+path,{...init,headers,credentials:"include"});
  const data=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(data.detail||data.message||("Request failed: "+r.status));
  return data;
 }
 async function load(){
  const me=await api("/api/v1/auth/me");setUser(me.user);
  const results=await Promise.allSettled([
   api("/api/v1/profile"),api("/api/v1/applications",{},t),api("/api/v1/resumes",{},t),
   api("/api/v1/integrations",{},t),api("/api/v1/approvals",{},t),api("/api/v1/jobs/sources",{},t)
  ]);
  const [p,a,r,i,ap,s]=results;
  if(p.status==="fulfilled"&&p.value.profile)setProfile(p.value.profile);
  if(a.status==="fulfilled")setApplications(a.value.applications||[]);
  if(r.status==="fulfilled"){setResumes(r.value.resumes||[]);if(r.value.resumes?.[0])setResumeId(r.value.resumes[0].id);}
  if(i.status==="fulfilled")setIntegrations(i.value.integrations||[]);
  if(ap.status==="fulfilled")setApprovals(ap.value.approvals||[]);
  if(s.status==="fulfilled")setSourceStatus(s.value);
 }
 useEffect(()=>{load().catch(()=>router.replace("/login")).finally(()=>setBusy(false));},[router]);
 async function logout(){try{await api("/api/v1/auth/logout",{method:"POST"});}finally{router.replace("/login");}}
 async function saveProfile(e:FormEvent){e.preventDefault();try{await api("/api/v1/profile",{method:"PUT",body:JSON.stringify({...profile,experience_years:Number(profile.experience_years),skills:Array.isArray(profile.skills)?profile.skills:String(profile.skills||"").split(",").map((x:string)=>x.trim()).filter(Boolean),preferences:profile.preferences||{}})});setNotice("Profile saved.");}catch(e){setNotice((e as Error).message);}}
 async function searchJobs(e:FormEvent){e.preventDefault();setBusy(true);try{const d=await api("/api/v1/jobs/search",{method:"POST",body:JSON.stringify({query,locations:locations.split(",").map(x=>x.trim()).filter(Boolean),limit:40})});setJobs(d.jobs||[]);setNotice(d.message||("Found "+d.count+" jobs."));}catch(e){setNotice((e as Error).message);}finally{setBusy(false);}}
 async function saveJob(j:any){try{await api("/api/v1/jobs/"+j.id+"/save",{method:"POST"});setJobs(v=>v.map(x=>x.id===j.id?{...x,saved_status:"saved"}:x));setNotice("Job saved.");}catch(e){setNotice((e as Error).message);}}
 async function trackJob(j:any){try{await api("/api/v1/applications",{method:"POST",body:JSON.stringify({job_id:j.id,company:j.company,role:j.title,job_url:j.apply_url,status:"planned"})});const d=await api("/api/v1/applications");setApplications(d.applications||[]);setNotice("Added to application tracker.");}catch(e){setNotice((e as Error).message);}}
 async function changeStatus(id:string,status:string){try{await api("/api/v1/applications/"+id,{method:"PATCH",body:JSON.stringify({status})});setApplications(v=>v.map(x=>x.id===id?{...x,status}:x));}catch(e){setNotice((e as Error).message);}}
 async function upload(e:FormEvent<HTMLFormElement>){e.preventDefault();const input=e.currentTarget.elements.namedItem("resume") as HTMLInputElement;const f=input.files?.[0];if(!f)return;const fd=new FormData();fd.append("file",f);try{const d=await api("/api/v1/resumes",{method:"POST",body:fd});setNotice("Resume parsed. Skills: "+d.extracted.skills.join(", "));const r=await api("/api/v1/resumes");setResumes(r.resumes||[]);setResumeId(d.resume.id);input.value="";}catch(e){setNotice((e as Error).message);}}
 async function analyze(e:FormEvent){e.preventDefault();try{const d=await api("/api/v1/resumes/"+resumeId+"/analyze",{method:"POST",body:JSON.stringify({job_description:jobDescription})});setAts(d);}catch(e){setNotice((e as Error).message);}}
 async function ask(e:FormEvent){e.preventDefault();const text=chatText.trim();if(!text)return;setChat(v=>[...v,{role:"user",content:text}]);setChatText("");setBusy(true);try{const d=await api("/api/v1/assistant/chat",{method:"POST",body:JSON.stringify({message:text,conversation_id:conversationId||null})});setConversationId(d.conversation_id);setChat(v=>[...v,{role:"assistant",content:d.answer}]);}catch(e){setChat(v=>[...v,{role:"assistant",content:(e as Error).message}]);}finally{setBusy(false);}}
 async function gmail(){try{const d=await api("/api/v1/integrations/gmail/connect");window.location.assign(d.authorization_url);}catch(e){setNotice((e as Error).message);}}
 async function whatsappCode(){try{const d=await api("/api/v1/webhooks/whatsapp/link-code",{method:"POST"});setLinkCode(d.code);}catch(e){setNotice((e as Error).message);}}
 async function emailOtp(){try{await api("/api/v1/verification/email/send",{method:"POST"});setNotice("Email OTP sent.");}catch(e){setNotice((e as Error).message);}}
 async function verifyEmail(){try{await api("/api/v1/verification/email/verify",{method:"POST",body:JSON.stringify({code:otp})});setUser((u:any)=>({...u,email_verified:true}));setOtp("");setNotice("Email verified.");}catch(e){setNotice((e as Error).message);}}
 async function smsOtp(){try{await api("/api/v1/verification/phone/send",{method:"POST",body:JSON.stringify({phone_e164:phone})});setNotice("SMS verification started.");}catch(e){setNotice((e as Error).message);}}
 async function verifyPhone(){try{await api("/api/v1/verification/phone/verify",{method:"POST",body:JSON.stringify({code:otp})});setOtp("");setNotice("Phone verified.");}catch(e){setNotice((e as Error).message);}}
 async function makeApproval(e:FormEvent){e.preventDefault();try{const d=await api("/api/v1/approvals",{method:"POST",body:JSON.stringify({action_type:"email.send",channel:"gmail",recipient:emailTo,subject:emailSubject,message:emailBody,attachments:[],metadata:{source:"dashboard"}})});setPending(d.approval);setApprovals(v=>[d.approval,...v]);setNotice("Preview created. No email has been sent.");}catch(e){setNotice((e as Error).message);}}
 async function approve(){if(!pending)return;try{const d=await api("/api/v1/approvals/"+pending.id+"/confirm",{method:"POST",body:JSON.stringify({confirm:true,content_hash:pending.content_hash})});setPending(null);setNotice(d.execution==="queued"?"Approved and queued. The worker will send only if Gmail is connected.":"Approval updated.");const a=await api("/api/v1/approvals");setApprovals(a.approvals||[]);}catch(e){setNotice((e as Error).message);}}
 if(busy&&!user)return <main className="dashboard-shell">Loading Life Easy…</main>;
 return <main className="le-app"><aside className="le-sidebar"><Link className="brand" href="/">life<span>easy</span></Link><small>CAREER WORKSPACE</small>{tabs.map(x=><button key={x} className={tab===x?"active":""} onClick={()=>setTab(x)}>{x}</button>)}<div className="le-side-bottom">{user?.email}<button onClick={logout}>Log out</button></div></aside><section className="le-main"><header className="le-topbar"><div><b>LIFE EASY / CAREER OS</b><small>{user?.display_name||user?.email}</small></div><span>{user?.email_verified?"Email verified":"Email not verified"}</span></header>{notice&&<div className="le-notice">{notice}<button onClick={()=>setNotice("")}>×</button></div>}
 {tab==="Overview"&&<><div className="le-page-title"><small>YOUR CAREER, ORGANIZED</small><h1>Welcome, {user?.display_name||"there"}.</h1><p>Discover roles, improve your resume, track applications and manage career communication in one place.</p></div><div className="le-stat-grid"><article><small>Applications</small><strong>{applications.length}</strong></article><article><small>Resumes</small><strong>{resumes.length}</strong></article><article><small>Connected apps</small><strong>{integrations.length}</strong></article><article><small>Indexed jobs</small><strong>{sourceStatus?.indexed_jobs??"—"}</strong></article></div><div className="le-panel"><h2>Start here</h2><div className="le-quick-grid">{["Jobs","Resume & ATS","AI assistant","Connections"].map(x=><button key={x} onClick={()=>setTab(x)}>{x} →</button>)}</div></div></>}
 {tab==="Jobs"&&<><div className="le-page-title"><small>JOB DISCOVERY</small><h1>Find your next role.</h1><p>Results are indexed from public Greenhouse and Lever career boards configured by the service owner.</p></div><form className="le-form le-job-form" onSubmit={searchJobs}><label>Role or skills<input value={query} onChange={e=>setQuery(e.target.value)}/></label><label>Locations<input value={locations} onChange={e=>setLocations(e.target.value)}/></label><button className="le-primary" disabled={busy}>Search jobs</button></form><div className="le-panel">{jobs.map(j=><article className="le-job" key={j.id}><div><small>{j.company} · {j.source}</small><h3>{j.title}</h3><p>{j.location} · {j.match?.score??0}% match</p></div><div><button onClick={()=>saveJob(j)}>Save</button><button onClick={()=>trackJob(j)}>Track</button><a href={j.apply_url} target="_blank" rel="noreferrer">Apply ↗</a></div></article>)}</div></>}
 {tab==="Applications"&&<><div className="le-page-title"><small>APPLICATION PIPELINE</small><h1>Keep every opportunity moving.</h1></div><div className="le-panel">{applications.length===0?"No applications yet. Use Track from job search.":applications.map(a=><article className="le-application" key={a.id}><div><b>{a.role||"Role"}</b><p>{a.company||"Company"}</p></div><select value={a.status} onChange={e=>changeStatus(a.id,e.target.value)}>{statuses.map(s=><option key={s}>{s}</option>)}</select></article>)}</div></>}
 {tab==="Resume & ATS"&&<><div className="le-page-title"><small>RESUME INTELLIGENCE</small><h1>Make your experience stand out.</h1><p>Private PDF/DOCX storage, text extraction and a transparent heuristic review.</p></div><div className="le-panel"><form className="le-form" onSubmit={upload}><label>Upload resume<input type="file" name="resume" accept=".pdf,.docx" required/></label><button className="le-primary">Upload & parse</button></form>{resumes.map(r=><button className="le-resume" key={r.id} onClick={()=>{setResumeId(r.id);setAts(null);}}>{r.filename} · {Math.round(r.byte_size/1024)} KB</button>)}</div><div className="le-panel"><h2>ATS-style analysis</h2><form className="le-form" onSubmit={analyze}><label>Paste target job description (optional)<textarea rows={5} value={jobDescription} onChange={e=>setJobDescription(e.target.value)}/></label><button className="le-primary" disabled={!resumeId}>Analyze resume</button></form>{ats&&<div><h2>{ats.heuristic_score}/100</h2><small>Heuristic score, not a vendor ATS score</small><p>Matched: {ats.matched_target_skills.join(", ")}</p><p>Missing: {ats.missing_target_skills.join(", ")}</p><ul>{ats.recommendations.map((x:string)=><li key={x}>{x}</li>)}</ul></div>}</div></>}
 {tab==="AI assistant"&&<><div className="le-page-title"><small>CAREER COPILOT</small><h1>Ask Life Easy.</h1></div><div className="le-chat"><div className="le-chat-messages">{chat.map((m,i)=><p className={m.role} key={i}>{m.content}</p>)}</div><form onSubmit={ask}><textarea rows={2} value={chatText} onChange={e=>setChatText(e.target.value)} placeholder="Ask about jobs, resumes, interviews…"/><button className="le-primary" disabled={busy}>Send</button></form></div></>}
 {tab==="Connections"&&<><div className="le-page-title"><small>CONNECTED ACCOUNTS</small><h1>Your accounts, your control.</h1></div><div className="le-panel"><div className="le-connection"><div><b>Gmail</b><p>Connect your own Gmail. Career emails are sent only after your approval.</p></div><button className="le-primary" onClick={gmail}>Connect Gmail</button></div><div className="le-connection"><div><b>WhatsApp Business</b><p>Generate a one-time code and send LINK CODE to the official Life Easy number.</p>{linkCode&&<code>{linkCode}</code>}</div><button onClick={whatsappCode}>Generate link code</button></div>{integrations.map((x,i)=><p key={i}>{x.provider}: {x.account_email||x.status}</p>)}</div><div className="le-panel"><h2>Verify account</h2><p>{user?.email} · {user?.email_verified?"Verified":"Not verified"}</p><button onClick={emailOtp}>Send email OTP</button><div className="le-inline-form"><input value={otp} onChange={e=>setOtp(e.target.value)} placeholder="6-digit OTP" maxLength={6}/><button onClick={verifyEmail}>Verify email</button></div><div className="le-inline-form"><input value={phone} onChange={e=>setPhone(e.target.value)} placeholder="+919876543210"/><button onClick={smsOtp}>Send SMS OTP</button></div><div className="le-inline-form"><input value={otp} onChange={e=>setOtp(e.target.value)} placeholder="SMS code" maxLength={6}/><button onClick={verifyPhone}>Verify phone</button></div></div></>}
 {tab==="Approvals"&&<><div className="le-page-title"><small>EXTERNAL ACTION CONTROL</small><h1>Nothing goes out without your OK.</h1><p>Review the exact destination and complete message before any email is sent.</p></div><div className="le-panel"><h2>Prepare an email</h2><form className="le-form" onSubmit={makeApproval}><label>Recipient<input type="email" value={emailTo} onChange={e=>setEmailTo(e.target.value)} required/></label><label>Subject<input value={emailSubject} onChange={e=>setEmailSubject(e.target.value)} required/></label><label>Exact message<textarea rows={7} value={emailBody} onChange={e=>setEmailBody(e.target.value)} required/></label><button className="le-primary">Create preview</button></form>{pending&&<div className="le-preview"><b>TO: {pending.payload.recipient}</b><p>{pending.payload.subject}</p><pre>{pending.payload.message}</pre><button className="le-primary" onClick={approve}>Approve this exact email</button><button onClick={()=>setPending(null)}>Cancel</button></div>}</div><div className="le-panel"><h2>Recent approvals</h2>{approvals.map(a=><p key={a.id}>{a.payload.recipient} · {a.status}</p>)}</div></>}
 {tab==="Profile"&&<><div className="le-page-title"><small>CAREER PROFILE</small><h1>Set your direction.</h1></div><div className="le-panel"><form className="le-form" onSubmit={saveProfile}><label>Professional headline<input value={profile.headline||""} onChange={e=>setProfile((p:any)=>({...p,headline:e.target.value}))}/></label><label>Preferred location<input value={profile.location||""} onChange={e=>setProfile((p:any)=>({...p,location:e.target.value}))}/></label><label>Experience years<input type="number" min="0" max="60" value={profile.experience_years??0} onChange={e=>setProfile((p:any)=>({...p,experience_years:e.target.value}))}/></label><label>Skills (comma separated)<input value={Array.isArray(profile.skills)?profile.skills.join(", "):profile.skills||""} onChange={e=>setProfile((p:any)=>({...p,skills:e.target.value}))}/></label><button className="le-primary">Save profile</button></form></div></>}
 <footer className="le-footer">Life Easy · Career-first AI workspace · External actions require explicit approval.</footer></section></main>;
}
