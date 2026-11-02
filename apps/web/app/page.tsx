const cards = [
 {title:"Job discovery",detail:"Search relevant roles across permitted job sources and company career pages.",icon:"⌕"},
 {title:"Profile matching",detail:"Compare each role with your verified skills, experience, and resume.",icon:"◎"},
 {title:"Recruiter research",detail:"Collect publicly listed recruiting contacts with source links.",icon:"↗"},
 {title:"Email approvals",detail:"Draft tailored outreach and require your approval before sending.",icon:"✉"}
];
export default function Home() {
 return <main className="shell">
  <nav className="nav"><a className="brand" href="/">life<span>easy</span></a><span className="pill"><i/> Personal workspace</span></nav>
  <section className="hero"><p className="eyebrow">YOUR CAREER, ORGANIZED</p><h1>One assistant.<br/><em>Your entire job search.</em></h1><p className="intro">Discover relevant opportunities, understand your match, research public recruiter contacts, and prepare thoughtful outreach — with you in control.</p><div className="actions"><a className="primary" href="#workspace">Open workspace <span>→</span></a><span className="note">Early access · Integrations not connected</span></div></section>
  <section id="workspace" className="workspace"><div className="section-head"><div><p className="eyebrow">WORKSPACE</p><h2>Build your next move.</h2></div><span className="status">Setup required</span></div>
   <div className="grid">{cards.map(card=><article className="card" key={card.title}><span className="card-icon">{card.icon}</span><h3>{card.title}</h3><p>{card.detail}</p><span className="coming">Integration setup required</span></article>)}</div>
  </section><footer><span>Life Easy</span><span>External actions always require your approval.</span></footer>
 </main>;
}
