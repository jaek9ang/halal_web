function EllipsisText({ value, className = "" }) {
  const text = String(value || "-");

  return (
    <div className={className} title={text}>
      {text}
    </div>
  );
}

export default EllipsisText;
