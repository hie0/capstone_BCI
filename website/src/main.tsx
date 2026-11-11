import React, { Suspense, lazy, useEffect } from "react";
import ReactDOM from "react-dom/client";
import {
  HashRouter,
  NavLink,
  Route,
  Routes,
  Link,
  useLocation,
} from "react-router-dom";
import { BrainCircuit, ArrowUpRight } from "lucide-react";
import "./styles.css";
const Home = lazy(() => import("./pages/Home"));
const Research = lazy(() => import("./pages/Research"));
const Simulation = lazy(() => import("./pages/Simulation"));
function App() {
  const location = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);
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
          <Link className="brand" to="/">
            <span className="brand-symbol">
              <BrainCircuit size={24} />
            </span>
            <span>
              NEURO<span className="brand-light">LINK</span>
              <small>MI-BCI RESEARCH LAB</small>
            </span>
          </Link>
          <nav aria-label="메인 내비게이션">
            <NavLink to="/" end>
              Home
            </NavLink>
            <NavLink to="/research">Research</NavLink>
            <NavLink to="/simulation">
              Simulation <span className="nav-dot" />
            </NavLink>
          </nav>
          <Link className="header-link" to="/simulation">
            Enter the lab <ArrowUpRight size={16} />
          </Link>
        </div>
      </header>
      <div id="main-content" tabIndex={-1}>
        <Suspense
          fallback={<div className="loading">연구실을 준비하고 있습니다…</div>}
        >
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/research" element={<Research />} />
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
          <BrainCircuit size={20} />
          <strong>NEUROLINK</strong>
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
