import { createElement, type ReactNode } from "react";

// Native MathML aligns accents, fractions and scripts without font-dependent
// Unicode superscript/subscript glyphs or scaling the formula as an image.
const m = (
  tag: string,
  children: ReactNode[],
  props: Record<string, string> = {},
) => createElement(tag, props, ...children);
const symbol = (value: string) => m("mi", [value]);
const op = (value: string) => m("mo", [value]);
const sub = (base: ReactNode, index: string) =>
  m("msub", [base, symbol(index)]);
const accent = (base: string, mark: string) =>
  m("mover", [symbol(base), m("mo", [mark], { stretchy: "true" })], {
    accent: "true",
  });
const minusHalf = () =>
  m("mrow", [op("−"), m("mfrac", [m("mn", ["1"]), m("mn", ["2"])])]);

export function StabilityFormula({
  kind,
}: {
  kind: "oas" | "tangent" | "alignment" | "centering";
}) {
  const expressions = {
    oas: [
      accent("Σ", "^"),
      op("→"),
      m("msub", [symbol("Σ"), m("mtext", ["OAS"])]),
    ],
    tangent: [
      sub(symbol("S"), "i"),
      op("="),
      m("mi", ["log"], { mathvariant: "normal" }),
      op("("),
      m("msup", [symbol("R"), minusHalf()]),
      sub(symbol("C"), "i"),
      m("msup", [symbol("R"), minusHalf()]),
      op(")"),
    ],
    alignment: [
      sub(accent("X", "~"), "t"),
      op("="),
      m("msubsup", [accent("R", "¯"), symbol("t"), minusHalf()]),
      sub(symbol("X"), "t"),
    ],
    centering: [
      sub(accent("y", "^"), "t"),
      op("="),
      symbol("σ"),
      op("("),
      sub(symbol("z"), "t"),
      op("−"),
      sub(symbol("μ"), "t"),
      op(")"),
    ],
  };
  return createElement(
    "math",
    {
      xmlns: "http://www.w3.org/1998/Math/MathML",
      className: "stability-formula",
    },
    m("mrow", expressions[kind]),
  );
}
