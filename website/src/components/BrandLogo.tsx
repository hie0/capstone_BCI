const LOGO = "./brand/neurolink-logo-header.png?v=35e1e3a4";

export function BrandLogo({ footer = false }: { footer?: boolean }) {
  return (
    <img
      className={footer ? "brand-image footer-brand-image" : "brand-image"}
      src={LOGO}
      width="720"
      height="184"
      alt="NEUROLINK · MI-BCI RESEARCH LAB"
      decoding="async"
    />
  );
}
