import "../components/creator/creator.css";

const SECTIONS: readonly { title: string; text: string }[] = [
  {
    title: "What Watch Me! shows",
    text: "Watch Me! shows short clips of shelter dogs, shared by shelters. The clips are samples. They are not a behavior or safety assessment. Meet the dog and talk to the shelter before adopting.",
  },
  {
    title: "How facts are made",
    text: "An AI tool drafts each fact from a clip. A shelter member watches the clip and confirms or changes the fact. Shelter staff publish the profile.",
  },
  {
    title: "Questions",
    text: "Questions are answered only with confirmed facts. If no fact applies, Watch Me! says so. Health questions go to the shelter's vet.",
  },
  {
    title: "Adoption",
    text: "Watch Me! does not take adoption applications or payments. Contact the shelter.",
  },
  {
    title: "Your data",
    text: "A question you type is stored for up to 30 days. Counts of questions are kept for up to 90 days. Questions use a cookie to count the hourly limit.",
  },
  {
    title: "Clips",
    text: "Shelter staff can delete a clip or a dog. Copies that someone already downloaded cannot be recalled.",
  },
  {
    title: "Whole clips",
    text: "The profile plays only the part of a clip that a fact cites. The whole clip file is reachable by anyone who has its link while the dog is published.",
  },
  {
    title: "Status of this page",
    text: "This is a draft for the first release. It has not had a legal review.",
  },
];

/** S11 Terms (05 section 5). Plain headings and paragraphs. */
export default function TermsPage() {
  return (
    <div className="wm-page" style={{ paddingTop: 16 }}>
      <h1>Terms</h1>
      {SECTIONS.map((s) => (
        <section key={s.title}>
          <h2>{s.title}</h2>
          <p>{s.text}</p>
        </section>
      ))}
    </div>
  );
}
