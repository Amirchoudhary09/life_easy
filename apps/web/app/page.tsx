const cards = [
 {title:"Job discovery",detail:"Find relevant SDE, internship, and other roles across permitted job sources and company career pages.",icon:"⌕",primary:true},
 {title:"Resume & matching",detail:"Understand your fit for each role using your skills, experience, resume, and preferences.",icon:"◎",primary:true},
 {title:"Recruiter research",detail:"Find publicly listed recruiter contacts with source links and prepare tailored outreach.",icon:"↗",primary:true},
 {title:"Application tracker",detail:"Track saved jobs, applications, interviews, follow-ups, and outcomes in one place.",icon:"▤",primary:true},
 {title:"Career email",detail:"Prepare personalized recruiter and application emails; send only after your approval.",icon:"✉"},
 {title:"LinkedIn career tools",detail:"Draft posts, connection notes, recruiter messages, and profile improvements.",icon:"in"}
];
export default function Home() {
 return <main className="shell">
  <nav className="nav"><a className="brand" href="/">life<span>easy</span></a><span className="pill"><i/> Career-first AI workspace</span></nav>
  <section className="hero"><p className="eyebrow">YOUR CAREER, ORGANIZED</p><h1>Find your next move.<br/><em>Let AI handle the busywork.</em></h1><p className="intro">Your career-first AI assistant: discover jobs, match your profile, research recruiters, manage applications, and prepare career emails and LinkedIn content — with you in control.</p><div className="actions"><a className="primary" href="#workspace">Explore workspace <span>→</span></a><span className="note">Early access · Integrations not connected</span></div></section>
  <section id="workspace" className="workspace"><div className="section-head"><div><p className="eyebrow">CAREER WORKSPACE</p><h2>Everything for your next opportunity.</h2></div><span className="status">Setup required</span></div>
   <div className="grid">{cards.map(card=><article className="card" key={card.title}><span className="card-icon">{card.icon}</span><h3>{card.title}</h3><p>{card.detail}</p><span className="coming">{card.primary ? "Core job-hunting module" : "Supporting career module"}</span></article>)}</div>
  </section><footer><span>Life Easy</span><span>External actions always require your approval.</span></footer>
 </main>;
}
