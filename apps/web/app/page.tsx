import Link from "next/link";

const cards = [
  { title: "Job discovery", detail: "Fresh roles from public company boards (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) and Adzuna, with source links.", icon: "⌕", primary: true },
  { title: "Resume & matching", detail: "Every match scored against your resume, skills and preferences, with the strengths and gaps explained.", icon: "◎", primary: true },
  { title: "Recruiter research", detail: "Publicly listed contacts only, each with the page it came from. Never guessed addresses.", icon: "↗", primary: true },
  { title: "Application tracker", detail: "Applications, interviews and follow-ups in one place, updated from your inbox.", icon: "▤", primary: true },
  { title: "Career email", detail: "Drafts from your own Gmail, Outlook or any IMAP mailbox. Sent only after you approve the exact message.", icon: "✉" },
  { title: "LinkedIn career tools", detail: "Posts, connection notes and recruiter messages, published only through LinkedIn's official API.", icon: "in" },
  { title: "WhatsApp & Telegram", detail: "Chat with the assistant from your phone; approve or reject with one tap.", icon: "☏" },
  { title: "Daily automations", detail: "Morning job digest, follow-up drafts, interview prep the day before, weekly report.", icon: "↻" },
];

export default function Home() {
  return (
    <main className="shell">
      <nav className="nav">
        <a className="brand" href="/">
          life<span>easy</span>
        </a>
        <div className="row">
          <span className="pill">
            <i /> Career-first AI workspace
          </span>
          <Link className="ghost-link" href="/login">
            Log in
          </Link>
        </div>
      </nav>
      <section className="hero">
        <p className="eyebrow">YOUR CAREER, ORGANIZED</p>
        <h1>
          Find your next move.
          <br />
          <em>Let AI handle the busywork.</em>
        </h1>
        <p className="intro">
          Your career-first AI assistant: discover jobs, match your profile, research recruiters, manage applications, and prepare career emails and LinkedIn content — with you in control.
        </p>
        <div className="actions">
          <Link className="primary" href="/register">
            Get started <span>→</span>
          </Link>
          <a className="note" href="#workspace">
            See what it does
          </a>
        </div>
      </section>
      <section id="workspace" className="workspace">
        <div className="section-head">
          <div>
            <p className="eyebrow">CAREER WORKSPACE</p>
            <h2>Everything for your next opportunity.</h2>
          </div>
          <span className="status">Nothing is sent without your approval</span>
        </div>
        <div className="grid">
          {cards.map((card) => (
            <article className="card" key={card.title}>
              <span className="card-icon">{card.icon}</span>
              <h3>{card.title}</h3>
              <p>{card.detail}</p>
              <span className="coming">{card.primary ? "Core job-hunting module" : "Supporting career module"}</span>
            </article>
          ))}
        </div>
      </section>
      <footer>
        <span>Life Easy</span>
        <span>External actions always require your approval.</span>
      </footer>
    </main>
  );
}
