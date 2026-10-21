// Markdown tables in a box that scrolls sideways, so a wide table never pushes the page wider than a phone.
export default function ScrollTable({ node, ...props }) {
  return (
    <div className="radha-table-wrap" data-testid="scroll-table">
      <table {...props} />
    </div>
  );
}
