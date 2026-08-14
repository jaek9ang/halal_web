function StatLine({ items }) {
  return (
    <div className="stat-line">
      {items.map((item) => (
        <div className="stat-cell" key={item.label}>
          <strong>{item.value}</strong>
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

export default StatLine;
