import React, { Suspense, lazy, useEffect } from "react";
import ReactDOM from "react-dom/client";
import {
  HashRouter,
  Navigate,
  Route,
  Routes,
  Link,
  useLocation,
} from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { BrandLogo } from "./components/BrandLogo";
import "./styles.css";
import Home from "./pages/Home";
const Simulation = lazy(() => import("./pages/Simulation"));
function App() {
  const location = useLocation();
  useEffect(() => {
    if (location.hash) {
      const scrollTimer = window.setTimeout(() => {
        document
          .getElementById(location.hash.slice(1))
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
      return () => window.clearTimeout(scrollTimer);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [location.pathname, location.hash]);

  const navItems = [
    {
      label: "연구 개요",
      to: "/#research-overview",
      active:
        location.pathname === "/" &&
        (!location.hash || location.hash === "#research-overview"),
    },
    {
      label: "연구 내용",
      to: "/#research-content",
      active:
        location.pathname === "/" && location.hash === "#research-content",
    },
    {
      label: "연구 결과",
      to: "/#research-results",
      active:
        location.pathname === "/" && location.hash === "#research-results",
    },
    {
      label: "응용",
      to: "/simulation",
      active: location.pathname === "/simulation",
      featured: true,
    },
  ];
  return (
    <>
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        본문으로 건너뛰기
      </a>
      <header>
        <div className="container header-inner">
          <Link className="brand" to="/" aria-label="NEUROLINK 홈">
            <BrandLogo />
          </Link>
          <nav aria-label="메인 내비게이션">
            {navItems.map((item) => (
              <Link
                key={item.label}
                to={item.to}
                className={item.active ? "active" : undefined}
                aria-current={item.active ? "page" : undefined}
              >
                {item.label}
                {item.featured && <span className="nav-dot" />}
              </Link>
            ))}
          </nav>
          <Link className="header-link" to="/simulation">
            응용 체험 <ArrowUpRight size={16} />
          </Link>
        </div>
      </header>
      <div id="main-content" tabIndex={-1}>
        <Suspense
          fallback={<div className="loading">연구실을 준비하고 있습니다…</div>}
        >
          <Routes>
            <Route path="/" element={<Home />} />
            <Route
              path="/research"
              element={<Navigate to="/#research-content" replace />}
            />
            <Route path="/simulation" element={<Simulation />} />
            <Route
              path="*"
              element={
                <main className="container section">
                  <h1>페이지를 찾을 수 없습니다.</h1>
                  <Link to="/">홈으로 돌아가기</Link>
                </main>
              }
            />
          </Routes>
        </Suspense>
      </div>
      <footer className="container">
        <div>
          <Link className="footer-brand" to="/" aria-label="NEUROLINK 홈">
            <BrandLogo footer />
          </Link>
          <span>국립부경대학교 컴퓨터·인공지능공학부</span>
        </div>
        <p>
          운동 상상 EEG의 시공간 제약 극복을 위한 연구
          <br />
          <span>CAPSTONE DESIGN · RESEARCH PROTOTYPE</span>
        </p>
      </footer>
    </>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);
