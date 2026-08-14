function PageHeader({ eyebrow, title, desc, onBack }) {
  return (
    <div className="page-header">
      <button className="back-button" onClick={onBack}>
        ← 홈
      </button>

      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{desc}</p>
      </div>
    </div>
  );
}

export default PageHeader;
