import type { ReactNode } from "react";

// Draw accents explicitly so their visibility and position do not depend on
// MathML accent support or the glyph metrics of a fallback math font.
function Accent({ base, mark }: { base: string; mark: "hat" | "tilde" | "bar" }) {
  const paths = {
    hat: "M2 6 L8 1 L14 6",
    tilde: "M1 5 C4 -1 7 8 10 3 C12 0 14 2 15 2",
    bar: "M1 3 H15",
  };
  return (
    <span className="formula-accent">
      <svg viewBox="0 0 16 8" aria-hidden="true">
        <path d={paths[mark]} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <i>{base}</i>
    </span>
  );
}

function Script({ base, sub, sup }: { base: ReactNode; sub?: string; sup?: string }) {
  return (
    <span className="formula-script">
      {base}
      <span className="formula-scripts">
        {sup && <sup>{sup}</sup>}
        {sub && <sub>{sub}</sub>}
      </span>
    </span>
  );
}

export function StabilityFormula({ kind }: { kind: "oas" | "tangent" | "alignment" | "centering" }) {
  const sigmaHat = () => <Accent base="Σ" mark="hat" />;
  const inverseR = () => <Script base={<i>R</i>} sup="−1/2" />;
  const formulas = {
    oas: (
      <span>
        <span className="formula-oas-symbol"><Script base="Σ" sub="OAS" /></span> = (1 − <i>ρ</i>){sigmaHat()} + <i>ρ</i><span className="formula-fraction"><span>tr({sigmaHat()})</span><span><i>C</i></span></span><i>I</i>
      </span>
    ),
    tangent: <span><Script base={<i>S</i>} sub="i" /> = log({inverseR()}<Script base={<i>C</i>} sub="i" />{inverseR()})</span>,
    alignment: <span><Script base={<Accent base="X" mark="tilde" />} sub="t" /> = <Script base={<Accent base="R" mark="bar" />} sub="t" sup="−1/2" /><Script base={<i>X</i>} sub="t" /></span>,
    centering: <span><Script base={<Accent base="p" mark="hat" />} sub="t" /> = <i>σ</i>(<Script base={<i>z</i>} sub="t" /> − <Script base={<i>μ</i>} sub="t" />)</span>,
  };
  const labels = {
    oas: "Σ_OAS = (1 − ρ) Σ-hat + ρ tr(Σ-hat) / C I",
    tangent: "S_i = log(R^(−1/2) C_i R^(−1/2))",
    alignment: "X-tilde_t = R-bar_t^(−1/2) X_t",
    centering: "p-hat_t = σ(z_t − μ_t)",
  };
  return <span className={`stability-formula stability-formula-${kind}`} role="math" aria-label={labels[kind]}>{formulas[kind]}</span>;
}
